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
            access_token TEXT
        )
    """)
    c.execute("INSERT OR REPLACE INTO items (item_id, access_token) VALUES (?, ?)",
                (item_id, access_token))
    conn.commit()
    conn.close()

def store_accounts(accounts):
    conn = sqlite3.connect("finance_data.db")
    c = conn.cursor()
    for account in accounts:
        c.execute("""
            INSERT OR REPLACE INTO accounts 
            (account_id, name, official_name, type, subtype, current_balance)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            account.account_id,
            account.name,
            account.official_name,
            str(account.type),
            str(account.subtype),
            account.balances.current
        ))
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
    query = "SELECT id,ticker,shares FROM Stocks"
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
        SELECT s.id, s.ticker, s.shares, sp.date, sp.closing_price
        FROM Stocks s
        JOIN stock_prices sp ON s.ticker = sp.ticker
        where sp.date = (select max(date) from stock_prices)
        """
    df = pd.read_sql_query(query, conn)
    conn.close()
    df['position_value'] = df['shares'] * df['closing_price']
    return df

def insert_stock(ticker, shares):
    """
    Insert a new stock record into the Stocks table.
    Returns the new stock's id.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO Stocks (ticker, shares) VALUES (?, ?)", (ticker, shares))
    conn.commit()
    stock_id = cur.lastrowid
    conn.close()
    return stock_id

def update_stock(stock_id, ticker, shares):
    """
    Update an existing stock record with the given id.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE Stocks SET ticker = ?, shares = ? WHERE id = ?", (ticker, shares, stock_id))
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