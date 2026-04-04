"""Tests for RSS news digest POC (mocked HTTP)."""

import json
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
