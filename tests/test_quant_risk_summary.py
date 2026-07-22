import math
import datetime as dt
import os
import sqlite3

import pandas as pd
import pytest

from services import db_manager


def _init_temp_db(tmp_path):
    db_path = tmp_path / "test_finance_data.db"
    db_manager.DATABASE = str(db_path)
    db_manager.init_db()
    return db_path


def _backdate_open_lots(opened_at="2020-01-01T00:00:00+00:00"):
    """Tests seed historical prices; open lots must start before those dates."""
    conn = sqlite3.connect(db_manager.DATABASE)
    conn.execute(
        "UPDATE Stocks SET opened_at_utc = ? WHERE closed_at_utc IS NULL",
        (opened_at,),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def client(tmp_path, monkeypatch):
    _init_temp_db(tmp_path)
    monkeypatch.setenv("NEWS_DIGEST_DISABLE_SCHEDULER", "1")
    from server import create_flask_app

    app = create_flask_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _seed_prices(ticker, rows):
    for date_str, price in rows:
        db_manager.upsert_stock_price(ticker, date_str, price)


def _seed_benchmark(rows):
    for date_str, price in rows:
        db_manager.upsert_benchmark_price("SPY", date_str, price, source="Test")


def test_quant_risk_summary_empty(client):
    resp = client.get("/quant/risk_summary")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["volatility_pct"] is None
    assert data["max_drawdown_pct"] is None
    assert data["beta"] is None
    assert data["top_sector"] is None
    assert data["hhi"] is None


def test_quant_risk_summary_metrics(monkeypatch, client):
    db_manager.insert_stock("AAPL", 1, cost_basis=100.0)
    db_manager.insert_stock("MSFT", 1, cost_basis=100.0)
    _backdate_open_lots()

    _seed_prices(
        "AAPL",
        [
            ("2026-01-01", 100.0),
            ("2026-01-02", 90.0),
            ("2026-01-03", 110.0),
        ],
    )
    _seed_prices(
        "MSFT",
        [
            ("2026-01-01", 100.0),
            ("2026-01-02", 100.0),
            ("2026-01-03", 100.0),
        ],
    )
    _seed_benchmark(
        [
            ("2026-01-01", 100.0),
            ("2026-01-02", 102.0),
            ("2026-01-03", 101.0),
        ],
    )

    from api import finnhub_api, etf_breakdown

    monkeypatch.setattr(
        finnhub_api,
        "get_sector_allocation_map",
        lambda tickers: {ticker: ("Tech" if ticker == "AAPL" else "Health") for ticker in tickers},
    )
    monkeypatch.setattr(etf_breakdown, "is_tracked_etf", lambda _: False)

    resp = client.get("/quant/risk_summary")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["top_sector"] in {"Tech", "Health"}
    assert data["top_sector_pct"] == 52.38
    assert data["hhi"] == 0.5011
    assert data["max_drawdown_pct"] == -5.0
    assert data["beta"] is None
    assert data["last_updated"] == "2026-01-03"


def _compute_diversification_ratio(price_rows, weights, dates):
    df = pd.DataFrame(price_rows, columns=["ticker", "date", "price"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["ticker", "date"])
    df["returns"] = df.groupby("ticker")["price"].pct_change()
    vol_by_ticker = df.groupby("ticker")["returns"].std() * math.sqrt(252)
    vol_by_ticker = vol_by_ticker.dropna()
    aligned = vol_by_ticker.to_frame("vol").join(weights.to_frame("weight"), how="inner")
    weighted_avg_vol = float((aligned["vol"] * aligned["weight"]).sum())

    portfolio = pd.DataFrame(dates, columns=["date", "portfolio_value"])
    portfolio["returns"] = portfolio["portfolio_value"].pct_change()
    volatility_raw = portfolio["returns"].dropna().std() * math.sqrt(252)
    return float(volatility_raw / weighted_avg_vol)


def test_quant_risk_summary_diversification_ratio(monkeypatch, client):
    db_manager.insert_stock("AAPL", 1, cost_basis=100.0)
    db_manager.insert_stock("MSFT", 1, cost_basis=100.0)
    _backdate_open_lots()

    aapl_prices = [
        ("2026-01-01", 100.0),
        ("2026-01-02", 90.0),
        ("2026-01-03", 110.0),
    ]
    msft_prices = [
        ("2026-01-01", 100.0),
        ("2026-01-02", 100.0),
        ("2026-01-03", 100.0),
    ]
    _seed_prices("AAPL", aapl_prices)
    _seed_prices("MSFT", msft_prices)
    _seed_benchmark(
        [
            ("2026-01-01", 100.0),
            ("2026-01-02", 102.0),
            ("2026-01-03", 101.0),
        ],
    )

    from api import finnhub_api, etf_breakdown

    monkeypatch.setattr(
        finnhub_api,
        "get_sector_allocation_map",
        lambda tickers: {ticker: ("Tech" if ticker == "AAPL" else "Health") for ticker in tickers},
    )
    monkeypatch.setattr(etf_breakdown, "is_tracked_etf", lambda _: False)

    total_value = 110.0 + 100.0
    weights = pd.Series({"AAPL": 110.0 / total_value, "MSFT": 100.0 / total_value})
    price_rows = [
        ("AAPL", *row) for row in aapl_prices
    ] + [
        ("MSFT", *row) for row in msft_prices
    ]
    portfolio_dates = [
        ("2026-01-01", 200.0),
        ("2026-01-02", 190.0),
        ("2026-01-03", 210.0),
    ]
    expected_ratio = _compute_diversification_ratio(price_rows, weights, portfolio_dates)

    resp = client.get("/quant/risk_summary")
    data = resp.get_json()
    assert data["diversification_ratio"] == round(expected_ratio, 2)


def test_quant_risk_summary_fresh_flags(monkeypatch, client):
    db_manager.insert_stock("AAPL", 1, cost_basis=100.0)
    _backdate_open_lots()
    _seed_prices(
        "AAPL",
        [
            ("2026-01-01", 100.0),
            ("2026-01-02", 101.0),
        ],
    )
    _seed_benchmark(
        [
            ("2026-01-01", 100.0),
            ("2026-01-02", 101.0),
        ],
    )

    import api.quant_risk as quant_risk

    class FixedDateTime(dt.datetime):
        @classmethod
        def utcnow(cls):
            return cls(2026, 1, 5)

        @classmethod
        def now(cls, tz=None):
            return cls(2026, 1, 5, tzinfo=tz)

    monkeypatch.setattr(quant_risk.dt, "datetime", FixedDateTime)

    resp = client.get("/quant/risk_summary")
    data = resp.get_json()
    assert data["last_updated"] == "2026-01-02"
    assert data["fresh"] is True
