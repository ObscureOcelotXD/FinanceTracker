"""Tests for RSS news digest POC (mocked HTTP)."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import api.news_digest as nd
import db_manager


SAMPLE_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Test</title>
<item><title>Headline A</title><link>https://example.com/a</link></item>
<item><title>Headline B</title><link>https://example.com/b</link></item>
</channel></rss>
"""


def test_collect_digest_dedupes_by_link(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, **kwargs):
        calls["n"] += 1
        r = MagicMock()
        r.raise_for_status = lambda: None
        r.content = SAMPLE_RSS
        return r

    monkeypatch.setattr(nd.requests, "get", fake_get)

    digest = nd.collect_digest(
        feeds=[("TestSrc", "http://fake/1"), ("TestSrc2", "http://fake/2")],
        max_items=10,
    )
    assert digest["item_count"] == 2
    assert len(digest["items"]) == 2
    titles = {x["title"] for x in digest["items"]}
    assert titles == {"Headline A", "Headline B"}


def test_write_outputs_creates_files(tmp_path):
    digest = {
        "generated_at_utc": "2026-01-01T12:00:00+00:00",
        "feed_count": 1,
        "item_count": 1,
        "errors": [],
        "items": [{"title": "T", "link": "https://x.com", "published_raw": "", "source_feed": "S", "feed_url": "u"}],
    }
    jp, mp = nd.write_outputs(digest, out_dir=tmp_path)
    assert jp.exists() and mp.exists()
    data = json.loads(jp.read_text(encoding="utf-8"))
    assert data["item_count"] == 1
    assert "Headlines" in mp.read_text(encoding="utf-8")


def test_strip_html_removes_tags():
    raw = "<p>Hello <b>World</b> &amp; Co.</p>"
    assert nd._strip_html(raw) == "Hello World & Co."


def test_match_tickers_from_universe_explicit_patterns():
    u = {
        "AAPL": "Apple Inc.",
        "MSFT": "Microsoft Corporation",
        "NVDA": "NVIDIA Corporation",
    }
    text = "Shares of $AAPL and (MSFT) rise; NASDAQ: NVDA also up"
    syms, comps = nd.match_tickers_from_universe(text, u)
    assert syms == ["AAPL", "MSFT", "NVDA"]
    assert comps["MSFT"] == "Microsoft Corporation"


def test_match_tickers_only_if_symbol_in_universe():
    text = "THE CEO AND CFO AT ETF TALK IPO"
    syms, _ = nd.match_tickers_from_universe(text, {"ZZZZZ": "Fake Corp."})
    assert syms == []


def test_match_tickers_bare_word_requires_universe_entry():
    u = {"IBM": "International Business Machines Corp."}
    syms, _ = nd.match_tickers_from_universe("IBM announces new chip", u)
    assert syms == ["IBM"]


def test_match_tickers_symbol_in_rss_body_not_title():
    """Symbols often appear in feed body text while the headline uses company names only."""
    u = {"LMT": "Manage Stocks"}
    text = "Pentagon Taps Boeing, Lockheed To Triple Output. LMT shares moved higher."
    syms, _ = nd.match_tickers_from_universe(text, u)
    assert syms == ["LMT"]


def test_rss_entry_combined_plain_text_includes_atom_content():
    entry = {
        "title": "Defense headline",
        "summary": "Short blurb.",
        "content": [{"type": "text/html", "value": "<p>Watch LMT and BA in regular trading.</p>"}],
    }
    combined = nd._rss_entry_combined_plain_text(entry)
    assert "LMT" in combined and "BA" in combined


def test_fill_snippets_prioritizes_priority_urls_before_others(monkeypatch):
    """DB-null-summary URLs are fetched first when passed as priority_urls."""
    import db_manager as dm

    calls: list[str] = []

    def fake_fetch(url: str) -> str:
        calls.append(url)
        return "ok"

    monkeypatch.setattr(nd, "_fetch_article_snippet_from_url", fake_fetch)
    monkeypatch.setenv("NEWS_DIGEST_FETCH_ARTICLE_SNIPPET", "1")
    first = {"title": "a", "link": "https://example.com/first", "summary_text": ""}
    second = {"title": "b", "link": "https://example.com/second", "summary_text": ""}
    pri = {dm.canonical_news_article_url(second)}
    nd._fill_article_snippets_for_items([first, second], 10, priority_urls=pri)
    assert calls[0] == second["link"]


