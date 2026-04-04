import sqlite3
from pathlib import Path
from types import SimpleNamespace

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


def test_client_error_log_insert(tmp_path):
    _init_temp_db(tmp_path)
    db_manager.insert_client_error("ui_test", "something failed", "detail line")
    conn = sqlite3.connect(db_manager.DATABASE)
    row = conn.execute(
        "SELECT origin, source, message, detail FROM client_error_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row == ("client", "ui_test", "something failed", "detail line")


def test_prune_error_logs_deletes_old_rows(tmp_path):
    _init_temp_db(tmp_path)
    conn = sqlite3.connect(db_manager.DATABASE)
    conn.execute(
        """
        INSERT INTO client_error_log (created_at, origin, source, message, detail)
        VALUES (?, 'client', 'old', 'msg', NULL)
        """,
        ("2020-01-01 00:00:00",),
    )
    conn.execute(
        """
        INSERT INTO client_error_log (created_at, origin, source, message, detail)
        VALUES (?, 'server', 'new', 'msg2', NULL)
        """,
        ("2099-01-01 00:00:00",),
    )
    conn.commit()
    conn.close()
    deleted = db_manager.prune_error_logs(retention_days=30)
    assert deleted >= 1
    conn = sqlite3.connect(db_manager.DATABASE)
    n = conn.execute("SELECT COUNT(*) FROM client_error_log").fetchone()[0]
    conn.close()
    assert n == 1


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


def test_plaid_helpers_use_configured_database_path(tmp_path, monkeypatch):
    custom_db = tmp_path / "custom_finance_data.db"
    db_manager.DATABASE = str(custom_db)
    db_manager.init_db()
    monkeypatch.chdir(tmp_path)

    db_manager.insert_items("item-1", "token-1")
    db_manager.update_item_institution("item-1", "Test Bank", "ins_123")

    account = SimpleNamespace(
        account_id="acct-1",
        name="Checking",
        official_name="Primary Checking",
        type="depository",
        subtype="checking",
        balances=SimpleNamespace(current=1234.56),
    )
    db_manager.store_accounts([account], item_id="item-1")

    transaction = SimpleNamespace(
        transaction_id="txn-1",
        account_id="acct-1",
        amount=42.5,
        date="2026-03-18",
        name="Coffee Shop",
        category=["Food and Drink"],
    )
    db_manager.insert_transactions([transaction])

    items = db_manager.get_items()
    assert items == [{"item_id": "item-1", "access_token": "token-1"}]
    assert db_manager.get_institutions() == ["Test Bank"]

    conn = sqlite3.connect(custom_db)
    cur = conn.cursor()
    cur.execute("SELECT item_id, institution_name, institution_id FROM items")
    assert cur.fetchone() == ("item-1", "Test Bank", "ins_123")
    cur.execute("SELECT account_id, item_id FROM accounts")
    assert cur.fetchone() == ("acct-1", "item-1")
    cur.execute("SELECT transaction_id, account_id, name FROM transactions")
    assert cur.fetchone() == ("txn-1", "acct-1", "Coffee Shop")
    conn.close()

    assert not (tmp_path / "finance_data.db").exists()


def test_get_held_stock_tickers_distinct_upper(tmp_path):
    _init_temp_db(tmp_path)
    db_manager.insert_stock("aapl", 1.0, cost_basis=100.0)
    db_manager.insert_stock("MSFT", 2.0, cost_basis=200.0)
    assert db_manager.get_held_stock_tickers() == ["AAPL", "MSFT"]


def test_news_digest_articles_upsert_and_list_filters(tmp_path):
    _init_temp_db(tmp_path)
    digest = {
        "generated_at_utc": "2026-04-03T12:00:00+00:00",
        "items": [
            {
                "title": "Fed holds rates",
                "link": "https://example.com/a",
                "source_feed": "CNBC",
                "categories": ["rates", "markets"],
                "tickers": ["MSFT"],
                "ticker_companies": {"MSFT": "Manage Stocks"},
            },
            {
                "title": "Oil slips",
                "link": "https://example.com/b",
                "source_feed": "BBC",
                "categories": ["energy"],
                "tickers": [],
                "ticker_companies": {},
            },
        ],
    }
    assert db_manager.upsert_news_digest_articles_from_digest(digest) == 2
    items, total, per = db_manager.list_news_digest_articles(page=1, per_page=10, sort="created")
    assert total == 2
    assert per == 10
    assert len(items) == 2
    assert items[0]["first_seen_at_utc"] == "2026-04-03T12:00:00+00:00"
    assert items[0]["summary"] is None
    rates_only, t2, _ = db_manager.list_news_digest_articles(
        category="rates", per_page=20
    )
    assert t2 == 1
    assert len(rates_only) == 1
    assert rates_only[0]["link"] == "https://example.com/a"
    msft_only, t3, _ = db_manager.list_news_digest_articles(ticker="MSFT")
    assert t3 == 1
    assert msft_only[0]["tickers"] == ["MSFT"]


def test_normalize_news_article_url_strips_tracking_params():
    raw = "https://EXAMPLE.com/Path/?utm_source=tw&id=1&utm_medium=x"
    out = db_manager.normalize_news_article_url_string(raw)
    assert "utm_" not in out
    assert "example.com" in out
    assert "id=1" in out


def test_prune_news_digest_articles_deletes_old_by_first_seen(tmp_path):
    _init_temp_db(tmp_path)
    old = "2020-01-01T00:00:00+00:00"
    conn = sqlite3.connect(db_manager.DATABASE)
    conn.execute(
        """
        INSERT INTO news_digest_articles (
            url, title, source_feed, categories_json, tickers_json, ticker_companies_json,
            first_seen_at_utc, last_seen_at_utc, summary
        ) VALUES (?, ?, ?, '[]', '[]', '{}', ?, ?, NULL)
        """,
        ("https://old.com/z", "Old", "X", old, old),
    )
    conn.commit()
    conn.close()
    n = db_manager.prune_news_digest_articles(retention_days=90)
    assert n >= 1
    remaining, tot, _ = db_manager.list_news_digest_articles(per_page=50)
    assert tot == 0


def test_get_plaid_holdings_tickers_distinct_upper(tmp_path):
    _init_temp_db(tmp_path)
    conn = sqlite3.connect(db_manager.DATABASE)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO items (item_id, access_token, institution_name) VALUES (?, ?, ?)",
        ("item-1", "tok", "Bank"),
    )
    cur.execute(
        """
        INSERT INTO accounts (account_id, name, official_name, type, subtype, current_balance, item_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("acct-1", "Brokerage", "Brokerage", "investment", "brokerage", 0.0, "item-1"),
    )
    cur.execute(
        "INSERT INTO plaid_holdings (account_id, ticker, shares, cost_basis) VALUES (?, ?, ?, ?)",
        ("acct-1", "nvda", 1.0, 100.0),
    )
    cur.execute(
        "INSERT INTO plaid_holdings (account_id, ticker, shares, cost_basis) VALUES (?, ?, ?, ?)",
        ("acct-1", "MSFT", 2.0, 200.0),
    )
    conn.commit()
    conn.close()
    assert db_manager.get_plaid_holdings_tickers() == ["MSFT", "NVDA"]
