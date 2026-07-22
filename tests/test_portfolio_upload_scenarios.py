"""
In-depth multi-format upload scenarios: continuity, trim/add, close/reopen,
covered calls, and parser edge cases (canonical + mixed broker exports).
"""
from pathlib import Path

import pytest

from api import portfolio_import as pi
from services import db_manager

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "portfolio_upload_scenarios"


def _upload(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    raw = __import__("base64").b64encode(text.encode("utf-8")).decode("ascii")
    contents = f"data:text/csv;base64,{raw}"
    return pi.apply_auto_upload(contents, path.name)


def _open_map():
    df = db_manager.get_stocks()
    out = {}
    for _, r in df.iterrows():
        key = (
            str(r["brokerage"]),
            str(r["account"]),
            str(r["ticker"]).upper(),
        )
        out[key] = r
    return out


def _calls_df():
    return db_manager.get_covered_calls()


@pytest.fixture
def scenario_db(tmp_path, monkeypatch):
    db_manager.DATABASE = str(tmp_path / "complex_scenario.db")
    db_manager.init_db()
    monkeypatch.setattr(pi, "_refresh_prices_after_holdings_change", lambda: None)
    for t, px in [("AAPL", 150.0), ("MSFT", 400.0), ("NVDA", 120.0)]:
        db_manager.upsert_stock_price(t, "2026-07-12", px)
    return db_manager.DATABASE


def test_complex_multi_format_upload_lifecycle(scenario_db):
    # --- 01 canonical: stocks + calls, money formatting, alternate date ---
    r1 = _upload(FIXTURES / "01_canonical_initial.csv")
    assert r1.get("errors") in (None, [])
    assert "holdings" in r1["detected"] and "covered_calls" in r1["detected"]
    assert r1["holdings"]["count"] == 4
    assert r1["covered_calls"]["count"] == 2

    open1 = _open_map()
    assert ("Schwab", "Individual", "AAPL") in open1
    assert ("Fidelity", "Taxable", "AAPL") in open1  # same ticker, different account
    assert float(open1[("Schwab", "Individual", "AAPL")]["shares"]) == 10
    assert float(open1[("Schwab", "Individual", "AAPL")]["cost_basis"]) == 1000
    aapl_taxable_id = int(open1[("Fidelity", "Taxable", "AAPL")]["id"])
    aapl_ind_id = int(open1[("Schwab", "Individual", "AAPL")]["id"])
    msft_id = int(open1[("Schwab", "Individual", "MSFT")]["id"])
    nvda_id = int(open1[("Fidelity", "Rollover IRA", "NVDA")]["id"])

    calls1 = _calls_df()
    assert len(calls1) == 2
    aapl_call = calls1[calls1["ticker"] == "AAPL"].iloc[0]
    assert float(aapl_call["strike"]) == 200
    assert aapl_call["expiration_date"] == "2026-08-15"
    assert float(aapl_call["premium_received"]) == 312.5  # abs of paren form not used here
    nvda_call = calls1[calls1["ticker"] == "NVDA"].iloc[0]
    assert nvda_call["expiration_date"] == "2026-08-28"  # 08/28/2026 normalized
    assert float(nvda_call["premium_received"]) == 167.34
    assert db_manager.get_realized_gains().empty

    # --- 02 mixed broker export: aliases, OCC/verbose options, trim/add ---
    r2 = _upload(FIXTURES / "02_mixed_trim_add_and_calls.csv")
    assert "holdings" in r2["detected"] and "covered_calls" in r2["detected"]
    open2 = _open_map()
    assert int(open2[("Schwab", "Individual", "AAPL")]["id"]) == aapl_ind_id  # continuous
    assert int(open2[("Schwab", "Individual", "MSFT")]["id"]) == msft_id
    assert int(open2[("Fidelity", "Rollover IRA", "NVDA")]["id"]) == nvda_id
    assert int(open2[("Fidelity", "Taxable", "AAPL")]["id"]) == aapl_taxable_id
    assert float(open2[("Schwab", "Individual", "AAPL")]["shares"]) == 6
    assert float(open2[("Schwab", "Individual", "MSFT")]["shares"]) == 8

    gains = db_manager.get_realized_gains()
    assert len(gains) == 1
    trim = gains.iloc[0]
    assert trim["ticker"] == "AAPL"
    assert trim["account"] == "Individual"
    assert float(trim["shares"]) == 4
    assert float(trim["cost_basis"]) == 400
    assert float(trim["proceeds"]) == 600  # 4 * 150
    assert trim["source"] == "upload_sync"

    calls2 = _calls_df()
    assert len(calls2) == 3  # AAPL verbose, NVDA OCC short, MSFT OCC
    assert set(calls2["ticker"]) == {"AAPL", "NVDA", "MSFT"}
    msft_cc = calls2[calls2["ticker"] == "MSFT"].iloc[0]
    assert int(msft_cc["contracts"]) == 2
    assert float(msft_cc["strike"]) == 450
    assert msft_cc["expiration_date"] == "2026-09-18"

    # --- 03 canonical: close NVDA, replace call book ---
    r3 = _upload(FIXTURES / "03_canonical_close_nvda_roll_calls.csv")
    open3 = _open_map()
    assert ("Fidelity", "Rollover IRA", "NVDA") not in open3
    assert int(open3[("Schwab", "Individual", "AAPL")]["id"]) == aapl_ind_id
    assert int(open3[("Schwab", "Individual", "MSFT")]["id"]) == msft_id

    gains = db_manager.get_realized_gains()
    assert len(gains) == 2
    nvda_g = gains[gains["ticker"] == "NVDA"].iloc[0]
    assert float(nvda_g["shares"]) == 20
    assert float(nvda_g["cost_basis"]) == 2000
    assert float(nvda_g["proceeds"]) == 2400  # 20 * 120
    assert nvda_g["brokerage"] == "Fidelity"

    calls3 = _calls_df()
    assert len(calls3) == 2
    assert set(calls3["ticker"]) == {"MSFT", "AAPL"}
    # NVDA covered call wiped with replace_all_covered_calls
    assert "NVDA" not in set(calls3["ticker"])
    aapl_tax_call = calls3[
        (calls3["ticker"] == "AAPL") & (calls3["account"] == "Taxable")
    ].iloc[0]
    assert aapl_tax_call["expiration_date"] == "2026-07-17"
    assert float(aapl_tax_call["strike"]) == 175

    # --- 04 mixed: reopen NVDA as new lot + new calls ---
    r4 = _upload(FIXTURES / "04_mixed_reopen_nvda.csv")
    open4 = _open_map()
    assert ("Fidelity", "Rollover IRA", "NVDA") in open4
    assert int(open4[("Fidelity", "Rollover IRA", "NVDA")]["id"]) != nvda_id
    assert float(open4[("Fidelity", "Rollover IRA", "NVDA")]["shares"]) == 10
    assert float(open4[("Fidelity", "Rollover IRA", "NVDA")]["cost_basis"]) == 1500
    # Continuous ids preserved for untouched lots
    assert int(open4[("Schwab", "Individual", "AAPL")]["id"]) == aapl_ind_id
    assert int(open4[("Schwab", "Individual", "MSFT")]["id"]) == msft_id
    assert len(db_manager.get_realized_gains()) == 2  # reopen does not add gains

    calls4 = _calls_df()
    assert len(calls4) == 2
    assert set(calls4["ticker"]) == {"MSFT", "NVDA"}
    nvda_new_cc = calls4[calls4["ticker"] == "NVDA"].iloc[0]
    assert nvda_new_cc["expiration_date"] == "2026-10-16"
    assert float(nvda_new_cc["strike"]) == 130
    assert float(nvda_new_cc["premium_received"]) == 95.4


def test_invalid_duplicate_holdings_file_rejected(scenario_db):
    result = _upload(FIXTURES / "05_invalid_duplicate_holdings.csv")
    # holdings-only path returns ok False on the holdings side
    assert result["holdings"] is not None
    assert result["holdings"]["ok"] is False
    assert any("duplicate" in e.lower() for e in result["holdings"]["errors"])


def test_simple_holdings_sequence_still_works(scenario_db):
    """Keep the original plain holdings fixtures as a smoke path."""
    for name in (
        "01_initial.csv",
        "02_trim_aapl_add_msft.csv",
        "03_close_nvda.csv",
        "04_reopen_nvda.csv",
    ):
        text = (FIXTURES / name).read_text(encoding="utf-8")
        raw = __import__("base64").b64encode(text.encode("utf-8")).decode("ascii")
        result = pi.apply_auto_upload(f"data:text/csv;base64,{raw}", name)
        assert result["holdings"]["ok"] is True

    open_lots = _open_map()
    assert ("Schwab", "Individual", "AAPL") in open_lots
    assert ("Fidelity", "Rollover IRA", "NVDA") in open_lots
    gains = db_manager.get_realized_gains()
    assert set(gains["ticker"]) == {"AAPL", "NVDA"}
