"""Tests for CSV / XLSX portfolio import."""
import base64
import io

import pandas as pd
import pytest

from api import portfolio_import as pi
from services import db_manager


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_manager.DATABASE = str(tmp_path / "test_finance_data.db")
    db_manager.init_db()
    monkeypatch.setattr(pi, "_refresh_prices_after_holdings_change", lambda: None)
    return db_manager.DATABASE


def _upload_payload(text: str, filename: str = "file.csv"):
    raw = base64.b64encode(text.encode("utf-8")).decode("ascii")
    contents = f"data:text/csv;base64,{raw}"
    return contents, filename


def test_parse_and_replace_holdings_csv(temp_db):
    db_manager.insert_stock("OLD", 10, cost_basis=1)
    csv = (
        "brokerage,account,ticker,shares,cost_basis\n"
        "Schwab,IRA,AAPL,250,42000\n"
        "Schwab,IRA,MSFT,100,35000\n"
    )
    contents, name = _upload_payload(csv, "holdings.csv")
    result = pi.apply_holdings_upload(contents, name)
    assert result["ok"] is True
    assert result["count"] == 2
    df = db_manager.get_stocks()
    assert len(df) == 2
    assert set(df["ticker"]) == {"AAPL", "MSFT"}
    assert "OLD" not in set(df["ticker"])
    aapl = df[df["ticker"] == "AAPL"].iloc[0]
    assert aapl["brokerage"] == "Schwab"
    assert aapl["account"] == "IRA"
    assert float(aapl["shares"]) == 250


def test_holdings_duplicate_key_rejected(temp_db):
    csv = (
        "brokerage,account,ticker,shares,cost_basis\n"
        "Schwab,IRA,AAPL,100,1\n"
        "Schwab,IRA,AAPL,200,2\n"
    )
    contents, name = _upload_payload(csv)
    result = pi.apply_holdings_upload(contents, name)
    assert result["ok"] is False
    assert any("duplicate" in e.lower() for e in result["errors"])


def test_same_ticker_different_accounts_allowed(temp_db):
    csv = (
        "brokerage,account,ticker,shares,cost_basis\n"
        "Schwab,IRA,AAPL,100,1\n"
        "Fidelity,Taxable,AAPL,50,2\n"
    )
    contents, name = _upload_payload(csv)
    result = pi.apply_holdings_upload(contents, name)
    assert result["ok"] is True
    assert result["count"] == 2
    coverable = db_manager.get_coverable_holdings_by_account()
    assert len(coverable) == 1  # only IRA has 100
    assert coverable.iloc[0]["account"] == "IRA"


def test_replace_covered_calls_csv(temp_db):
    db_manager.insert_covered_call(
        ticker="ZZZ",
        strike=10,
        expiration_date="2026-12-01",
        contracts=1,
        premium_received=1,
    )
    csv = (
        "ticker,strike,expiration_date,contracts,premium_received,open_date,status,notes\n"
        "AAPL,220,2026-08-15,2,450,2026-07-01,open,Aug\n"
    )
    contents, name = _upload_payload(csv, "calls.csv")
    result = pi.apply_covered_calls_upload(contents, name)
    assert result["ok"] is True
    assert result["count"] == 1
    df = db_manager.get_covered_calls()
    assert len(df) == 1
    assert df.iloc[0]["ticker"] == "AAPL"


def test_xlsx_workbook_both_sheets(temp_db):
    holdings = pd.DataFrame(
        [
            {
                "brokerage": "Schwab",
                "account": "IRA",
                "ticker": "NVDA",
                "shares": 150,
                "cost_basis": 10000,
            }
        ]
    )
    calls = pd.DataFrame(
        [
            {
                "ticker": "NVDA",
                "strike": 140,
                "expiration_date": "2026-09-19",
                "contracts": 1,
                "premium_received": 200,
                "open_date": "2026-07-01",
                "status": "open",
                "notes": "",
            }
        ]
    )
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        holdings.to_excel(writer, sheet_name="Holdings", index=False)
        calls.to_excel(writer, sheet_name="Covered Calls", index=False)
    raw = base64.b64encode(buf.getvalue()).decode("ascii")
    contents = f"data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{raw}"
    result = pi.apply_workbook_upload(contents, "portfolio.xlsx")
    assert result["holdings"]["ok"] is True
    assert result["covered_calls"]["ok"] is True
    assert len(db_manager.get_stocks()) == 1
    assert len(db_manager.get_covered_calls()) == 1


