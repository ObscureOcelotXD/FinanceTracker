import sqlite3
from pathlib import Path

import db_manager


def _init_temp_db(tmp_path: Path):
    db_path = tmp_path / "test_finance_data.db"
    db_manager.DATABASE = str(db_path)
    db_manager.init_db()
    return db_path


def test_realized_gain_insert_and_compute(tmp_path):
    _init_temp_db(tmp_path)
    gain_id = db_manager.insert_realized_gain(
        ticker="MSFT",
        shares=10,
        proceeds=1500.0,
        cost_basis=1000.0,
        fees=25.0,
        tax_year=2024,
    )
    assert gain_id is not None
    df = db_manager.get_realized_gains(2024)
    assert not df.empty
    row = df.iloc[0]
    assert row["realized_gain"] == 475.0
    assert round(row["realized_gain_pct"], 6) == 0.475


def test_plaid_holdings_upsert_and_query(tmp_path):
    _init_temp_db(tmp_path)
    conn = sqlite3.connect(db_manager.DATABASE)
    cur = conn.cursor()
    cur.execute("INSERT INTO items (item_id, access_token, institution_name) VALUES (?, ?, ?)",
                ("item-1", "token", "Test Bank"))
    cur.execute(
        """
        INSERT INTO accounts (account_id, name, official_name, type, subtype, current_balance, item_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("acct-1", "Brokerage", "Brokerage", "investment", "brokerage", 0.0, "item-1"),
    )
    cur.execute(
        "INSERT INTO stock_prices (ticker, date, closing_price) VALUES (?, ?, ?)",
        ("AAPL", "2026-01-24", 200.0),
    )
    conn.commit()
    conn.close()

    db_manager.upsert_plaid_holding("acct-1", "AAPL", 2.0, 300.0)
    df = db_manager.get_plaid_holdings("Test Bank")
    assert not df.empty
    row = df.iloc[0]
    assert row["ticker"] == "AAPL"
    assert row["shares"] == 2.0
    assert row["cost_basis"] == 300.0
    assert row["position_value"] == 400.0


def test_wipe_all_data_clears_tables(tmp_path):
    _init_temp_db(tmp_path)
    db_manager.insert_stock("AAPL", 1, cost_basis=100.0)
    db_manager.insert_realized_gain(
        ticker="AAPL",
        shares=1,
        proceeds=150.0,
        cost_basis=100.0,
        fees=0.0,
        tax_year=2025,
    )
    db_manager.wipe_all_data()
    assert db_manager.get_stocks().empty
    assert db_manager.get_realized_gains().empty
