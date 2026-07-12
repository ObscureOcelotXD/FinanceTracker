"""Tests for covered call holdings and metrics."""
from datetime import date

import pytest

from api import covered_calls as cc_api
from services import db_manager


@pytest.fixture
def temp_db(tmp_path):
    db_manager.DATABASE = str(tmp_path / "test_finance_data.db")
    db_manager.init_db()
    return db_manager.DATABASE


def test_coverable_holdings_respect_hide_toggles(temp_db, monkeypatch):
    from api import security_type as st

    monkeypatch.setattr(st, "_from_polygon", lambda _t: None)
    monkeypatch.setattr(st, "_from_finnhub", lambda _t: None)
    monkeypatch.setattr(st, "_from_etf_source_registry", lambda _t: None)

    db_manager.replace_all_stocks(
        [
            {"brokerage": "A", "account": "1", "ticker": "AAPL", "shares": 200, "cost_basis": 1},
            {"brokerage": "A", "account": "1", "ticker": "VTI", "shares": 200, "cost_basis": 1},
            {"brokerage": "A", "account": "1", "ticker": "FXAIX", "shares": 200, "cost_basis": 1},
        ]
    )
    db_manager.set_hide_etfs(True)
    db_manager.set_hide_mutual_funds(True)
    rows = cc_api.get_coverable_holdings_records()
    tickers = {r["ticker"] for r in rows}
    assert tickers == {"AAPL"}


def test_covered_calls_layout_has_privacy_markers():
    import os

    os.environ.setdefault("NEWS_DIGEST_DISABLE_SCHEDULER", "1")
    # App must exist before page module calls get_app().
    import dashApp  # noqa: F401
    import dashPages.stocks_covered_calls as page

    rendered = str(page.layout)
    assert "privacy-sensitive-visual" in rendered
    assert rendered.count("privacy-sensitive-visual") >= 3


def test_coverable_holdings_manual_and_plaid(temp_db, monkeypatch):
    db_manager.set_hide_plaid(False)
    db_manager.insert_stock("AAPL", 250, cost_basis=10000)
    db_manager.insert_stock("MSFT", 50, cost_basis=2000)

    plaid_df = __import__("pandas").DataFrame(
        [
            {
                "account_id": "acc-1",
                "account_name": "Brokerage IRA",
                "institution_name": "Schwab",
                "ticker": "NVDA",
                "shares": 150.0,
                "cost_basis": 5000.0,
                "latest_price": 120.0,
                "position_value": 18000.0,
                "gain_loss": 13000.0,
                "gain_loss_pct": 2.6,
            }
        ]
    )
    monkeypatch.setattr(db_manager, "get_plaid_holdings", lambda institution_name=None: plaid_df)

    rows = cc_api.get_coverable_holdings_records()
    tickers = {(r["brokerage"], r["account"], r["ticker"]) for r in rows}
    assert ("Manual", "Manage Stocks", "AAPL") in tickers
    assert ("Schwab", "Brokerage IRA", "NVDA") in tickers
    assert all(r["coverable_lots"] >= 1 for r in rows)
    assert ("Manual", "Manage Stocks", "MSFT") not in tickers


def test_compute_metrics_otm_and_assignment_warning():
    metrics = cc_api.compute_covered_call_metrics(
        strike=110.0,
        expiration_date="2026-08-15",
        contracts=2,
        premium_received=250.0,
        current_price=100.0,
        as_of=date(2026, 7, 11),
    )
    assert metrics["days_to_expiration"] == 35
    assert metrics["shares_at_risk"] == 200
    assert metrics["otm_itm_pct"] == pytest.approx(10.0)
    assert metrics["moneyness_label"].endswith("OTM")
    assert metrics["premium_yield_pct"] == pytest.approx(250.0 / (110.0 * 200) * 100.0)
    assert metrics["assignment_warning"] is False

    itm = cc_api.compute_covered_call_metrics(
        strike=100.0,
        expiration_date="2026-08-15",
        contracts=1,
        premium_received=100.0,
        current_price=102.0,
        as_of=date(2026, 7, 11),
    )
    assert itm["assignment_warning"] is True
    assert itm["assignment_reason"] == "In the money"

    near = cc_api.compute_covered_call_metrics(
        strike=100.0,
        expiration_date="2026-08-15",
        contracts=1,
        premium_received=100.0,
        current_price=99.0,
        as_of=date(2026, 7, 11),
        near_pct=2.0,
    )
    assert near["assignment_warning"] is True
    assert "Within" in (near["assignment_reason"] or "")


def test_open_calls_enriched_and_calendar(temp_db):
    db_manager.insert_covered_call(
        ticker="aapl",
        strike=200.0,
        expiration_date="2026-07-18",
        contracts=1,
        premium_received=150.0,
        open_date="2026-06-01",
    )
    db_manager.insert_covered_call(
        ticker="msft",
        strike=450.0,
        expiration_date="2026-08-15",
        contracts=2,
        premium_received=400.0,
    )
    db_manager.upsert_stock_price("AAPL", "2026-07-10", 195.0)
    db_manager.upsert_stock_price("MSFT", "2026-07-10", 460.0)

    rows = cc_api.get_open_covered_calls_enriched(as_of=date(2026, 7, 11))
    assert len(rows) == 2
    aapl = next(r for r in rows if r["ticker"] == "AAPL")
    msft = next(r for r in rows if r["ticker"] == "MSFT")
    assert aapl["current_price"] == 195.0
    assert aapl["assignment_warning"] is False
    assert msft["assignment_warning"] is True

    calendar = cc_api.build_expiration_calendar(rows)
    assert len(calendar) == 2
    assert calendar[0]["expiration_date"] == "2026-07-18"
    assert len(calendar[0]["items"]) == 1


def test_insert_stock_helper_exists(temp_db):
    db_manager.insert_stock("TSLA", 100, cost_basis=5000)
    df = db_manager.get_stocks()
    assert not df.empty
    assert df.iloc[0]["ticker"] == "TSLA"