def test_auto_detect_holdings_csv(temp_db):
    csv = "brokerage,account,ticker,shares,cost_basis\nSchwab,IRA,AAPL,100,1\n"
    contents, name = _upload_payload(csv, "whatever.csv")
    result = pi.apply_auto_upload(contents, name)
    assert result["detected"] == ["holdings"]
    assert result["holdings"]["ok"] is True
    assert result["covered_calls"] is None
    assert len(db_manager.get_stocks()) == 1


def test_auto_detect_covered_calls_csv(temp_db):
    csv = (
        "ticker,strike,expiration_date,contracts,premium_received\n"
        "AAPL,220,2026-08-15,1,50\n"
    )
    contents, name = _upload_payload(csv, "mystery.csv")
    result = pi.apply_auto_upload(contents, name)
    assert result["detected"] == ["covered_calls"]
    assert result["covered_calls"]["ok"] is True
    assert result["holdings"] is None
    assert len(db_manager.get_covered_calls()) == 1


def test_auto_detect_unknown_columns(temp_db):
    csv = "foo,bar\n1,2\n"
    contents, name = _upload_payload(csv, "bad.csv")
    result = pi.apply_auto_upload(contents, name)
    assert result.get("errors")
    assert result["detected"] == []


def test_parse_option_symbol_verbose_and_occ():
    verbose = pi.parse_option_symbol("SOFI 09/18/2026 24.00 C")
    assert verbose["ticker"] == "SOFI"
    assert verbose["expiration_date"] == "2026-09-18"
    assert verbose["strike"] == 24.0
    assert verbose["right"] == "C"

    occ = pi.parse_option_symbol("-NVDA260828C260")
    assert occ["ticker"] == "NVDA"
    assert occ["expiration_date"] == "2026-08-28"
    assert occ["strike"] == 260.0
    assert occ["right"] == "C"
    assert occ["short_marker"] is True


def test_mixed_portfolio_user_dummy_formats(temp_db):
    csv = (
        "brokerage,account,ticker,shares,market_value\n"
        "Schwab,Individual,SOFI 09/18/2026 24.00 C,-2,-$88.67\n"
        "Fidelity,Rollover IRA,-NVDA260828C260,-1,$167.34\n"
        "SOFI,Individual,NVDA,100,17510\n"
        'Schwab,Individual,SOFI,544,"$10,169.21"\n'
        "Fidelity,Rollover IRA,NVDA,100,$14874.98\n"
        "Fidelity,M/M INC,FXAIX,177.915,$41185.21\n"
    )
    contents, name = _upload_payload(csv, "portfolio.csv")
    result = pi.apply_auto_upload(contents, name)
    assert "holdings" in result["detected"]
    assert "covered_calls" in result["detected"]
    assert result["holdings"]["ok"] is True
    assert result["covered_calls"]["ok"] is True
    assert result["holdings"]["count"] == 4
    assert result["covered_calls"]["count"] == 2

    stocks = db_manager.get_stocks()
    assert set(stocks["ticker"]) == {"NVDA", "SOFI", "FXAIX"}
    fxaix = stocks[stocks["ticker"] == "FXAIX"].iloc[0]
    assert float(fxaix["shares"]) == pytest.approx(177.915)
    sofi = stocks[(stocks["ticker"] == "SOFI") & (stocks["brokerage"] == "Schwab")].iloc[0]
    assert float(sofi["shares"]) == 544

    calls = db_manager.get_covered_calls(status="open")
    assert len(calls) == 2
    sofi_call = calls[calls["ticker"] == "SOFI"].iloc[0]
    assert float(sofi_call["strike"]) == 24.0
    assert sofi_call["expiration_date"] == "2026-09-18"
    assert int(sofi_call["contracts"]) == 2
    assert float(sofi_call["premium_received"]) == pytest.approx(88.67)
    assert sofi_call["brokerage"] == "Schwab"
    assert sofi_call["account"] == "Individual"
    nvda_call = calls[calls["ticker"] == "NVDA"].iloc[0]
    assert float(nvda_call["strike"]) == 260.0
    assert nvda_call["expiration_date"] == "2026-08-28"
    assert int(nvda_call["contracts"]) == 1
    assert float(nvda_call["premium_received"]) == pytest.approx(167.34)
    assert nvda_call["brokerage"] == "Fidelity"
    assert nvda_call["account"] == "Rollover IRA"


