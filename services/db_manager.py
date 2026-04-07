import hashlib
import json
import os
import sqlite3
import bisect
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from zoneinfo import ZoneInfo

import pandas as pd
import re
DATABASE = "finance_data.db"


def _plaid_token_encryption_key_raw() -> Optional[str]:
    raw = (os.getenv("PLAID_TOKEN_ENCRYPTION_KEY") or "").strip()
    return raw or None


def _encrypt_plaid_access_token_at_rest(plain: str) -> str:
    """When ``PLAID_TOKEN_ENCRYPTION_KEY`` is set (Fernet urlsafe base64), store ciphertext in SQLite."""
    key_raw = _plaid_token_encryption_key_raw()
    if not key_raw or not plain:
        return plain
    from cryptography.fernet import Fernet

    f = Fernet(key_raw.encode("utf-8"))
    return f.encrypt(plain.encode("utf-8")).decode("utf-8")


def _decrypt_plaid_access_token_at_rest(stored: str) -> str:
    if not stored:
        return stored
    key_raw = _plaid_token_encryption_key_raw()
    if not key_raw:
        return stored
    from cryptography.fernet import Fernet, InvalidToken

    f = Fernet(key_raw.encode("utf-8"))
    try:
        return f.decrypt(stored.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # Legacy rows written before encryption was enabled remain readable as plaintext.
        return stored


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_items_timestamp_columns(c: sqlite3.Cursor) -> None:
    c.execute("PRAGMA table_info(items)")
    cols = [row[1] for row in c.fetchall()]
    if "first_linked_at_utc" not in cols:
        c.execute("ALTER TABLE items ADD COLUMN first_linked_at_utc TEXT")
    if "updated_at_utc" not in cols:
        c.execute("ALTER TABLE items ADD COLUMN updated_at_utc TEXT")


def _ensure_items_institution_columns(c: sqlite3.Cursor) -> None:
    c.execute("PRAGMA table_info(items)")
    cols = [row[1] for row in c.fetchall()]
    if "institution_name" not in cols:
        c.execute("ALTER TABLE items ADD COLUMN institution_name TEXT")
    if "institution_id" not in cols:
        c.execute("ALTER TABLE items ADD COLUMN institution_id TEXT")


def _ensure_accounts_timestamp_columns(c: sqlite3.Cursor) -> None:
    c.execute("PRAGMA table_info(accounts)")
    cols = [row[1] for row in c.fetchall()]
    if "first_seen_at_utc" not in cols:
        c.execute("ALTER TABLE accounts ADD COLUMN first_seen_at_utc TEXT")
    if "updated_at_utc" not in cols:
        c.execute("ALTER TABLE accounts ADD COLUMN updated_at_utc TEXT")


def get_connection():
    return sqlite3.connect(DATABASE)

# region Initialization
def init_db():
    """Initializes the database and creates the table if it doesn't exist."""
    con = get_connection()
    cur = con.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS finance_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_name TEXT NOT NULL,
            source_name TEXT NOT NULL,
            source_value REAL NOT NULL,
            date_created TEXT NOT NULL
        )
    ''')

    cur2 = con.cursor()
    cur2.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            account_id TEXT PRIMARY KEY,
            name TEXT,
            official_name TEXT,
            type TEXT,
            subtype TEXT,
            current_balance REAL,
            first_seen_at_utc TEXT,
            updated_at_utc TEXT
        )
    """)
    cur2.execute("PRAGMA table_info(accounts)")
    account_columns = [row[1] for row in cur2.fetchall()]
    if "item_id" not in account_columns:
        cur2.execute("ALTER TABLE accounts ADD COLUMN item_id TEXT")
    _ensure_accounts_timestamp_columns(cur2)

    cur3 = con.cursor()
    cur3.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id TEXT PRIMARY KEY,
            account_id TEXT,
            amount REAL,
            date TEXT,
            name TEXT,
            category TEXT
        )
    """)

    cur4 = con.cursor()
    cur4.execute("""
        CREATE TABLE IF NOT EXISTS Stocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            shares REAL NOT NULL
        )
    """)
    # Add cost_basis column if it doesn't exist yet.
    cur4.execute("PRAGMA table_info(Stocks)")
    stock_columns = [row[1] for row in cur4.fetchall()]
    if "cost_basis" not in stock_columns:
        cur4.execute("ALTER TABLE Stocks ADD COLUMN cost_basis REAL")
    # Merge duplicate tickers before enforcing uniqueness.
    cur4.execute("""
        UPDATE Stocks
        SET shares = (
            SELECT SUM(s2.shares)
            FROM Stocks s2
            WHERE s2.ticker = Stocks.ticker
        )
        WHERE id IN (
            SELECT MIN(id)
            FROM Stocks
            GROUP BY ticker
        )
    """)
    cur4.execute("""
        UPDATE Stocks
        SET cost_basis = (
            SELECT SUM(COALESCE(s2.cost_basis, 0))
            FROM Stocks s2
            WHERE s2.ticker = Stocks.ticker
        )
        WHERE id IN (
            SELECT MIN(id)
            FROM Stocks
            GROUP BY ticker
        )
    """)
    cur4.execute("""
        DELETE FROM Stocks
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM Stocks
            GROUP BY ticker
        )
    """)
    # Enforce unique tickers to prevent duplicates going forward.
    cur4.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_stocks_ticker
        ON Stocks (ticker)
    """)

    cur5 = con.cursor()
    cur5.execute("""
        CREATE TABLE IF NOT EXISTS stock_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            closing_price REAL NOT NULL
        )
    """)
    # Ensure no duplicate (ticker, date) rows before adding unique constraint.
    cur5.execute("""
        DELETE FROM stock_prices
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM stock_prices
            GROUP BY ticker, date
        )
    """)
    # Enforce one price per ticker per day.
    cur5.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_stock_prices_ticker_date
        ON stock_prices (ticker, date)
    """)


    cur6 = con.cursor()
    cur6.execute("""
        CREATE TABLE IF NOT EXISTS price_update_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            last_run_date TEXT NOT NULL
        )
    """)
    cur7 = con.cursor()
    cur7.execute("""
        CREATE TABLE IF NOT EXISTS stock_metadata (
            ticker TEXT PRIMARY KEY,
            sector TEXT,
            updated_at TEXT
        )
    """)

    cur7.execute("""
        CREATE TABLE IF NOT EXISTS items (
            item_id TEXT PRIMARY KEY,
            access_token TEXT,
            institution_name TEXT,
            institution_id TEXT,
            first_linked_at_utc TEXT,
            updated_at_utc TEXT
        )
    """)
    _ensure_items_timestamp_columns(cur7)

    cur8 = con.cursor()
    cur8.execute("""
        CREATE TABLE IF NOT EXISTS realized_gains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            shares REAL NOT NULL,
            buy_date TEXT,
            sell_date TEXT,
            proceeds REAL NOT NULL,
            cost_basis REAL NOT NULL,
            fees REAL,
            realized_gain REAL,
            realized_gain_pct REAL,
            tax_year INTEGER NOT NULL
        )
    """)

    cur9 = con.cursor()
    cur9.execute("""
        CREATE TABLE IF NOT EXISTS plaid_holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            shares REAL NOT NULL,
            cost_basis REAL
        )
    """)
    cur9.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_plaid_holdings_account_ticker
        ON plaid_holdings (account_id, ticker)
    """)

    cur10 = con.cursor()
    cur10.execute("""
        CREATE TABLE IF NOT EXISTS benchmark_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            closing_price REAL NOT NULL,
            source TEXT,
            updated_at TEXT
        )
    """)
    cur10.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_benchmark_prices_symbol_date
        ON benchmark_prices (symbol, date)
    """)

    cur11 = con.cursor()
    cur11.execute("""
        CREATE TABLE IF NOT EXISTS etf_sector_breakdown (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            sector TEXT NOT NULL,
            weight REAL NOT NULL,
            source TEXT,
            updated_at TEXT
        )
    """)
    cur11.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_etf_sector_symbol_sector
        ON etf_sector_breakdown (symbol, sector)
    """)

    cur12 = con.cursor()
    cur12.execute("""
        CREATE TABLE IF NOT EXISTS etf_sources (
            symbol TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            url TEXT,
            updated_at TEXT
        )
    """)

    cur13 = con.cursor()
    cur13.execute("""
        CREATE TABLE IF NOT EXISTS sec_filing_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_hash TEXT NOT NULL,
            ticker TEXT,
            filing_type TEXT,
            filing_date TEXT,
            source_path TEXT,
            summary_text TEXT,
            model TEXT,
            created_at TEXT NOT NULL
        )
    """)
    cur13.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_sec_filing_doc_hash
        ON sec_filing_summaries (doc_hash)
    """)

    cur14 = con.cursor()
    cur14.execute("""
        CREATE TABLE IF NOT EXISTS client_error_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            origin TEXT NOT NULL DEFAULT 'client',
            source TEXT NOT NULL,
            message TEXT NOT NULL,
            detail TEXT
        )
    """)
    cur14.execute("PRAGMA table_info(client_error_log)")
    _cel_cols = [row[1] for row in cur14.fetchall()]
    if _cel_cols and "origin" not in _cel_cols:
        cur14.execute(
            "ALTER TABLE client_error_log ADD COLUMN origin TEXT DEFAULT 'client'"
        )
        cur14.execute(
            "UPDATE client_error_log SET origin = 'client' WHERE origin IS NULL"
        )
    cur14.execute("""
        CREATE INDEX IF NOT EXISTS idx_client_error_log_created_at
        ON client_error_log (created_at)
    """)

    cur15 = con.cursor()
    cur15.execute("""
        CREATE TABLE IF NOT EXISTS news_digest_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            source_feed TEXT,
            categories_json TEXT NOT NULL DEFAULT '[]',
            tickers_json TEXT NOT NULL DEFAULT '[]',
            ticker_companies_json TEXT NOT NULL DEFAULT '{}',
            first_seen_at_utc TEXT NOT NULL,
            last_seen_at_utc TEXT NOT NULL,
            summary TEXT
        )
    """)
    cur15.execute("PRAGMA table_info(news_digest_articles)")
    _nda_cols = {row[1] for row in cur15.fetchall()}
    if "summary" not in _nda_cols:
        # TODO: populate from LLM or paid API when summaries are implemented.
        cur15.execute("ALTER TABLE news_digest_articles ADD COLUMN summary TEXT")
    if "ai_relevance_json" not in _nda_cols:
        cur15.execute("ALTER TABLE news_digest_articles ADD COLUMN ai_relevance_json TEXT")
    if "ai_processed_at_utc" not in _nda_cols:
        cur15.execute("ALTER TABLE news_digest_articles ADD COLUMN ai_processed_at_utc TEXT")
    # Drop legacy created_at_utc if present (SQLite 3.35+).
    if "created_at_utc" in _nda_cols:
        try:
            cur15.execute("ALTER TABLE news_digest_articles DROP COLUMN created_at_utc")
        except sqlite3.OperationalError:
            pass
    cur15.execute("DROP INDEX IF EXISTS idx_news_digest_articles_created")
    cur15.execute("""
        CREATE INDEX IF NOT EXISTS idx_news_digest_articles_last_seen
        ON news_digest_articles (last_seen_at_utc DESC)
    """)
    cur15.execute("""
        CREATE INDEX IF NOT EXISTS idx_news_digest_articles_first_seen
        ON news_digest_articles (first_seen_at_utc DESC)
    """)

    cur16 = con.cursor()
    cur16.execute("""
        CREATE TABLE IF NOT EXISTS home_insights_cache (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            insight_text TEXT,
            sources_json TEXT NOT NULL DEFAULT '[]',
            generated_at_utc TEXT,
            model TEXT,
            error_text TEXT
        )
    """)

    con.commit()
    con.close()
    prune_error_logs()

# endregion


def insert_app_error(
    origin: str,
    source: str,
    message: str,
    detail: Optional[str] = None,
) -> None:
    """Append an app error row (client or server). See ENABLE_*_ERROR_LOG in server."""
    orig = (origin or "app")[:32]
    src = (source or "app")[:120]
    msg = (message or "")[:2000]
    det = None
    if detail is not None:
        det = str(detail)[:4000]
    created = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute(
            """
            INSERT INTO client_error_log (created_at, origin, source, message, detail)
            VALUES (?, ?, ?, ?, ?)
            """,
            (created, orig, src, msg, det),
        )
        con.commit()
    finally:
        con.close()


def insert_client_error(source: str, message: str, detail: Optional[str] = None) -> None:
    """Append a client-reported error (origin=client)."""
    insert_app_error("client", source, message, detail)


def prune_error_logs(retention_days: Optional[int] = None) -> int:
    """
    Delete error log rows older than retention (default ERROR_LOG_RETENTION_DAYS or 30).
    Set retention_days to 0 to skip pruning. Returns number of rows deleted.
    """
    if retention_days is None:
        raw = (os.getenv("ERROR_LOG_RETENTION_DAYS") or "30").strip()
        try:
            days = int(raw)
        except ValueError:
            days = 30
    else:
        days = retention_days
    if days <= 0:
        return 0
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S")
    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute("DELETE FROM client_error_log WHERE created_at < ?", (cutoff,))
        deleted = cur.rowcount if cur.rowcount is not None else 0
        con.commit()
        return int(deleted)
    except sqlite3.OperationalError:
        # Table may not exist yet on first migration path
        return 0
    finally:
        con.close()


# region UI and API Crud Operations
def get_all_records():
    """Retrieves all records from the finance_data table."""
    con = get_connection()
    cur = con.cursor()
    cur.execute("SELECT id, account_name, source_name, source_value FROM finance_data")
    records = cur.fetchall()
    con.close()
    return records

def insert_record(account_name, source_name, source_value):
    # Validate inputs
    if not re.match("^[a-zA-Z0-9_]+$", account_name):
        raise ValueError("Invalid account name")
    if not re.match("^[a-zA-Z0-9_]+$", source_name):
        raise ValueError("Invalid source name")
    try:
        source_value = float(source_value)
    except ValueError:
        raise ValueError("Source value must be a number")


    try:
        con = get_connection()
        cur = con.cursor()
        date_created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute('''
            INSERT INTO finance_data (account_name, source_name, source_value, date_created)
            VALUES (?, ?, ?, ?)
        ''', (account_name, source_name, float(source_value), date_created))
        con.commit()
    except sqlite3.DatabaseError as e:
        # Handle database errors
        print(f"Database error occurred: {e}")
    except Exception as e:
        # Handle other exceptions
        print(f"An error occurred: {e}")
    finally:
        if con:
            con.close()

def delete_record(row_id):
    # Validate inputs
    try:
        row_id = int(row_id)
    except ValueError:
        raise ValueError("Invalid row_id. It must be an integer.")
    try:
        con = get_connection()
        cur = con.cursor()
        print(f"Executing DELETE FROM finance_data WHERE id={row_id}")
        cur.execute('''
            DELETE FROM finance_data WHERE id=?
        ''', (row_id,))
        con.commit()
        print(f"Record with Id: {row_id} deleted from the database")
    except ValueError:
        print("Invalid row_id. It must be an integer.")
    except sqlite3.DatabaseError as e:
        print(f"Database error occurred: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        if con:
            con.close()

def insert_items(item_id, access_token):
     # Insert into items table (your existing functionality)
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS items (
            item_id TEXT PRIMARY KEY,
            access_token TEXT,
            institution_name TEXT,
            institution_id TEXT,
            first_linked_at_utc TEXT,
            updated_at_utc TEXT
        )
    """)
    _ensure_items_institution_columns(c)
    _ensure_items_timestamp_columns(c)
    now = _utc_now_iso()
    enc = _encrypt_plaid_access_token_at_rest(access_token)
    c.execute(
        """
        INSERT INTO items (item_id, access_token, first_linked_at_utc, updated_at_utc)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(item_id) DO UPDATE SET
            access_token = excluded.access_token,
            updated_at_utc = excluded.updated_at_utc
        """,
        (item_id, enc, now, now),
    )
    conn.commit()
    conn.close()


def update_item_institution(item_id, institution_name=None, institution_id=None):
    conn = get_connection()
    c = conn.cursor()
    _ensure_items_institution_columns(c)
    _ensure_items_timestamp_columns(c)
    c.execute(
        """
        UPDATE items
        SET institution_name = ?, institution_id = ?, updated_at_utc = ?
        WHERE item_id = ?
        """,
        (institution_name, institution_id, _utc_now_iso(), item_id),
    )
    conn.commit()
    conn.close()


def get_items():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS items (
            item_id TEXT PRIMARY KEY,
            access_token TEXT
        )
    """)
    _ensure_items_institution_columns(c)
    _ensure_items_timestamp_columns(c)
    c.execute(
        """
        SELECT item_id, access_token, institution_name, institution_id,
               first_linked_at_utc, updated_at_utc
        FROM items
        """
    )
    rows = c.fetchall()
    conn.close()
    return [
        {
            "item_id": row[0],
            "access_token": _decrypt_plaid_access_token_at_rest(row[1]),
            "institution_name": row[2],
            "institution_id": row[3],
            "first_linked_at_utc": row[4],
            "updated_at_utc": row[5],
        }
        for row in rows
    ]


def list_plaid_items_public():
    """Linked Plaid items for UI/API (no access tokens)."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS items (
            item_id TEXT PRIMARY KEY,
            access_token TEXT
        )
    """)
    _ensure_items_institution_columns(c)
    _ensure_items_timestamp_columns(c)
    c.execute(
        """
        SELECT item_id, institution_name, institution_id, first_linked_at_utc, updated_at_utc
        FROM items
        ORDER BY COALESCE(first_linked_at_utc, '') DESC, item_id
        """
    )
    rows = c.fetchall()
    conn.close()
    return [
        {
            "item_id": row[0],
            "institution_name": row[1],
            "institution_id": row[2],
            "first_linked_at_utc": row[3],
            "updated_at_utc": row[4],
        }
        for row in rows
    ]


def find_plaid_items_matching_institution(
    institution_id=None,
    institution_name=None,
    exclude_item_id=None,
):
    """
    Return full item dicts (including access_token) that match the same institution as
    a new link, excluding the new item_id. Used to replace stale Items on relink.
    """
    matches = []
    for row in get_items():
        if exclude_item_id and row["item_id"] == exclude_item_id:
            continue
        if institution_id and row.get("institution_id") == institution_id:
            matches.append(row)
        elif (
            not institution_id
            and institution_name
            and (row.get("institution_name") or "").strip().lower()
            == institution_name.strip().lower()
        ):
            matches.append(row)
    return matches


def delete_plaid_item_data(item_id: str) -> dict[str, int]:
    """Delete local accounts, transactions, holdings, and the items row for one Plaid item."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT account_id FROM accounts WHERE item_id = ?", (item_id,))
    account_ids = [r[0] for r in c.fetchall()]
    txn_deleted = 0
    holdings_deleted = 0
    if account_ids:
        q_marks = ",".join("?" * len(account_ids))
        c.execute(
            f"DELETE FROM transactions WHERE account_id IN ({q_marks})",
            account_ids,
        )
        txn_deleted = c.rowcount if c.rowcount is not None else 0
        c.execute(
            f"DELETE FROM plaid_holdings WHERE account_id IN ({q_marks})",
            account_ids,
        )
        holdings_deleted = c.rowcount if c.rowcount is not None else 0
    c.execute("DELETE FROM accounts WHERE item_id = ?", (item_id,))
    accounts_deleted = c.rowcount if c.rowcount is not None else 0
    c.execute("DELETE FROM items WHERE item_id = ?", (item_id,))
    items_deleted = c.rowcount if c.rowcount is not None else 0
    conn.commit()
    conn.close()
    return {
        "transactions_deleted": txn_deleted,
        "plaid_holdings_deleted": holdings_deleted,
        "accounts_deleted": accounts_deleted,
        "items_deleted": items_deleted,
    }


def get_plaid_item_by_id(item_id: str) -> Optional[dict[str, Any]]:
    """Single linked item including decrypted access token, or None."""
    for row in get_items():
        if row["item_id"] == item_id:
            return row
    return None


def store_accounts(accounts, item_id=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("PRAGMA table_info(accounts)")
    account_columns = [row[1] for row in c.fetchall()]
    if "item_id" not in account_columns:
        c.execute("ALTER TABLE accounts ADD COLUMN item_id TEXT")
    _ensure_accounts_timestamp_columns(c)
    now = _utc_now_iso()
    for account in accounts:
        c.execute(
            """
            INSERT INTO accounts (
                account_id, name, official_name, type, subtype, current_balance, item_id,
                first_seen_at_utc, updated_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id) DO UPDATE SET
                name = excluded.name,
                official_name = excluded.official_name,
                type = excluded.type,
                subtype = excluded.subtype,
                current_balance = excluded.current_balance,
                item_id = excluded.item_id,
                updated_at_utc = excluded.updated_at_utc
            """,
            (
                account.account_id,
                account.name,
                account.official_name,
                str(account.type),
                str(account.subtype),
                account.balances.current,
                item_id,
                now,
                now,
            ),
        )
    conn.commit()
    conn.close()


def get_institutions():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS items (
            item_id TEXT PRIMARY KEY,
            access_token TEXT,
            institution_name TEXT,
            institution_id TEXT
        )
    """)
    c.execute("SELECT DISTINCT institution_name FROM items WHERE institution_name IS NOT NULL")
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]


def upsert_plaid_holding(account_id, ticker, shares, cost_basis=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO plaid_holdings (account_id, ticker, shares, cost_basis)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(account_id, ticker) DO UPDATE SET
            shares = excluded.shares,
            cost_basis = excluded.cost_basis
        """,
        (account_id, ticker, shares, cost_basis),
    )
    conn.commit()
    conn.close()


def get_plaid_holdings(institution_name=None):
    conn = get_connection()
    params = []
    where_clause = ""
    if institution_name:
        where_clause = "WHERE i.institution_name = ?"
        params.append(institution_name)
    query = f"""
        SELECT
            h.account_id,
            COALESCE(a.official_name, a.name) AS account_name,
            i.institution_name,
            h.ticker,
            h.shares,
            COALESCE(h.cost_basis, 0) AS cost_basis,
            sp.closing_price AS latest_price,
            (h.shares * sp.closing_price) AS position_value,
            ((h.shares * sp.closing_price) - COALESCE(h.cost_basis, 0)) AS gain_loss,
            CASE
                WHEN COALESCE(h.cost_basis, 0) = 0 THEN NULL
                ELSE ((h.shares * sp.closing_price) - COALESCE(h.cost_basis, 0)) / COALESCE(h.cost_basis, 0)
            END AS gain_loss_pct
        FROM plaid_holdings h
        LEFT JOIN accounts a
            ON a.account_id = h.account_id
        LEFT JOIN items i
            ON i.item_id = a.item_id
        LEFT JOIN (
            SELECT ticker, MAX(date) AS max_date
            FROM stock_prices
            GROUP BY ticker
        ) latest
            ON latest.ticker = h.ticker
        LEFT JOIN stock_prices sp
            ON sp.ticker = h.ticker
           AND sp.date = latest.max_date
        {where_clause}
    """
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def wipe_all_data(force: bool = False):
    db_path = str(DATABASE)
    if not force and "test" not in db_path.lower():
        raise RuntimeError("Refusing to wipe non-test database without force=True.")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing_tables = {row[0] for row in cur.fetchall()}

    def _safe_delete(table_name):
        if table_name in existing_tables:
            cur.execute(f"DELETE FROM {table_name}")

    cur.execute("DELETE FROM finance_data")
    cur.execute("DELETE FROM Stocks")
    cur.execute("DELETE FROM stock_prices")
    cur.execute("DELETE FROM stock_metadata")
    cur.execute("DELETE FROM realized_gains")
    cur.execute("DELETE FROM accounts")
    cur.execute("DELETE FROM transactions")
    _safe_delete("items")
    _safe_delete("plaid_holdings")
    _safe_delete("price_update_log")
    _safe_delete("benchmark_prices")
    _safe_delete("etf_sector_breakdown")
    _safe_delete("etf_sources")
    _safe_delete("sec_filing_summaries")
    _safe_delete("client_error_log")
    _safe_delete("news_digest_articles")
    _safe_delete("home_insights_cache")
    conn.commit()
    conn.close()

def insert_transactions(transactions):
    # Connect to SQLite and insert each transaction
    conn = get_connection()
    c = conn.cursor()
    for txn in transactions:
        # Concatenate categories if present
        category = ", ".join(txn.category) if txn.category else ""
        c.execute("""
            INSERT OR REPLACE INTO transactions 
            (transaction_id, account_id, amount, date, name, category)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            txn.transaction_id,
            txn.account_id,
            txn.amount,
            txn.date,
            txn.name,
            category
        ))
    conn.commit()
    conn.close()
#endregion


def get_sec_summary(doc_hash: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT doc_hash, ticker, filing_type, filing_date, source_path, summary_text, model, created_at
        FROM sec_filing_summaries
        WHERE doc_hash = ?
        """,
        (doc_hash,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "doc_hash": row[0],
        "ticker": row[1],
        "filing_type": row[2],
        "filing_date": row[3],
        "source_path": row[4],
        "summary_text": row[5],
        "model": row[6],
        "created_at": row[7],
    }


def upsert_sec_summary(
    doc_hash: str,
    ticker: str,
    filing_type: str,
    filing_date: str,
    source_path: str,
    summary_text: str,
    model: str,
):
    conn = get_connection()
    cur = conn.cursor()
    created_at = datetime.now(timezone.utc).isoformat()
    cur.execute(
        """
        INSERT INTO sec_filing_summaries
            (doc_hash, ticker, filing_type, filing_date, source_path, summary_text, model, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(doc_hash) DO UPDATE SET
            ticker=excluded.ticker,
            filing_type=excluded.filing_type,
            filing_date=excluded.filing_date,
            source_path=excluded.source_path,
            summary_text=excluded.summary_text,
            model=excluded.model,
            created_at=excluded.created_at
        """,
        (doc_hash, ticker, filing_type, filing_date, source_path, summary_text, model, created_at),
    )
    conn.commit()
    conn.close()


def get_sec_summaries(limit: int = 50, ticker: Optional[str] = None, filing_type: Optional[str] = None):
    conn = get_connection()
    cur = conn.cursor()
    where = []
    params = []
    if ticker:
        where.append("ticker = ?")
        params.append(ticker)
    if filing_type:
        where.append("filing_type = ?")
        params.append(filing_type)
    where_clause = f"WHERE {' AND '.join(where)}" if where else ""
    cur.execute(
        f"""
        SELECT doc_hash, ticker, filing_type, filing_date, source_path, summary_text, model, created_at
        FROM sec_filing_summaries
        {where_clause}
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (*params, limit),
    )
    rows = cur.fetchall()
    conn.close()
    results = []
    for row in rows:
        results.append({
            "doc_hash": row[0],
            "ticker": row[1],
            "filing_type": row[2],
            "filing_date": row[3],
            "source_path": row[4],
            "summary_text": row[5],
            "model": row[6],
            "created_at": row[7],
        })
    return results


def delete_sec_summaries(ticker: Optional[str] = None, filing_type: Optional[str] = None):
    conn = get_connection()
    cur = conn.cursor()
    where = []
    params = []
    if ticker:
        where.append("ticker = ?")
        params.append(ticker)
    if filing_type:
        where.append("filing_type = ?")
        params.append(filing_type)
    where_clause = f"WHERE {' AND '.join(where)}" if where else ""
    cur.execute(f"DELETE FROM sec_filing_summaries {where_clause}", params)
    conn.commit()
    conn.close()


def prune_sec_filing_summaries(retention_days: Optional[int] = None) -> int:
    """
    Delete summary rows whose ``created_at`` is older than ``retention_days`` (UTC).

    Default comes from env ``SEC_FILING_SUMMARY_RETENTION_DAYS`` (default **365**).
    Set to ``0`` to disable automatic pruning. Summaries are kept longer than raw
    downloaded filing files (see ``SEC_FILINGS_RETENTION_DAYS`` in ``services/filings.py``).
    """
    if retention_days is None:
        raw = (os.getenv("SEC_FILING_SUMMARY_RETENTION_DAYS") or "365").strip()
        try:
            retention_days = int(raw)
        except ValueError:
            retention_days = 365
    if retention_days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    cutoff_s = cutoff.isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        DELETE FROM sec_filing_summaries
        WHERE created_at IS NOT NULL AND created_at < ?
        """,
        (cutoff_s,),
    )
    deleted = cur.rowcount if cur.rowcount is not None else 0
    conn.commit()
    conn.close()
    return int(deleted)


def get_home_insights() -> Optional[dict[str, Any]]:
    """Single-row cache for Groq cross-insights on the home page."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT insight_text, sources_json, generated_at_utc, model, error_text
        FROM home_insights_cache WHERE id = 1
        """
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    try:
        sources = json.loads(row[1] or "[]")
    except json.JSONDecodeError:
        sources = []
    if not isinstance(sources, list):
        sources = []
    return {
        "insight_text": row[0],
        "sources": sources,
        "generated_at_utc": row[2],
        "model": row[3],
        "error_text": row[4],
    }


def upsert_home_insights(
    insight_text: Optional[str],
    sources: list[dict[str, Any]],
    model: str,
    error_text: Optional[str] = None,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    cur.execute(
        """
        INSERT INTO home_insights_cache (id, insight_text, sources_json, generated_at_utc, model, error_text)
        VALUES (1, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            insight_text = excluded.insight_text,
            sources_json = excluded.sources_json,
            generated_at_utc = excluded.generated_at_utc,
            model = excluded.model,
            error_text = excluded.error_text
        """,
        (
            insight_text,
            json.dumps(sources, ensure_ascii=False),
            now,
            (model or "")[:120],
            error_text,
        ),
    )
    conn.commit()
    conn.close()


# region Data Retrieval for Dash App using Pandas DataFrame
def get_account_balances():
    # Connect to your SQLite database
    conn = get_connection()
    # Write your query - adjust column names as needed
    query = "SELECT account_id, current_balance FROM accounts"
    # Load data into a Pandas DataFrame
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def get_all_records_df():
    """Retrieves all records from the finance_data table."""
    con = get_connection()
    query = "SELECT id, account_name, source_name, source_value,date_created FROM finance_data"
    df = pd.read_sql_query(query, con)
    con.close()
    return df
# endregion


#region Stock Data
def get_held_stock_tickers():
    """
    Distinct tickers from the manual ``Stocks`` table (Manage Stocks), uppercase, sorted.
    Used for portfolio-aware matching (e.g. news digest) without a separate symbol file.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT UPPER(TRIM(ticker)) AS t
        FROM Stocks
        WHERE TRIM(COALESCE(ticker, '')) != ''
        ORDER BY t
        """
    )
    rows = [r[0] for r in cur.fetchall() if r[0]]
    conn.close()
    return rows


def get_plaid_holdings_tickers():
    """
    Distinct tickers from ``plaid_holdings`` (linked brokerage positions), uppercase, sorted.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT UPPER(TRIM(ticker)) AS t
        FROM plaid_holdings
        WHERE TRIM(COALESCE(ticker, '')) != ''
        ORDER BY t
        """
    )
    rows = [r[0] for r in cur.fetchall() if r[0]]
    conn.close()
    return rows


_TRACKING_QUERY_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "_ga",
        "igshid",
    }
)


def normalize_news_article_url_string(url: str) -> str:
    """
    Strip common tracking query params, normalize host casing, stable query ordering.
    ``news:nolink:`` keys are returned unchanged.
    """
    u = (url or "").strip()
    if not u or u.startswith("news:nolink:"):
        return u
    try:
        if "://" not in u:
            u = "https://" + u
        p = urlparse(u)
        netloc = (p.netloc or "").lower()
        path = p.path or ""
        if len(path) > 1 and path.endswith("/"):
            path = path.rstrip("/")
        q = parse_qs(p.query, keep_blank_values=False)
        pairs: list[tuple[str, str]] = []
        for k, vals in q.items():
            if k.lower() in _TRACKING_QUERY_PARAMS:
                continue
            for v in vals:
                pairs.append((k, v))
        pairs.sort(key=lambda x: (x[0].lower(), x[1]))
        new_query = urlencode(pairs) if pairs else ""
        scheme = (p.scheme or "https").lower()
        return urlunparse((scheme, netloc, path, p.params or "", new_query, ""))
    except Exception:
        return (url or "").strip()


def canonical_news_article_url(item: dict[str, Any]) -> str:
    """Stable row key: normalized URL, or ``news:nolink:<hash>`` when RSS has no link."""
    link = (item.get("link") or "").strip()
    if link:
        return normalize_news_article_url_string(link)
    title = (item.get("title") or "").strip()
    h = hashlib.sha256(title.encode("utf-8")).hexdigest()[:16]
    return f"news:nolink:{h}"


def news_digest_urls_with_null_summary(urls: list[str]) -> set[str]:
    """
    Among the given canonical article URLs, return those already stored with NULL or blank ``summary``.
    Used to prioritize HTML snippet fetches for rows still missing RSS body text.
    """
    cleaned = [str(u).strip() for u in urls if u and str(u).strip()]
    if not cleaned:
        return set()
    conn = get_connection()
    cur = conn.cursor()
    placeholders = ",".join("?" * len(cleaned))
    cur.execute(
        f"""
        SELECT url FROM news_digest_articles
        WHERE url IN ({placeholders})
          AND (summary IS NULL OR TRIM(summary) = '')
        """,
        cleaned,
    )
    out = {row[0] for row in cur.fetchall()}
    conn.close()
    return out


def upsert_news_digest_articles_from_digest(digest: dict[str, Any]) -> int:
    """
    Persist digest items (same fields as the home table). Upsert by normalized ``url``;
    ``first_seen_at_utc`` is set on first insert only; ``last_seen_at_utc`` updated on repeats.
    ``summary`` stores the RSS body text so re-tagging can match tickers later.
    """
    items = digest.get("items") or []
    if not items:
        return 0
    generated = (digest.get("generated_at_utc") or "").strip() or datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    cur = conn.cursor()
    n = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        url = canonical_news_article_url(it)
        title = (it.get("title") or "").strip() or "(no title)"
        src = (it.get("source_feed") or "").strip() or None
        cats = it.get("categories") if isinstance(it.get("categories"), list) else []
        tickers = it.get("tickers") if isinstance(it.get("tickers"), list) else []
        tc = it.get("ticker_companies") if isinstance(it.get("ticker_companies"), dict) else {}
        summary = (it.get("summary_text") or "").strip() or None
        cur.execute(
            """
            INSERT INTO news_digest_articles (
                url, title, source_feed, categories_json, tickers_json, ticker_companies_json,
                first_seen_at_utc, last_seen_at_utc, summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title = excluded.title,
                source_feed = excluded.source_feed,
                categories_json = excluded.categories_json,
                tickers_json = excluded.tickers_json,
                ticker_companies_json = excluded.ticker_companies_json,
                last_seen_at_utc = excluded.last_seen_at_utc,
                summary = COALESCE(excluded.summary, news_digest_articles.summary)
            """,
            (
                url,
                title,
                src,
                json.dumps(cats, ensure_ascii=False),
                json.dumps(tickers, ensure_ascii=False),
                json.dumps(tc, ensure_ascii=False),
                generated,
                generated,
                summary,
            ),
        )
        n += 1
    conn.commit()
    conn.close()
    return n


def update_news_digest_article_tickers(
    url: str,
    tickers: list[str],
    ticker_companies: dict[str, str],
) -> bool:
    """Update stored ticker tags for a row (used after re-matching holdings against title/summary)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE news_digest_articles
        SET tickers_json = ?, ticker_companies_json = ?
        WHERE url = ?
        """,
        (
            json.dumps(tickers, ensure_ascii=False),
            json.dumps(ticker_companies, ensure_ascii=False),
            url,
        ),
    )
    changed = cur.rowcount if cur.rowcount is not None else 0
    conn.commit()
    conn.close()
    return bool(changed)


def recent_news_digest_articles_with_null_summary(days: int = 2) -> list[dict[str, Any]]:
    """
    Return articles from the last *days* (by ``first_seen_at_utc``) that still have no summary.
    Each dict has ``url``, ``title``, ``link`` (alias for url).
    """
    conn = get_connection()
    cur = conn.cursor()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    cur.execute(
        """
        SELECT url, title FROM news_digest_articles
        WHERE (summary IS NULL OR TRIM(summary) = '')
          AND first_seen_at_utc >= ?
        ORDER BY first_seen_at_utc DESC
        """,
        (cutoff,),
    )
    rows = cur.fetchall()
    conn.close()
    return [{"url": r[0], "title": r[1], "link": r[0]} for r in rows]


def update_news_digest_article_summary(url: str, summary: str) -> bool:
    """Set the ``summary`` column for one article. Returns True if a row was updated."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE news_digest_articles SET summary = ? WHERE url = ?",
        (summary, url),
    )
    changed = cur.rowcount if cur.rowcount is not None else 0
    conn.commit()
    conn.close()
    return bool(changed)


def list_news_digest_articles_pending_ai(
    days: int = 2,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Recent articles that have not yet been processed by the holdings-relevance LLM.
    Returns rows with ``url``, ``title``, ``summary`` (may be null).
    """
    conn = get_connection()
    cur = conn.cursor()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    lim = max(1, min(int(limit), 50))
    cur.execute(
        """
        SELECT url, title, summary FROM news_digest_articles
        WHERE (ai_processed_at_utc IS NULL OR TRIM(ai_processed_at_utc) = '')
          AND first_seen_at_utc >= ?
        ORDER BY first_seen_at_utc DESC
        LIMIT ?
        """,
        (cutoff, lim),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {"url": r[0], "title": r[1], "summary": r[2]}
        for r in rows
    ]


def update_news_digest_article_ai_relevance(
    url: str,
    relevance: dict[str, Any],
    processed_at_utc: str,
) -> bool:
    """Persist Groq (or other) holdings-relevance JSON and processing timestamp."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE news_digest_articles
        SET ai_relevance_json = ?, ai_processed_at_utc = ?
        WHERE url = ?
        """,
        (json.dumps(relevance, ensure_ascii=False), processed_at_utc, url),
    )
    changed = cur.rowcount if cur.rowcount is not None else 0
    conn.commit()
    conn.close()
    return bool(changed)


def prune_news_digest_articles(retention_days: Optional[int] = None) -> int:
    """
    Delete rows whose ``first_seen_at_utc`` is older than ``retention_days`` (default 90, UTC).
    Set env ``NEWS_DIGEST_RETENTION_DAYS`` to override; set to ``0`` to disable pruning.
    """
    if retention_days is None:
        raw = (os.getenv("NEWS_DIGEST_RETENTION_DAYS") or "90").strip()
        try:
            retention_days = int(raw)
        except ValueError:
            retention_days = 90
    if retention_days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    cutoff_s = cutoff.isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        DELETE FROM news_digest_articles
        WHERE first_seen_at_utc < ?
        """,
        (cutoff_s,),
    )
    deleted = cur.rowcount if cur.rowcount is not None else 0
    conn.commit()
    conn.close()
    return int(deleted)


def news_digest_schedule_tz() -> ZoneInfo:
    """Same calendar-day semantics as ``NEWS_DIGEST_TZ`` in ``api/news_digest``."""
    try:
        load_dotenv = __import__("dotenv", fromlist=["load_dotenv"]).load_dotenv
        load_dotenv()
    except Exception:
        pass
    name = (os.getenv("NEWS_DIGEST_TZ") or "America/New_York").strip()
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("UTC")


def local_day_start_end_utc_iso(local_date: str) -> tuple[str, str]:
    """``local_date`` ``YYYY-MM-DD`` in :func:`news_digest_schedule_tz`; return UTC ISO bounds ``[start, end)``."""
    tz = news_digest_schedule_tz()
    d = datetime.strptime(local_date.strip(), "%Y-%m-%d").date()
    start_local = datetime.combine(d, datetime.min.time(), tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(timezone.utc).isoformat(),
        end_local.astimezone(timezone.utc).isoformat(),
    )


def _news_digest_item_dict_from_row(r: tuple[Any, ...]) -> dict[str, Any]:
    url = r[0]
    cats = json.loads(r[3] or "[]")
    syms = json.loads(r[4] or "[]")
    tc = json.loads(r[5] or "{}")
    ai_rel: Optional[dict[str, Any]] = None
    if len(r) > 9 and r[9]:
        try:
            parsed = json.loads(r[9])
            if isinstance(parsed, dict):
                ai_rel = parsed
        except json.JSONDecodeError:
            ai_rel = None
    return {
        "url": url,
        "title": r[1],
        "link": "" if str(url).startswith("news:nolink:") else url,
        "source_feed": r[2] or "",
        "categories": cats,
        "tickers": syms,
        "ticker_companies": tc,
        "first_seen_at_utc": r[6],
        "last_seen_at_utc": r[7],
        "summary": r[8],
        "ai_relevance": ai_rel,
        "ai_processed_at_utc": (r[10] if len(r) > 10 else None) or None,
    }


def list_news_digest_local_dates_desc() -> list[dict[str, Any]]:
    """
    Distinct calendar days (``NEWS_DIGEST_TZ``) that have at least one article, newest first.
    Each item: ``{ "date": "YYYY-MM-DD", "count": int }``.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT first_seen_at_utc FROM news_digest_articles")
    rows = cur.fetchall()
    conn.close()
    tz = news_digest_schedule_tz()
    counts: dict[str, int] = {}
    for (iso,) in rows:
        if not iso:
            continue
        try:
            dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local_d = dt.astimezone(tz).date().isoformat()
        counts[local_d] = counts.get(local_d, 0) + 1
    out = [{"date": k, "count": counts[k]} for k in sorted(counts.keys(), reverse=True)]
    return out


def news_digest_local_date_neighbors(
    sorted_dates_asc: list[str], current: str
) -> tuple[Optional[str], Optional[str]]:
    """
    ``sorted_dates_asc`` is distinct ``YYYY-MM-DD`` values ascending.
    Returns ``(older_date, newer_date)``: older = further in the past, newer = closer to today.
    If ``current`` has no rows but falls between two days with data, neighbors jump to those days.
    """
    asc = sorted_dates_asc
    if not asc:
        return None, None
    if current in asc:
        idx = asc.index(current)
        return (asc[idx - 1] if idx > 0 else None, asc[idx + 1] if idx + 1 < len(asc) else None)
    pos = bisect.bisect_left(asc, current)
    older = asc[pos - 1] if pos > 0 else None
    newer = asc[pos] if pos < len(asc) else None
    return older, newer


def today_local_iso_digest_tz() -> str:
    """Today's calendar date ``YYYY-MM-DD`` in :func:`news_digest_schedule_tz`."""
    now = datetime.now(news_digest_schedule_tz())
    return now.date().isoformat()


def list_news_digest_articles_for_local_date(local_date: str) -> list[dict[str, Any]]:
    """All articles whose ``first_seen_at_utc`` falls on ``local_date`` in the digest schedule timezone."""
    start_iso, end_iso = local_day_start_end_utc_iso(local_date)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT url, title, source_feed, categories_json, tickers_json, ticker_companies_json,
               first_seen_at_utc, last_seen_at_utc, summary, ai_relevance_json, ai_processed_at_utc
        FROM news_digest_articles
        WHERE first_seen_at_utc >= ? AND first_seen_at_utc < ?
        ORDER BY first_seen_at_utc DESC
        """,
        (start_iso, end_iso),
    )
    rows_out = [_news_digest_item_dict_from_row(r) for r in cur.fetchall()]
    conn.close()
    return rows_out


def list_news_digest_articles(
    page: int = 1,
    per_page: int = 20,
    category: Optional[str] = None,
    ticker: Optional[str] = None,
    sort: str = "created",
) -> tuple[list[dict[str, Any]], int, int]:
    """
    Paginated history for the news table. Optional filters: category slug (e.g. ``rates``),
    ticker symbol (e.g. ``MSFT``). ``sort``: ``created`` (default) by ``first_seen_at_utc``,
    or ``last_seen`` by ``last_seen_at_utc``. Returns (rows, total_count, per_page_effective).
    """
    page = max(1, int(page))
    per_page = min(max(1, int(per_page)), 100)
    offset = (page - 1) * per_page
    sort_key = (sort or "created").strip().lower()
    if sort_key not in ("created", "last_seen"):
        sort_key = "created"

    where_parts: list[str] = []
    params: list[Any] = []
    if category and str(category).strip():
        where_parts.append(
            "EXISTS (SELECT 1 FROM json_each(categories_json) WHERE LOWER(value) = ?)"
        )
        params.append(str(category).strip().lower())
    if ticker and str(ticker).strip():
        where_parts.append(
            "EXISTS (SELECT 1 FROM json_each(tickers_json) WHERE UPPER(value) = ?)"
        )
        params.append(str(ticker).strip().upper())

    where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
    order_sql = (
        "ORDER BY last_seen_at_utc DESC"
        if sort_key == "last_seen"
        else "ORDER BY first_seen_at_utc DESC"
    )

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM news_digest_articles{where_sql}", params)
    total = int(cur.fetchone()[0])

    cur.execute(
        f"""
        SELECT url, title, source_feed, categories_json, tickers_json, ticker_companies_json,
               first_seen_at_utc, last_seen_at_utc, summary, ai_relevance_json, ai_processed_at_utc
        FROM news_digest_articles
        {where_sql}
        {order_sql}
        LIMIT ? OFFSET ?
        """,
        params + [per_page, offset],
    )
    rows_out = [_news_digest_item_dict_from_row(r) for r in cur.fetchall()]
    conn.close()
    return rows_out, total, per_page


def get_stocks():
    conn = get_connection()
    query = """
        SELECT
            s.id,
            s.ticker,
            s.shares,
            COALESCE(s.cost_basis, 0) AS cost_basis,
            sp.closing_price AS latest_price,
            (s.shares * sp.closing_price) AS position_value,
            ((s.shares * sp.closing_price) - COALESCE(s.cost_basis, 0)) AS gain_loss,
            CASE
                WHEN COALESCE(s.cost_basis, 0) = 0 THEN NULL
                ELSE ((s.shares * sp.closing_price) - COALESCE(s.cost_basis, 0)) / COALESCE(s.cost_basis, 0)
            END AS gain_loss_pct
        FROM Stocks s
        LEFT JOIN (
            SELECT ticker, MAX(date) AS max_date
            FROM stock_prices
            GROUP BY ticker
        ) latest
            ON latest.ticker = s.ticker
        LEFT JOIN stock_prices sp
            ON sp.ticker = s.ticker
           AND sp.date = latest.max_date
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_sector_map(tickers):
    if not tickers:
        return {}
    conn = get_connection()
    placeholders = ",".join("?" for _ in tickers)
    query = f"""
        SELECT ticker, sector
        FROM stock_metadata
        WHERE ticker IN ({placeholders})
    """
    df = pd.read_sql_query(query, conn, params=tickers)
    conn.close()
    return dict(zip(df["ticker"], df["sector"])) if not df.empty else {}

def get_sector_records(tickers):
    if not tickers:
        return {}
    conn = get_connection()
    placeholders = ",".join("?" for _ in tickers)
    query = f"""
        SELECT ticker, sector, updated_at
        FROM stock_metadata
        WHERE ticker IN ({placeholders})
    """
    df = pd.read_sql_query(query, conn, params=tickers)
    conn.close()
    if df.empty:
        return {}
    return {row["ticker"]: {"sector": row["sector"], "updated_at": row["updated_at"]} for _, row in df.iterrows()}

def upsert_stock_sector(ticker, sector, updated_at):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO stock_metadata (ticker, sector, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(ticker) DO UPDATE SET
            sector = excluded.sector,
            updated_at = excluded.updated_at
    """, (ticker, sector, updated_at))
    conn.commit()
    conn.close()

def get_duplicate_stocks_df():
    conn = get_connection()
    query = """
        SELECT
            ticker,
            COUNT(*) AS occurrences,
            SUM(shares) AS total_shares,
            SUM(COALESCE(cost_basis, 0)) AS total_cost_basis
        FROM Stocks
        GROUP BY ticker
        HAVING COUNT(*) > 1
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_value_stocks():
    conn = get_connection()
    # activeStocks = "SELECT id,ticker,shares FROM Stocks"
    # activeStocksList = pd.read_sql_query(activeStocks, conn)

    # getStockPrices = "SELECT ticker, date, closing_price FROM stock_prices"
    # stockPricesList = pd.read_sql_query(getStockPrices, conn)

    query = """
        SELECT
            s.ticker,
            s.total_shares AS shares,
            sp.date,
            sp.closing_price
        FROM (
            SELECT ticker, SUM(shares) AS total_shares
            FROM Stocks
            GROUP BY ticker
        ) s
        JOIN stock_prices sp
            ON s.ticker = sp.ticker
        JOIN (
            SELECT ticker, MAX(date) AS max_date
            FROM stock_prices
            GROUP BY ticker
        ) latest
            ON latest.ticker = sp.ticker
           AND latest.max_date = sp.date
        """
    df = pd.read_sql_query(query, conn)
    conn.close()
    df['position_value'] = df['shares'] * df['closing_price']
    return df

def get_stock_prices_df():
    conn = get_connection()
    query = "SELECT ticker, date, closing_price FROM stock_prices"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def get_portfolio_value_history():
    conn = get_connection()
    query = """
        SELECT
            sp.date,
            sp.ticker,
            sp.closing_price,
            s.total_shares AS shares
        FROM stock_prices sp
        JOIN (
            SELECT ticker, SUM(shares) AS total_shares
            FROM Stocks
            GROUP BY ticker
        ) s
            ON sp.ticker = s.ticker
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    if df.empty:
        return df
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["closing_price"] = pd.to_numeric(df["closing_price"], errors="coerce")
    df["shares"] = pd.to_numeric(df["shares"], errors="coerce")
    df["position_value"] = df["shares"] * df["closing_price"]
    portfolio = (
        df.groupby("date", as_index=False)["position_value"]
        .sum()
        .rename(columns={"position_value": "portfolio_value"})
        .sort_values("date")
    )
    return portfolio


def get_stock_price_series(ticker):
    conn = get_connection()
    query = "SELECT date, closing_price FROM stock_prices WHERE ticker = ?"
    df = pd.read_sql_query(query, conn, params=(ticker,))
    conn.close()
    if df.empty:
        return df
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["closing_price"] = pd.to_numeric(df["closing_price"], errors="coerce")
    return df.sort_values("date")


def get_benchmark_price_series(symbol):
    conn = get_connection()
    query = "SELECT date, closing_price FROM benchmark_prices WHERE symbol = ?"
    df = pd.read_sql_query(query, conn, params=(symbol,))
    conn.close()
    if df.empty:
        return df
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["closing_price"] = pd.to_numeric(df["closing_price"], errors="coerce")
    return df.sort_values("date")


def upsert_benchmark_price(symbol, date, closing_price, source=None, updated_at=None):
    conn = get_connection()
    cur = conn.cursor()
    if updated_at is None:
        updated_at = datetime.now(timezone.utc).isoformat()
    cur.execute(
        "SELECT id FROM benchmark_prices WHERE symbol = ? AND date = ?",
        (symbol, date),
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            """
            UPDATE benchmark_prices
            SET closing_price = ?, source = ?, updated_at = ?
            WHERE symbol = ? AND date = ?
            """,
            (closing_price, source, updated_at, symbol, date),
        )
    else:
        cur.execute(
            """
            INSERT INTO benchmark_prices (symbol, date, closing_price, source, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (symbol, date, closing_price, source, updated_at),
        )
    conn.commit()
    conn.close()


def get_etf_sector_breakdown(symbol):
    conn = get_connection()
    query = """
        SELECT sector, weight, source, updated_at
        FROM etf_sector_breakdown
        WHERE symbol = ?
    """
    df = pd.read_sql_query(query, conn, params=(symbol,))
    conn.close()
    if df.empty:
        return df
    df = df.copy()
    df["weight"] = pd.to_numeric(df["weight"], errors="coerce")
    return df


def clear_etf_sector_breakdown(symbol):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM etf_sector_breakdown WHERE symbol = ?", (symbol,))
    conn.commit()
    conn.close()


def upsert_etf_sector_breakdown(symbol, sector, weight, source=None, updated_at=None):
    conn = get_connection()
    cur = conn.cursor()
    if updated_at is None:
        updated_at = datetime.now(timezone.utc).isoformat()
    cur.execute(
        "SELECT id FROM etf_sector_breakdown WHERE symbol = ? AND sector = ?",
        (symbol, sector),
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            """
            UPDATE etf_sector_breakdown
            SET weight = ?, source = ?, updated_at = ?
            WHERE symbol = ? AND sector = ?
            """,
            (weight, source, updated_at, symbol, sector),
        )
    else:
        cur.execute(
            """
            INSERT INTO etf_sector_breakdown (symbol, sector, weight, source, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (symbol, sector, weight, source, updated_at),
        )
    conn.commit()
    conn.close()


def get_etf_sources():
    conn = get_connection()
    query = "SELECT symbol, source_type, url, updated_at FROM etf_sources"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def get_etf_source(symbol):
    conn = get_connection()
    query = "SELECT symbol, source_type, url, updated_at FROM etf_sources WHERE symbol = ?"
    df = pd.read_sql_query(query, conn, params=(symbol,))
    conn.close()
    if df.empty:
        return None
    return df.iloc[0].to_dict()


def upsert_etf_source(symbol, source_type, url=None, updated_at=None):
    if updated_at is None:
        updated_at = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT symbol FROM etf_sources WHERE symbol = ?",
        (symbol,),
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            """
            UPDATE etf_sources
            SET source_type = ?, url = ?, updated_at = ?
            WHERE symbol = ?
            """,
            (source_type, url, updated_at, symbol),
        )
    else:
        cur.execute(
            """
            INSERT INTO etf_sources (symbol, source_type, url, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (symbol, source_type, url, updated_at),
        )
    conn.commit()
    conn.close()

def delete_orphan_stock_prices():
    """
    Remove stock_prices rows for tickers that are no longer in Stocks.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM stock_prices
        WHERE ticker NOT IN (SELECT ticker FROM Stocks)
    """)
    conn.commit()
    conn.close()

def insert_stock(ticker, shares, cost_basis=None):
    """
    Insert a new stock record into the Stocks table.
    Returns the new stock's id.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO Stocks (ticker, shares, cost_basis) VALUES (?, ?, ?)",
        (ticker, shares, cost_basis),
    )
    conn.commit()
    stock_id = cur.lastrowid
    conn.close()
    return stock_id

def update_stock(stock_id, ticker=None, shares=None, cost_basis=None):
    """
    Update an existing stock record with the given id.
    """
    fields = []
    params = []
    if ticker is not None:
        fields.append("ticker = ?")
        params.append(ticker)
    if shares is not None:
        fields.append("shares = ?")
        params.append(shares)
    if cost_basis is not None:
        fields.append("cost_basis = ?")
        params.append(cost_basis)
    if not fields:
        return
    conn = get_connection()
    cur = conn.cursor()
    params.append(stock_id)
    cur.execute(f"UPDATE Stocks SET {', '.join(fields)} WHERE id = ?", params)
    conn.commit()
    conn.close()


def upsert_stock_by_ticker(ticker, shares, cost_basis=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, cost_basis FROM Stocks WHERE ticker = ?", (ticker,))
    row = cur.fetchone()
    if row:
        stock_id = row[0]
        existing_cost_basis = row[1]
        if cost_basis is None:
            cost_basis = existing_cost_basis
        cur.execute(
            "UPDATE Stocks SET shares = ?, cost_basis = ? WHERE id = ?",
            (shares, cost_basis, stock_id),
        )
    else:
        cur.execute(
            "INSERT INTO Stocks (ticker, shares, cost_basis) VALUES (?, ?, ?)",
            (ticker, shares, cost_basis),
        )
    conn.commit()
    conn.close()

def delete_stock(stock_id):
    """
    Delete the stock record with the given id from the Stocks table.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM Stocks WHERE id = ?", (stock_id,))
    conn.commit()
    conn.close()


def _compute_realized_gain(proceeds, cost_basis, fees):
    proceeds_val = float(proceeds) if proceeds is not None else 0.0
    cost_val = float(cost_basis) if cost_basis is not None else 0.0
    fees_val = float(fees) if fees is not None else 0.0
    gain = proceeds_val - cost_val - fees_val
    gain_pct = gain / cost_val if cost_val else None
    return gain, gain_pct


def insert_realized_gain(
    ticker,
    shares,
    proceeds,
    cost_basis,
    fees=None,
    buy_date=None,
    sell_date=None,
    tax_year=None,
):
    gain, gain_pct = _compute_realized_gain(proceeds, cost_basis, fees)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO realized_gains
            (ticker, shares, buy_date, sell_date, proceeds, cost_basis, fees, realized_gain, realized_gain_pct, tax_year)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ticker,
            shares,
            buy_date,
            sell_date,
            proceeds,
            cost_basis,
            fees,
            gain,
            gain_pct,
            tax_year,
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def update_realized_gain(
    gain_id,
    ticker=None,
    shares=None,
    proceeds=None,
    cost_basis=None,
    fees=None,
    buy_date=None,
    sell_date=None,
    tax_year=None,
):
    fields = []
    params = []
    if ticker is not None:
        fields.append("ticker = ?")
        params.append(ticker)
    if shares is not None:
        fields.append("shares = ?")
        params.append(shares)
    if buy_date is not None:
        fields.append("buy_date = ?")
        params.append(buy_date)
    if sell_date is not None:
        fields.append("sell_date = ?")
        params.append(sell_date)
    if proceeds is not None:
        fields.append("proceeds = ?")
        params.append(proceeds)
    if cost_basis is not None:
        fields.append("cost_basis = ?")
        params.append(cost_basis)
    if fees is not None:
        fields.append("fees = ?")
        params.append(fees)
    if tax_year is not None:
        fields.append("tax_year = ?")
        params.append(tax_year)

    recompute = proceeds is not None or cost_basis is not None or fees is not None
    if recompute:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT proceeds, cost_basis, fees FROM realized_gains WHERE id = ?",
            (gain_id,),
        )
        row = cur.fetchone()
        conn.close()
        current_proceeds = row[0] if row else 0.0
        current_cost_basis = row[1] if row else 0.0
        current_fees = row[2] if row else 0.0
        gain, gain_pct = _compute_realized_gain(
            proceeds if proceeds is not None else current_proceeds,
            cost_basis if cost_basis is not None else current_cost_basis,
            fees if fees is not None else current_fees,
        )
        fields.append("realized_gain = ?")
        params.append(gain)
        fields.append("realized_gain_pct = ?")
        params.append(gain_pct)

    if not fields:
        return
    conn = get_connection()
    cur = conn.cursor()
    params.append(gain_id)
    cur.execute(f"UPDATE realized_gains SET {', '.join(fields)} WHERE id = ?", params)
    conn.commit()
    conn.close()


def delete_realized_gain(gain_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM realized_gains WHERE id = ?", (gain_id,))
    conn.commit()
    conn.close()


def get_realized_gains(year=None):
    conn = get_connection()
    if year:
        query = "SELECT * FROM realized_gains WHERE tax_year = ?"
        df = pd.read_sql_query(query, conn, params=[year])
    else:
        query = "SELECT * FROM realized_gains"
        df = pd.read_sql_query(query, conn)
    conn.close()
    if df.empty:
        return df
    df["realized_gain"] = pd.to_numeric(df["realized_gain"], errors="coerce")
    df["realized_gain_pct"] = pd.to_numeric(df["realized_gain_pct"], errors="coerce")
    return df


def get_all_tickers():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ticker FROM Stocks")
    rows = cursor.fetchall()
    conn.close()
    # Return a list of ticker strings
    return [row[0] for row in rows]

def insert_stock_price(ticker, date, closing_price):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO stock_prices (ticker, date, closing_price)
        VALUES (?, ?, ?)
    """, (ticker, date, closing_price))
    conn.commit()
    conn.close()

def upsert_stock_price(ticker, date, closing_price):
    """
    Update the existing row for (ticker, date) if present; otherwise insert it.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM stock_prices WHERE ticker = ? AND date = ?
    """, (ticker, date))
    row = cursor.fetchone()
    if row:
        cursor.execute("""
            UPDATE stock_prices
            SET closing_price = ?
            WHERE id = ?
        """, (closing_price, row[0]))
    else:
        cursor.execute("""
            INSERT INTO stock_prices (ticker, date, closing_price)
            VALUES (?, ?, ?)
        """, (ticker, date, closing_price))
    conn.commit()
    conn.close()

def get_last_update():
    """
    Retrieves the last_run_date from price_update_log.
    Returns the date as a string in ISO format (YYYY-MM-DD) or None if not set.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # # Check if the price_update_log table exists
    # cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='price_update_log'")
    # if cursor.fetchone() is None:
    #     conn.close()
    #     return None

    cursor.execute("SELECT last_run_date FROM price_update_log ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def set_last_update(date_str):
    """
    Sets or updates the last_run_date in the price_update_log table.
    If a record exists, updates it; otherwise, inserts a new record.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check if there's already a record in price_update_log
    cursor.execute("SELECT id FROM price_update_log LIMIT 1")
    row = cursor.fetchone()
    
    if row:
        # Update the existing record
        cursor.execute("UPDATE price_update_log SET last_run_date = ? WHERE id = ?", (date_str, row[0]))
    else:
        # Insert a new record
        cursor.execute("INSERT INTO price_update_log (last_run_date) VALUES (?)", (date_str,))
    
    conn.commit()
    conn.close()

#endregion