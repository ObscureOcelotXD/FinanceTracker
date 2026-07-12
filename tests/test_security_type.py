"""Tests for security type classification and UI hide toggles."""
import pandas as pd
import pytest

from api import security_type as st
from services import db_manager


@pytest.fixture
def temp_db(tmp_path):
    db_manager.DATABASE = str(tmp_path / "test_finance_data.db")
    db_manager.init_db()
    return db_manager.DATABASE


def test_heuristic_mutual_fund_and_known_etf(temp_db, monkeypatch):
    # Avoid network during classification
    monkeypatch.setattr(st, "_from_polygon", lambda _t: None)
    monkeypatch.setattr(st, "_from_finnhub", lambda _t: None)
    monkeypatch.setattr(st, "_from_etf_source_registry", lambda _t: None)

    assert st.classify_ticker("FXAIX") == "mutual_fund"
    assert st.classify_ticker("DFIEX") == "mutual_fund"
    assert st.classify_ticker("VTI") == "etf"
    assert st.classify_ticker("AAPL") == "stock"
    assert db_manager.get_security_type("FXAIX") == "mutual_fund"


def test_filter_holdings_df_respects_toggles(temp_db, monkeypatch):
    monkeypatch.setattr(st, "_from_polygon", lambda _t: None)
    monkeypatch.setattr(st, "_from_finnhub", lambda _t: None)
    monkeypatch.setattr(st, "_from_etf_source_registry", lambda _t: None)

    df = pd.DataFrame(
        {
            "ticker": ["AAPL", "VTI", "FXAIX"],
            "shares": [10, 20, 30],
        }
    )
    db_manager.set_hide_mutual_funds(False)
    db_manager.set_hide_etfs(False)
    assert len(st.filter_holdings_df_for_ui(df)) == 3

    db_manager.set_hide_mutual_funds(True)
    out = st.filter_holdings_df_for_ui(df)
    assert set(out["ticker"]) == {"AAPL", "VTI"}

    db_manager.set_hide_etfs(True)
    out2 = st.filter_holdings_df_for_ui(df)
    assert set(out2["ticker"]) == {"AAPL"}


def test_registry_url_distinguishes_mutual_fund(temp_db, monkeypatch):
    monkeypatch.setattr(st, "_from_polygon", lambda _t: None)
    monkeypatch.setattr(st, "_from_finnhub", lambda _t: None)
    # Force classify via registry (skip heuristic by using a non-X ticker)
    db_manager.upsert_etf_source(
        "FOO",
        "schwab_portfolio",
        url="https://example.com/mutualfunds/portfolio.asp?symbol=FOO",
    )
    assert st.classify_ticker("FOO", force_refresh=True) == "mutual_fund"

    db_manager.upsert_etf_source(
        "BAR",
        "schwab_portfolio",
        url="https://example.com/etfs/portfolio.asp?symbol=BAR",
    )
    assert st.classify_ticker("BAR", force_refresh=True) == "etf"