def test_export_round_trip_csv(temp_db):
    db_manager.replace_all_stocks(
        [{"brokerage": "Schwab", "account": "IRA", "ticker": "AAPL", "shares": 100, "cost_basis": 1}]
    )
    db_manager.replace_all_covered_calls(
        [
            {
                "brokerage": "Schwab",
                "account": "IRA",
                "ticker": "AAPL",
                "strike": 200,
                "expiration_date": "2026-08-15",
                "contracts": 1,
                "premium_received": 50,
                "open_date": "2026-07-01",
                "status": "open",
                "notes": "x",
            }
        ]
    )
    holdings_csv = pi.export_holdings_csv()
    calls_csv = pi.export_covered_calls_csv()
    assert "AAPL" in holdings_csv
    assert "Schwab" in holdings_csv
    assert "AAPL" in calls_csv
    assert "200" in calls_csv
    z = pi.export_portfolio_zip_bytes()
    assert z[:2] == b"PK"

    portfolio_csv = pi.export_portfolio_csv()
    assert "type" in portfolio_csv.splitlines()[0]
    assert "stock" in portfolio_csv
    assert "call" in portfolio_csv
    # Clear and re-import canonical export
    db_manager.replace_all_stocks([])
    db_manager.replace_all_covered_calls([])
    contents, name = _upload_payload(portfolio_csv, "portfolio.csv")
    result = pi.apply_auto_upload(contents, name)
    assert "holdings" in result["detected"]
    assert "covered_calls" in result["detected"]
    stocks = db_manager.get_stocks()
    assert len(stocks) == 1
    assert stocks.iloc[0]["ticker"] == "AAPL"
    assert stocks.iloc[0]["brokerage"] == "Schwab"
    calls = db_manager.get_covered_calls()
    assert len(calls) == 1
    assert float(calls.iloc[0]["strike"]) == 200
    assert calls.iloc[0]["brokerage"] == "Schwab"
    assert calls.iloc[0]["account"] == "IRA"
    assert calls.iloc[0]["notes"] == "x"
    assert float(calls.iloc[0]["premium_received"]) == pytest.approx(50)
    assert "cost_basis/premium" in portfolio_csv.splitlines()[0]


def test_canonical_template_round_trip(temp_db):
    csv = pi.portfolio_canonical_template_csv()
    assert "cost_basis/premium" in csv.splitlines()[0]
    contents, name = _upload_payload(csv, "portfolio_template.csv")
    result = pi.apply_auto_upload(contents, name)
    assert result["holdings"]["ok"] is True
    assert result["covered_calls"]["ok"] is True
    assert len(db_manager.get_stocks()) == 2
    assert len(db_manager.get_covered_calls()) == 2
    sofi_call = db_manager.get_covered_calls()
    sofi_call = sofi_call[sofi_call["ticker"] == "SOFI"].iloc[0]
    assert sofi_call["brokerage"] == "Schwab"
    assert sofi_call["account"] == "Individual"
    assert float(sofi_call["premium_received"]) == pytest.approx(88.67)


def test_cost_basis_premium_column_maps_call_premium(temp_db):
    csv = (
        "type,brokerage,account,ticker,shares,cost_basis/premium,strike,expiration_date,contracts,open_date,status,notes\n"
        "stock,Schwab,IRA,AAPL,100,5000,,,,,\n"
        "call,Schwab,IRA,AAPL,,250,200,2026-08-15,1,2026-07-01,open,\n"
    )
    contents, name = _upload_payload(csv, "portfolio.csv")
    result = pi.apply_auto_upload(contents, name)
    assert result["holdings"]["ok"] is True
    assert result["covered_calls"]["ok"] is True
    stock = db_manager.get_stocks().iloc[0]
    assert float(stock["cost_basis"]) == pytest.approx(5000)
    call = db_manager.get_covered_calls().iloc[0]
    assert float(call["premium_received"]) == pytest.approx(250)

    exported = pi.export_portfolio_csv()
    header = exported.splitlines()[0]
    assert "cost_basis/premium" in header
    assert "premium_received" not in header.split(",")
    assert "250" in exported
