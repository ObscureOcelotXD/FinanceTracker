"""Tests for auto price backfill when holdings lack quotes."""
import datetime

import pytest

from api import finnhub_api
from services import db_manager


@pytest.fixture
def temp_db(tmp_path):
    db_manager.DATABASE = str(tmp_path / "test_finance_data.db")
    db_manager.init_db()
    return db_manager.DATABASE


def test_update_stock_prices_fetches_missing_even_if_ran_today(temp_db, monkeypatch):
    today = datetime.date.today().isoformat()
    db_manager.replace_all_stocks(
        [
            {"brokerage": "A", "account": "1", "ticker": "NVDA", "shares": 10, "cost_basis": 1},
            {"brokerage": "A", "account": "1", "ticker": "MSFT", "shares": 5, "cost_basis": 1},
        ]
    )
    db_manager.upsert_stock_price("NVDA", today, 100.0)
    db_manager.set_last_update(today)

    fetched = []

    def fake_batch(tickers):
        fetched.extend(list(tickers))
        return {t: 50.0 for t in tickers}

    monkeypatch.setattr(finnhub_api, "fetch_stock_prices_batch", fake_batch)
    monkeypatch.setattr(finnhub_api, "backfill_held_price_history", lambda: 0)

    finnhub_api.update_stock_prices(forceUpdate=False)

    assert fetched == ["MSFT"]
    assert "MSFT" not in db_manager.get_tickers_missing_prices()
    prices = db_manager.get_latest_stock_prices_map(["MSFT", "NVDA"])
    assert prices["MSFT"] == pytest.approx(50.0)
    assert prices["NVDA"] == pytest.approx(100.0)


def test_update_stock_prices_skips_when_all_priced_today(temp_db, monkeypatch):
    today = datetime.date.today().isoformat()
    db_manager.replace_all_stocks(
        [{"brokerage": "A", "account": "1", "ticker": "NVDA", "shares": 10, "cost_basis": 1}]
    )
    db_manager.upsert_stock_price("NVDA", today, 100.0)
    db_manager.set_last_update(today)

    called = {"n": 0}

    def fake_batch(tickers):
        called["n"] += 1
        return {}

    monkeypatch.setattr(finnhub_api, "fetch_stock_prices_batch", fake_batch)
    monkeypatch.setattr(finnhub_api, "backfill_held_price_history", lambda: 0)
    finnhub_api.update_stock_prices(forceUpdate=False)
    assert called["n"] == 0


def test_backfill_held_price_history_inserts_closes(temp_db, monkeypatch):
    db_manager.replace_all_stocks(
        [{"brokerage": "A", "account": "1", "ticker": "MSFT", "shares": 5, "cost_basis": 1}]
    )
    monkeypatch.setenv("PRICE_HISTORY_BACKFILL", "1")
    monkeypatch.setenv("PRICE_HISTORY_BACKFILL_DAYS", "10")
    monkeypatch.setenv("PRICE_HISTORY_MIN_DATES", "5")
    monkeypatch.setenv("PRICE_HISTORY_BACKFILL_FORCE", "1")

    # Two unix midnights UTC-ish
    candles = [
        (1_700_000_000, 100.0),
        (1_700_086_400, 101.5),
        (1_700_172_800, 99.0),
    ]

    monkeypatch.setattr(
        "api.quant_risk.fetch_yahoo_history",
        lambda symbol, start, end: (candles, None),
    )
    monkeypatch.setattr(
        "api.quant_risk.ensure_benchmark_history",
        lambda symbol, start, end: None,
    )

    n = finnhub_api.backfill_held_price_history(force=True)
    assert n["upserted"] == 3
    assert n["skipped"] is False
    df = db_manager.get_stock_prices_df()
    assert len(df[df["ticker"] == "MSFT"]) == 3


def test_backfill_skips_when_enough_dates(temp_db, monkeypatch):
    db_manager.replace_all_stocks(
        [{"brokerage": "A", "account": "1", "ticker": "MSFT", "shares": 5, "cost_basis": 1}]
    )
    today = datetime.date.today()
    for i in range(20):
        day = (today - datetime.timedelta(days=i)).isoformat()
        db_manager.upsert_stock_price("MSFT", day, 100.0 + i)

    monkeypatch.setenv("PRICE_HISTORY_BACKFILL", "1")
    monkeypatch.setenv("PRICE_HISTORY_MIN_DATES", "15")
    monkeypatch.delenv("PRICE_HISTORY_BACKFILL_FORCE", raising=False)

    called = {"n": 0}

    def boom(*args, **kwargs):
        called["n"] += 1
        raise AssertionError("should not fetch")

    monkeypatch.setattr("api.quant_risk.fetch_yahoo_history", boom)
    result = finnhub_api.backfill_held_price_history(force=False)
    assert result["upserted"] == 0
    assert result["skipped"] is True
    assert called["n"] == 0
