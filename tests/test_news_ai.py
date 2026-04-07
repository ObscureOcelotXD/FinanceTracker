"""Tests for Groq-backed news holdings relevance (POC)."""

import json
import sqlite3
from unittest.mock import MagicMock

import api.news_ai as news_ai
from services import db_manager


def test_normalize_relevance_filters_to_universe():
    u = {"LMT": "Plaid-linked", "BA": "Manage Stocks"}
    out = news_ai._normalize_relevance(
        {"mentioned": ["lmt", "ZZZ"], "relevant": ["ba", "BA"], "note": " test "},
        u,
    )
    assert out["mentioned"] == ["LMT"]
    assert out["relevant"] == ["BA"]
    assert "test" in out["note"]


def test_enrich_merges_ai_tickers(tmp_path, monkeypatch):
    db_path = tmp_path / "t.db"
    db_manager.DATABASE = str(db_path)
    db_manager.init_db()
    import api.news_digest as nd

    monkeypatch.setattr(
        nd,
        "portfolio_ticker_universe",
        lambda: ({"LMT": "Plaid-linked", "X": "Manage Stocks"}, {}),
    )

    items = [
        {
            "tickers": ["X"],
            "ticker_companies": {"X": "Manage Stocks"},
            "ai_relevance": {"mentioned": [], "relevant": ["LMT"], "note": "Defense"},
        }
    ]
    news_ai.enrich_items_with_merged_tickers(items)
    assert sorted(items[0]["tickers"]) == ["LMT", "X"]
    assert "LMT" in items[0]["ticker_companies"]


def test_run_batch_skips_when_disabled(tmp_path, monkeypatch):
    db_path = tmp_path / "t.db"
    db_manager.DATABASE = str(db_path)
    db_manager.init_db()
    monkeypatch.delenv("NEWS_AI_ENABLED", raising=False)
    assert news_ai.run_news_ai_relevance_batch() == 0


def test_run_batch_calls_groq_and_stores(tmp_path, monkeypatch):
    import api.news_digest as nd
    db_path = tmp_path / "t.db"
    db_manager.DATABASE = str(db_path)
    db_manager.init_db()
    monkeypatch.setenv("NEWS_AI_ENABLED", "1")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("NEWS_AI_MAX_ARTICLES_PER_RUN", "5")

    now = "2026-06-15T12:00:00+00:00"
    conn = sqlite3.connect(db_manager.DATABASE)
    conn.execute(
        """INSERT INTO news_digest_articles (
            url, title, source_feed, categories_json, tickers_json, ticker_companies_json,
            first_seen_at_utc, last_seen_at_utc, summary
        ) VALUES (?, ?, ?, '[]', '[]', '{}', ?, ?, ?)""",
        ("https://ex.com/a", "Headline", "T", now, now, "Body mentions LMT."),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        nd,
        "portfolio_ticker_universe",
        lambda: ({"LMT": "Plaid-linked"}, {"unique_for_matching": 1}),
    )

    mock_post = MagicMock()
    mock_post.return_value.raise_for_status = MagicMock()
    mock_post.return_value.json.return_value = {
        "choices": [{"message": {"content": json.dumps({"mentioned": ["LMT"], "relevant": [], "note": "ok"})}}]
    }
    monkeypatch.setattr(news_ai.requests, "post", mock_post)

    n = news_ai.run_news_ai_relevance_batch()
    assert n == 1
    rows, total, _ = db_manager.list_news_digest_articles(page=1, per_page=10)
    assert total == 1
    assert rows[0]["ai_relevance"]["mentioned"] == ["LMT"]
    assert rows[0]["ai_processed_at_utc"]


def test_list_pending_ai_respects_limit(tmp_path):
    _init = tmp_path / "t.db"
    db_manager.DATABASE = str(_init)
    db_manager.init_db()
    conn = sqlite3.connect(db_manager.DATABASE)
    now = "2026-06-15T12:00:00+00:00"
    for i in range(5):
        conn.execute(
            """INSERT INTO news_digest_articles (
                url, title, source_feed, categories_json, tickers_json, ticker_companies_json,
                first_seen_at_utc, last_seen_at_utc, summary
            ) VALUES (?, ?, ?, '[]', '[]', '{}', ?, ?, NULL)""",
            (f"https://ex.com/{i}", f"H{i}", "T", now, now),
        )
    conn.commit()
    conn.close()
    pending = db_manager.list_news_digest_articles_pending_ai(days=2, limit=2)
    assert len(pending) == 2
