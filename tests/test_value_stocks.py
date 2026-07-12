"""Tests for value stocks / missing price helpers."""
import pytest

from services import db_manager


@pytest.fixture
def temp_db(tmp_path):
    db_manager.DATABASE = str(tmp_path / "test_finance_data.db")
    db_manager.init_db()
    return db_manager.DATABASE


def test_get_value_stocks_includes_unpriced_tickers(temp_db):
    db_manager.replace_all_stocks(
        [
            {"brokerage": "A", "account": "1", "ticker": "NVDA", "shares": 10, "cost_basis": 1000},
            {"brokerage": "A", "account": "1", "ticker": "MSFT", "shares": 5, "cost_basis": 500},
        ]
    )
    db_manager.upsert_stock_price("NVDA", "2026-07-11", 100.0)

    missing = db_manager.get_tickers_missing_prices()
    assert missing == ["MSFT"]

    df = db_manager.get_value_stocks()
    tickers = set(df["ticker"].tolist())
    assert tickers == {"NVDA", "MSFT"}
    nvda = df[df["ticker"] == "NVDA"].iloc[0]
    msft = df[df["ticker"] == "MSFT"].iloc[0]
    assert float(nvda["position_value"]) == pytest.approx(1000.0)
    # Falls back to cost basis when no quote
    assert float(msft["position_value"]) == pytest.approx(500.0)


def test_get_all_tickers_is_distinct(temp_db):
    db_manager.replace_all_stocks(
        [
            {"brokerage": "A", "account": "1", "ticker": "NVDA", "shares": 10, "cost_basis": 1},
            {"brokerage": "B", "account": "2", "ticker": "NVDA", "shares": 20, "cost_basis": 2},
        ]
    )
    assert db_manager.get_all_tickers() == ["NVDA"]
