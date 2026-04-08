import sqlite3
from pathlib import Path
from types import SimpleNamespace

from services import db_manager


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


def test_delete_plaid_item_data_removes_accounts_transactions_holdings(tmp_path):
    _init_temp_db(tmp_path)
    db_manager.insert_items("it-del", "tok")
    db_manager.update_item_institution("it-del", "Bank", "ins_1")
    account = SimpleNamespace(
        account_id="acct-del",
        name="Checking",
        official_name=None,
        type="depository",
        subtype="checking",
        balances=SimpleNamespace(current=100.0),
    )
    db_manager.store_accounts([account], item_id="it-del")
    conn = sqlite3.connect(db_manager.DATABASE)
    conn.execute(
        """
        INSERT INTO transactions (transaction_id, account_id, amount, date, name, category)
        VALUES ('tx1', 'acct-del', 1.0, '2026-01-01', 'Coffee', 'Food')
        """
    )
    conn.commit()
    conn.close()
    db_manager.upsert_plaid_holding("acct-del", "AAPL", 1.0, 100.0)

    summary = db_manager.delete_plaid_item_data("it-del")
    assert summary["items_deleted"] == 1
    assert summary["accounts_deleted"] == 1
    assert summary["transactions_deleted"] >= 1
    assert summary["plaid_holdings_deleted"] >= 1

    conn = sqlite3.connect(db_manager.DATABASE)
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM plaid_holdings").fetchone()[0] == 0
    conn.close()


def test_find_plaid_items_matching_institution(tmp_path):
    _init_temp_db(tmp_path)
    db_manager.insert_items("a", "t1")
    db_manager.update_item_institution("a", "Same Bank", "ins_x")
    db_manager.insert_items("b", "t2")
    db_manager.update_item_institution("b", "Other", "ins_y")

    m = db_manager.find_plaid_items_matching_institution(
        institution_id="ins_x",
        institution_name=None,
        exclude_item_id="new",
    )
    assert [x["item_id"] for x in m] == ["a"]


def test_plaid_access_token_encrypted_at_rest_when_key_configured(tmp_path, monkeypatch):
    _init_temp_db(tmp_path)
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("PLAID_TOKEN_ENCRYPTION_KEY", key)

    db_manager.insert_items("item-enc", "secret-access-token")
    items = db_manager.get_items()
    assert len(items) == 1
    assert items[0]["item_id"] == "item-enc"
    assert items[0]["access_token"] == "secret-access-token"
    assert items[0]["first_linked_at_utc"]
    assert items[0]["updated_at_utc"]

    conn = sqlite3.connect(db_manager.DATABASE)
    raw = conn.execute("SELECT access_token FROM items WHERE item_id = ?", ("item-enc",)).fetchone()[
        0
    ]
    conn.close()
    assert raw != "secret-access-token"
    assert Fernet(key.encode("utf-8")).decrypt(raw.encode("utf-8")).decode("utf-8") == (
        "secret-access-token"
    )


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
    assert len(items) == 1
    assert items[0]["item_id"] == "item-1"
    assert items[0]["access_token"] == "token-1"
    assert items[0]["first_linked_at_utc"]
    assert items[0]["updated_at_utc"]
    assert db_manager.get_institutions() == ["Test Bank"]

    conn = sqlite3.connect(custom_db)
    cur = conn.cursor()
    cur.execute("SELECT item_id, institution_name, institution_id FROM items")
    assert cur.fetchone() == ("item-1", "Test Bank", "ins_123")
    cur.execute(
        "SELECT account_id, item_id, first_seen_at_utc, updated_at_utc FROM accounts"
    )
    acct_row = cur.fetchone()
    assert acct_row[0] == "acct-1" and acct_row[1] == "item-1"
    assert acct_row[2] and acct_row[3]
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


def test_news_digest_urls_with_null_summary(tmp_path):
    _init_temp_db(tmp_path)
    conn = sqlite3.connect(db_manager.DATABASE)
    t = "2026-01-01T12:00:00+00:00"
    conn.execute(
        """
        INSERT INTO news_digest_articles (
            url, title, source_feed, categories_json, tickers_json, ticker_companies_json,
            first_seen_at_utc, last_seen_at_utc, summary
        ) VALUES (?, ?, ?, '[]', '[]', '{}', ?, ?, NULL)
        """,
        ("https://a.com/x", "A", "S", t, t),
    )
    conn.execute(
        """
        INSERT INTO news_digest_articles (
            url, title, source_feed, categories_json, tickers_json, ticker_companies_json,
            first_seen_at_utc, last_seen_at_utc, summary
        ) VALUES (?, ?, ?, '[]', '[]', '{}', ?, ?, ?)
        """,
        ("https://b.com/y", "B", "S", t, t, "has body"),
    )
    conn.commit()
    conn.close()
    s = db_manager.news_digest_urls_with_null_summary(["https://a.com/x", "https://b.com/y"])
    assert s == {"https://a.com/x"}


