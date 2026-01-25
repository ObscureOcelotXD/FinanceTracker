import sqlite3
from datetime import datetime
import sqlite3
import pandas as pd
import re
DATABASE = "finance_data.db"

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
            current_balance REAL
        )
    """)
    cur2.execute("PRAGMA table_info(accounts)")
    account_columns = [row[1] for row in cur2.fetchall()]
    if "item_id" not in account_columns:
        cur2.execute("ALTER TABLE accounts ADD COLUMN item_id TEXT")

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

    con.commit()
    con.close()

# endregion


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
    conn = sqlite3.connect("finance_data.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS items (
            item_id TEXT PRIMARY KEY,
            access_token TEXT,
            institution_name TEXT,
            institution_id TEXT
        )
    """)
    c.execute("PRAGMA table_info(items)")
    item_columns = [row[1] for row in c.fetchall()]
    if "institution_name" not in item_columns:
        c.execute("ALTER TABLE items ADD COLUMN institution_name TEXT")
    if "institution_id" not in item_columns:
        c.execute("ALTER TABLE items ADD COLUMN institution_id TEXT")
    c.execute(
        "INSERT OR REPLACE INTO items (item_id, access_token) VALUES (?, ?)",
        (item_id, access_token),
    )
    conn.commit()
    conn.close()


def update_item_institution(item_id, institution_name=None, institution_id=None):
    conn = sqlite3.connect("finance_data.db")
    c = conn.cursor()
    c.execute("PRAGMA table_info(items)")
    item_columns = [row[1] for row in c.fetchall()]
    if "institution_name" not in item_columns:
        c.execute("ALTER TABLE items ADD COLUMN institution_name TEXT")
    if "institution_id" not in item_columns:
        c.execute("ALTER TABLE items ADD COLUMN institution_id TEXT")
    c.execute(
        """
        UPDATE items
        SET institution_name = ?, institution_id = ?
        WHERE item_id = ?
        """,
        (institution_name, institution_id, item_id),
    )
    conn.commit()
    conn.close()


def get_items():
    conn = sqlite3.connect("finance_data.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS items (
            item_id TEXT PRIMARY KEY,
            access_token TEXT
        )
    """)
    c.execute("SELECT item_id, access_token FROM items")
    rows = c.fetchall()
    conn.close()
    return [{"item_id": row[0], "access_token": row[1]} for row in rows]

def store_accounts(accounts, item_id=None):
    conn = sqlite3.connect("finance_data.db")
    c = conn.cursor()
    c.execute("PRAGMA table_info(accounts)")
    account_columns = [row[1] for row in c.fetchall()]
    if "item_id" not in account_columns:
        c.execute("ALTER TABLE accounts ADD COLUMN item_id TEXT")
    for account in accounts:
        c.execute("""
            INSERT OR REPLACE INTO accounts 
            (account_id, name, official_name, type, subtype, current_balance, item_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            account.account_id,
            account.name,
            account.official_name,
            str(account.type),
            str(account.subtype),
            account.balances.current,
            item_id,
        ))
    conn.commit()
    conn.close()


def get_institutions():
    conn = sqlite3.connect("finance_data.db")
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


def wipe_all_data():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM finance_data")
    cur.execute("DELETE FROM Stocks")
    cur.execute("DELETE FROM stock_prices")
    cur.execute("DELETE FROM stock_metadata")
    cur.execute("DELETE FROM realized_gains")
    cur.execute("DELETE FROM accounts")
    cur.execute("DELETE FROM transactions")
    cur.execute("DELETE FROM items")
    cur.execute("DELETE FROM plaid_holdings")
    cur.execute("DELETE FROM price_update_log")
    conn.commit()
    conn.close()

def insert_transactions(transactions):
    # Connect to SQLite and insert each transaction
    conn = sqlite3.connect("finance_data.db")
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