def test_fetch_article_snippet_reads_og_description(monkeypatch):
    html = (
        "<html><head>"
        '<meta property="og:description" content="LMT shares moved on Pentagon news." />'
        "</head><body></body></html>"
    )
    mock_r = MagicMock()
    mock_r.raise_for_status = lambda: None
    mock_r.text = html

    def fake_get(url, **kwargs):
        return mock_r

    monkeypatch.setattr(nd.requests, "get", fake_get)
    monkeypatch.setenv("NEWS_DIGEST_FETCH_ARTICLE_SNIPPET", "1")
    out = nd._fetch_article_snippet_from_url("https://finance.yahoo.com/markets/stocks/articles/x.html")
    assert "LMT" in out


def test_yahoo_style_rss_entry_gets_summary_via_fetch(monkeypatch):
    """Yahoo top-news RSS often has no description in XML; digest fills snippet after merge."""
    rss_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><title>Yahoo</title>
    <item><title>Pentagon Taps Boeing, Lockheed</title>
    <link>https://finance.yahoo.com/markets/stocks/articles/pentagon-220254992.html</link>
    </item></channel></rss>"""
    html = (
        "<html><head>"
        '<meta property="og:description" content="Technical view: LMT above the 20-day SMA." />'
        "</head></html>"
    )

    def fake_get(url, **kwargs):
        r = MagicMock()
        r.raise_for_status = lambda: None
        if "fake-feed" in str(url):
            r.content = rss_xml
        else:
            r.text = html
        return r

    monkeypatch.setattr(nd.requests, "get", fake_get)
    monkeypatch.setenv("NEWS_DIGEST_FETCH_ARTICLE_SNIPPET", "1")
    items, err = nd._fetch_and_parse_feed("Yahoo", "http://fake-feed/rss")
    assert err is None
    assert len(items) == 1
    assert not items[0].get("summary_text", "").strip()
    nd._fill_article_snippets_for_items(items, 5)
    assert "LMT" in items[0]["summary_text"]


def test_enrich_news_item_tags_lmt_from_summary_body(monkeypatch):
    monkeypatch.setattr(db_manager, "get_held_stock_tickers", lambda: ["LMT"])
    monkeypatch.setattr(db_manager, "get_plaid_holdings_tickers", lambda: [])
    item = {
        "title": "Pentagon Taps Boeing, Lockheed To Triple Output",
        "summary_text": "Coverage notes LMT among defense names.",
        "link": "https://example.com/a",
        "published_raw": "",
        "source_feed": "Test",
        "feed_url": "http://fake",
    }
    nd.enrich_news_item(item)
    assert item["tickers"] == ["LMT"]


def test_portfolio_ticker_universe_marks_manual_plaid_or_both(monkeypatch):
    monkeypatch.setattr(db_manager, "get_held_stock_tickers", lambda: ["MSFT", "AAPL"])
    monkeypatch.setattr(db_manager, "get_plaid_holdings_tickers", lambda: ["MSFT", "GOOG"])
    uni, stats = nd.portfolio_ticker_universe()
    assert stats["manual_distinct"] == 2
    assert stats["plaid_distinct"] == 2
    assert stats["unique_for_matching"] == 3
    assert uni["MSFT"] == "Manage Stocks & Plaid"
    assert uni["AAPL"] == "Manage Stocks"
    assert uni["GOOG"] == "Plaid-linked"


def test_infer_categories_detects_multiple():
    tl = "Federal Reserve signals interest rate cut; stocks rally on Nasdaq"
    cats = nd._infer_categories(tl)
    assert "rates" in cats
    assert "markets" in cats


def test_infer_categories_defaults_to_general():
    assert nd._infer_categories("Local weather forecast for the weekend") == ["general"]


def test_enrich_news_item_adds_categories(monkeypatch):
    monkeypatch.setattr(db_manager, "get_held_stock_tickers", lambda: [])
    monkeypatch.setattr(db_manager, "get_plaid_holdings_tickers", lambda: [])
    item = {
        "title": "Q4 earnings beat for JPMorgan as profit rises",
        "summary_text": "Shares traded higher on the NYSE.",
        "link": "https://example.com/x",
        "published_raw": "",
        "source_feed": "Test",
        "feed_url": "http://fake",
    }
    nd.enrich_news_item(item)
    assert "earnings" in item["categories"]
    assert "banking" in item["categories"]
    assert "markets" in item["categories"]
    assert item["tickers"] == []
    assert item["ticker_companies"] == {}


def test_enrich_news_item_tags_tickers_from_holdings(monkeypatch):
    monkeypatch.setattr(db_manager, "get_held_stock_tickers", lambda: ["MSFT"])
    monkeypatch.setattr(db_manager, "get_plaid_holdings_tickers", lambda: [])
    item = {
        "title": "MSFT cloud revenue beats estimates",
        "summary_text": "",
        "link": "https://example.com/x",
        "published_raw": "",
        "source_feed": "Test",
        "feed_url": "http://fake",
    }
    nd.enrich_news_item(item)
    assert item["tickers"] == ["MSFT"]
    assert item["ticker_companies"] == {"MSFT": "Manage Stocks"}


def test_digest_fresh_for_today_matches_local_date(tmp_path, monkeypatch):
    monkeypatch.setattr(nd, "OUTPUT_DIR", tmp_path)
    now_utc = datetime.now(timezone.utc).isoformat()
    nd.write_outputs(
        {
            "generated_at_utc": now_utc,
            "feed_count": 0,
            "item_count": 0,
            "errors": [],
            "items": [],
        },
        out_dir=tmp_path,
    )
    assert nd.digest_fresh_for_today() is True

    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    nd.write_outputs(
        {
            "generated_at_utc": yesterday,
            "feed_count": 0,
            "item_count": 0,
            "errors": [],
            "items": [],
        },
        out_dir=tmp_path,
    )
    assert nd.digest_fresh_for_today() is False


def test_retag_stored_articles_applies_holdings_after_story_stored(tmp_path, monkeypatch):
    """Rows not in the current RSS batch still get ticker badges after holdings change + retag."""
    db_path = tmp_path / "test_finance_data.db"
    db_manager.DATABASE = str(db_path)
    db_manager.init_db()
    monkeypatch.setenv("NEWS_DIGEST_TZ", "America/New_York")
    first = "2026-06-15T12:00:00+00:00"
    conn = sqlite3.connect(db_manager.DATABASE)
    conn.execute(
        """
        INSERT INTO news_digest_articles (
            url, title, source_feed, categories_json, tickers_json, ticker_companies_json,
            first_seen_at_utc, last_seen_at_utc, summary
        ) VALUES (?, ?, ?, '[]', '[]', '{}', ?, ?, NULL)
        """,
        ("https://example.com/lmt", "LMT raises outlook", "Test", first, first),
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(db_manager, "get_held_stock_tickers", lambda: [])
    monkeypatch.setattr(db_manager, "get_plaid_holdings_tickers", lambda: [])
    assert nd.retag_stored_articles_for_local_date("2026-06-15") == 1
    rows = db_manager.list_news_digest_articles_for_local_date("2026-06-15")
    assert rows[0]["tickers"] == []
    monkeypatch.setattr(db_manager, "get_held_stock_tickers", lambda: ["LMT"])
    monkeypatch.setattr(db_manager, "get_plaid_holdings_tickers", lambda: [])
    assert nd.retag_stored_articles_for_local_date("2026-06-15") == 1
    rows2 = db_manager.list_news_digest_articles_for_local_date("2026-06-15")
    assert rows2[0]["tickers"] == ["LMT"]
    assert rows2[0]["ticker_companies"]["LMT"] == "Manage Stocks"


def test_retag_finds_ticker_in_stored_summary(tmp_path, monkeypatch):
    """Title says 'Lockheed' but stored summary has 'LMT' — retag should tag it."""
    db_path = tmp_path / "test_finance_data.db"
    db_manager.DATABASE = str(db_path)
    db_manager.init_db()
    monkeypatch.setenv("NEWS_DIGEST_TZ", "America/New_York")
    first = "2026-06-15T12:00:00+00:00"
    conn = sqlite3.connect(db_manager.DATABASE)
    conn.execute(
        """
        INSERT INTO news_digest_articles (
            url, title, source_feed, categories_json, tickers_json, ticker_companies_json,
            first_seen_at_utc, last_seen_at_utc, summary
        ) VALUES (?, ?, ?, '[]', '[]', '{}', ?, ?, ?)
        """,
        (
            "https://example.com/pentagon",
            "Pentagon Taps Boeing, Lockheed To Triple Output",
            "Yahoo",
            first,
            first,
            "LMT shares moved higher. BA also up on the news.",
        ),
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(db_manager, "get_held_stock_tickers", lambda: ["LMT"])
    monkeypatch.setattr(db_manager, "get_plaid_holdings_tickers", lambda: [])
    nd.retag_stored_articles_for_local_date("2026-06-15")
    rows = db_manager.list_news_digest_articles_for_local_date("2026-06-15")
    assert rows[0]["tickers"] == ["LMT"]


def test_upsert_persists_summary_text(tmp_path):
    """summary_text from the digest item should be stored in the DB summary column."""
    db_path = tmp_path / "test_finance_data.db"
    db_manager.DATABASE = str(db_path)
    db_manager.init_db()
    digest = {
        "generated_at_utc": "2026-06-15T12:00:00+00:00",
        "items": [
            {
                "title": "Pentagon headline",
                "link": "https://example.com/pent",
                "source_feed": "Yahoo",
                "categories": [],
                "tickers": [],
                "ticker_companies": {},
                "summary_text": "LMT and BA shares up on defense news.",
            },
        ],
    }
    db_manager.upsert_news_digest_articles_from_digest(digest)
    rows, total, _ = db_manager.list_news_digest_articles(page=1, per_page=10)
    assert total == 1
    assert rows[0]["summary"] == "LMT and BA shares up on defense news."


def test_backfill_null_summaries_fetches_for_db_only_rows(tmp_path, monkeypatch):
    """
    Articles in the DB with NULL summary but NOT in the current digest
    should still get their snippet fetched by the backfill pass.
    """
    db_path = tmp_path / "test_finance_data.db"
    db_manager.DATABASE = str(db_path)
    db_manager.init_db()
    monkeypatch.setenv("NEWS_DIGEST_FETCH_ARTICLE_SNIPPET", "1")
    monkeypatch.setenv("NEWS_DIGEST_MAX_ARTICLE_SNIPPET_FETCHES", "10")

    now_utc = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_manager.DATABASE)
    conn.execute(
        """INSERT INTO news_digest_articles
        (url, title, source_feed, categories_json, tickers_json, ticker_companies_json,
         first_seen_at_utc, last_seen_at_utc, summary)
        VALUES (?, ?, ?, '[]', '[]', '{}', ?, ?, NULL)""",
        ("https://example.com/backfill-me", "Backfill Article", "Test", now_utc, now_utc),
    )
    conn.execute(
        """INSERT INTO news_digest_articles
        (url, title, source_feed, categories_json, tickers_json, ticker_companies_json,
         first_seen_at_utc, last_seen_at_utc, summary)
        VALUES (?, ?, ?, '[]', '[]', '{}', ?, ?, 'already present')""",
        ("https://example.com/skip-me", "Already Filled", "Test", now_utc, now_utc),
    )
    conn.commit()
    conn.close()

    fetched_urls = []
    def fake_fetch(url):
        fetched_urls.append(url)
        return f"Snippet for {url}"

    monkeypatch.setattr(nd, "_fetch_article_snippet_from_url", fake_fetch)
    filled = nd._backfill_null_summaries_after_digest(budget=10)

    assert filled == 1
    assert "https://example.com/backfill-me" in fetched_urls
    assert "https://example.com/skip-me" not in fetched_urls

    rows, _, _ = db_manager.list_news_digest_articles(page=1, per_page=10)
    backfill_row = [r for r in rows if r["url"] == "https://example.com/backfill-me"][0]
    assert backfill_row["summary"] == "Snippet for https://example.com/backfill-me"
