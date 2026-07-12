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
    finnhub_api.update_stock_prices(forceUpdate=False)
    assert called["n"] == 0