def test_news_digest_local_dates_day_bounds_and_neighbors(tmp_path):
    _init_temp_db(tmp_path)
    conn = sqlite3.connect(db_manager.DATABASE)
    conn.execute(
        """
        INSERT INTO news_digest_articles (
            url, title, source_feed, categories_json, tickers_json, ticker_companies_json,
            first_seen_at_utc, last_seen_at_utc, summary
        ) VALUES (?, ?, ?, '[]', '[]', '{}', ?, ?, NULL)
        """,
        ("https://day-new.com", "New", "X", "2026-04-03T10:00:00+00:00", "2026-04-03T10:00:00+00:00"),
    )
    conn.execute(
        """
        INSERT INTO news_digest_articles (
            url, title, source_feed, categories_json, tickers_json, ticker_companies_json,
            first_seen_at_utc, last_seen_at_utc, summary
        ) VALUES (?, ?, ?, '[]', '[]', '{}', ?, ?, NULL)
        """,
        ("https://day-old.com", "Old", "X", "2026-04-01T15:00:00+00:00", "2026-04-01T15:00:00+00:00"),
    )
    conn.commit()
    conn.close()
    meta = db_manager.list_news_digest_local_dates_desc()
    dates = [m["date"] for m in meta]
    assert "2026-04-03" in dates and "2026-04-01" in dates
    asc = sorted(dates)
    older, newer = db_manager.news_digest_local_date_neighbors(asc, "2026-04-03")
    assert older == "2026-04-01"
    assert newer is None
    older2, newer2 = db_manager.news_digest_local_date_neighbors(asc, "2026-04-01")
    assert older2 is None
    assert newer2 == "2026-04-03"
    day_rows = db_manager.list_news_digest_articles_for_local_date("2026-04-01")
    assert len(day_rows) == 1
    assert day_rows[0]["url"] == "https://day-old.com"


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


def test_quant_risk_snapshots_roundtrip(tmp_path):
    _init_temp_db(tmp_path)
    payload = {
        "volatility_pct": 14.5,
        "max_drawdown_pct": -8.0,
        "beta": 1.1,
        "last_updated": "2026-04-01",
        "fresh": True,
        "top_sector": "Technology",
        "top_sector_pct": 40.0,
        "hhi": 0.25,
        "diversification_ratio": 0.9,
    }
    db_manager.upsert_quant_risk_snapshot("2026-04-01", payload)
    rows = db_manager.get_quant_risk_snapshots(limit=5)
    assert len(rows) == 1
    assert rows[0]["snapshot_date"] == "2026-04-01"
    assert rows[0]["payload"]["beta"] == 1.1
    db_manager.upsert_quant_risk_snapshot("2026-04-01", {**payload, "beta": 1.2})
    rows2 = db_manager.get_quant_risk_snapshots(limit=5)
    assert rows2[0]["payload"]["beta"] == 1.2


def test_quant_backtest_runs_roundtrip(tmp_path):
    _init_temp_db(tmp_path)
    params = {
        "portfolio": {"AAPL": 1.0},
        "start": "2020-01-01",
        "end": "2021-01-01",
        "strategy_name": "sma",
        "fast_window": 10,
        "slow_window": 30,
        "rebalance_monthly": False,
    }
    stats = {"total_return_pct": 5.0, "sharpe_ratio": 1.2}
    bench = {"total_return_pct": 4.0}
    db_manager.insert_quant_backtest_run("job-q1", params, stats, bench)
    one = db_manager.get_quant_backtest_run_by_job_id("job-q1")
    assert one
    assert one["stats"]["total_return_pct"] == 5.0
    assert one["benchmark_stats"]["total_return_pct"] == 4.0
    rows = db_manager.get_quant_backtest_runs(limit=5)
    assert len(rows) == 1
    assert rows[0]["job_id"] == "job-q1"


