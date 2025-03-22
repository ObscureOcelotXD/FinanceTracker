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
#endregion