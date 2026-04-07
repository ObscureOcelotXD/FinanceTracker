"""Home page Groq cross-insights (news + SEC)."""

import json
from unittest.mock import MagicMock

import api.home_insights as hi
from services import db_manager


def test_normalize_sources_merges_labels():
    catalog = [
        {"kind": "news", "label": "N1", "title": "Headline", "url": "https://a.com/x"},
        {"kind": "sec", "label": "S1", "title": "MSFT 10-K", "detail": "2024-01-01"},
    ]
    raw = [
        {"kind": "news", "label": "N1", "title": ""},
        {"kind": "sec", "label": "S1", "title": "MSFT 10-K"},
    ]
    out = hi._normalize_sources(raw, catalog)
    assert len(out) == 2
    assert out[0].get("url") == "https://a.com/x"


def test_generate_stores_insight(tmp_path, monkeypatch):
    db_path = tmp_path / "t.db"
    db_manager.DATABASE = str(db_path)
    db_manager.init_db()
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("HOME_INSIGHTS_ENABLED", "1")

    mock_post = MagicMock()
    mock_post.return_value.raise_for_status = MagicMock()
    mock_post.return_value.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "insights": "- First point\n- Second",
                            "sources": [{"kind": "news", "title": "T", "label": "N1", "url": "https://z.com"}],
                        }
                    )
                }
            }
        ]
    }
    monkeypatch.setattr(hi.requests, "post", mock_post)
    monkeypatch.setattr(hi, "_build_context", lambda: ("prompt body", [{"kind": "news", "label": "N1", "title": "T", "url": "https://z.com"}]))

    assert hi.generate_and_store_home_insights() is True
    row = db_manager.get_home_insights()
    assert row
    assert "First point" in (row.get("insight_text") or "")


def test_gather_news_queries_tickers_then_general(monkeypatch):
    calls: list[tuple[object, int]] = []

    def fake_list(
        page=1,
        per_page=20,
        category=None,
        ticker=None,
        sort="created",
    ):
        calls.append((ticker, per_page))
        if ticker == "MSFT":
            return (
                [
                    {
                        "url": "https://ex/msft",
                        "title": "MSFT story",
                        "tickers": ["MSFT"],
                        "categories": ["tech"],
                        "summary": "s",
                        "source_feed": "F",
                        "ai_relevance": {"mentioned": ["MSFT"], "relevant": [], "note": ""},
                    }
                ],
                1,
                10,
            )
        if ticker == "AAPL":
            return (
                [
                    {
                        "url": "https://ex/aapl",
                        "title": "AAPL story",
                        "tickers": ["AAPL"],
                        "categories": [],
                        "summary": "s2",
                        "source_feed": "F2",
                    }
                ],
                1,
                10,
            )
        return (
            [
                {
                    "url": "https://ex/general",
                    "title": "General",
                    "tickers": [],
                    "summary": "g",
                    "source_feed": "G",
                }
            ],
            1,
            10,
        )

    gather_limits = {
        "max_news": 4,
        "max_sec": 14,
        "max_news_summary": 480,
        "max_sec_summary": 720,
        "max_prompt_chars": 18000,
        "groq_max_tokens": 1100,
        "portfolio_tickers_max": 2,
        "per_ticker_news": 3,
        "max_source_labels": 40,
    }
    monkeypatch.setattr(hi, "_limits", lambda: gather_limits)
    monkeypatch.setattr(db_manager, "list_news_digest_articles", fake_list)
    monkeypatch.setattr(
        "api.news_digest.portfolio_ticker_universe",
        lambda: ({"AAPL": "Manage Stocks", "MSFT": "Manage Stocks"}, {}),
    )

    rows = hi._gather_news_rows_for_insights()
    assert len(rows) == 3
    urls = [r["url"] for r in rows]
    assert "https://ex/msft" in urls and "https://ex/aapl" in urls
    assert calls[0][0] == "AAPL"
    assert calls[1][0] == "MSFT"
    assert calls[-1][0] is None


def test_build_context_includes_tags_and_ai_line(monkeypatch):
    monkeypatch.setattr(
        hi,
        "_gather_news_rows_for_insights",
        lambda: [
            {
                "url": "https://x/1",
                "title": "Hello",
                "source_feed": "Feed",
                "tickers": ["LMT"],
                "categories": ["defense"],
                "summary": "Body text",
                "first_seen_at_utc": "2026-01-01T12:00:00+00:00",
                "ai_relevance": {
                    "mentioned": ["LMT"],
                    "relevant": [],
                    "note": "Defense sector note.",
                },
            }
        ],
    )
    monkeypatch.setattr(db_manager, "get_sec_summaries", lambda limit: [])
    body, catalog = hi._build_context()
    assert "tickers_matched: LMT" in body
    assert "categories: defense" in body
    assert "ai_mentioned: LMT" in body
    assert "ai_note:" in body
    assert catalog[0].get("tickers") == ["LMT"]