def test_quant_backtest_runs_filtered(tmp_path):
    _init_temp_db(tmp_path)
    base_sma = {
        "portfolio": {"AAPL": 1.0, "MSFT": 2.0},
        "start": "2020-01-01",
        "end": "2021-01-01",
        "strategy_name": "sma",
        "fast_window": 10,
        "slow_window": 30,
        "rebalance_monthly": False,
    }
    base_bh = {
        **base_sma,
        "strategy_name": "buy_hold",
    }
    db_manager.insert_quant_backtest_run("j1", base_sma, {"total_return_pct": 1.0}, {})
    db_manager.insert_quant_backtest_run("j2", base_bh, {"total_return_pct": 2.0}, {})
    db_manager.insert_quant_backtest_run(
        "j3",
        {**base_sma, "portfolio": {"GOOG": 1.0}},
        {"total_return_pct": 3.0},
        {},
    )
    only_sma = db_manager.get_quant_backtest_runs_filtered(limit=10, strategy_name="sma")
    assert len(only_sma) == 2
    assert {r["job_id"] for r in only_sma} == {"j1", "j3"}
    msft = db_manager.get_quant_backtest_runs_filtered(limit=10, ticker_contains="MSFT")
    assert len(msft) == 2
    goog = db_manager.get_quant_backtest_runs_filtered(limit=10, ticker_contains="GOOG")
    assert len(goog) == 1
    assert goog[0]["job_id"] == "j3"


def test_prune_sec_filing_summaries_keeps_recent_deletes_old(tmp_path):
    _init_temp_db(tmp_path)
    conn = sqlite3.connect(db_manager.DATABASE)
    old = "2020-01-01T00:00:00+00:00"
    new = "2025-06-15T12:00:00+00:00"
    conn.execute(
        """
        INSERT INTO sec_filing_summaries
        (doc_hash, ticker, filing_type, filing_date, source_path, summary_text, model, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("hash_old", "X", "10-K", "2020-01-01", "/p", "old", "m", old),
    )
    conn.execute(
        """
        INSERT INTO sec_filing_summaries
        (doc_hash, ticker, filing_type, filing_date, source_path, summary_text, model, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("hash_new", "Y", "10-Q", "2025-01-01", "/q", "new", "m", new),
    )
    conn.commit()
    conn.close()
    n = db_manager.prune_sec_filing_summaries(retention_days=365)
    assert n >= 1
    conn = sqlite3.connect(db_manager.DATABASE)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM sec_filing_summaries")
    count = cur.fetchone()[0]
    conn.close()
    assert count == 1


def test_recent_null_summary_and_update_summary(tmp_path):
    _init_temp_db(tmp_path)
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc).isoformat()
    old = "2020-01-01T00:00:00+00:00"
    conn = sqlite3.connect(db_manager.DATABASE)
    conn.execute(
        """INSERT INTO news_digest_articles
        (url, title, source_feed, categories_json, tickers_json, ticker_companies_json,
         first_seen_at_utc, last_seen_at_utc, summary)
        VALUES (?, ?, ?, '[]', '[]', '{}', ?, ?, NULL)""",
        ("https://x.com/null-summary", "Null Article", "T", now, now),
    )
    conn.execute(
        """INSERT INTO news_digest_articles
        (url, title, source_feed, categories_json, tickers_json, ticker_companies_json,
         first_seen_at_utc, last_seen_at_utc, summary)
        VALUES (?, ?, ?, '[]', '[]', '{}', ?, ?, 'already filled')""",
        ("https://x.com/has-summary", "Filled Article", "T", now, now),
    )
    conn.execute(
        """INSERT INTO news_digest_articles
        (url, title, source_feed, categories_json, tickers_json, ticker_companies_json,
         first_seen_at_utc, last_seen_at_utc, summary)
        VALUES (?, ?, ?, '[]', '[]', '{}', ?, ?, NULL)""",
        ("https://x.com/old-null", "Old Null", "T", old, old),
    )
    conn.commit()
    conn.close()

    rows = db_manager.recent_news_digest_articles_with_null_summary(days=2)
    urls = {r["url"] for r in rows}
    assert "https://x.com/null-summary" in urls
    assert "https://x.com/has-summary" not in urls
    assert "https://x.com/old-null" not in urls

    assert db_manager.update_news_digest_article_summary("https://x.com/null-summary", "Now filled")
    rows2 = db_manager.recent_news_digest_articles_with_null_summary(days=2)
    assert all(r["url"] != "https://x.com/null-summary" for r in rows2)


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
