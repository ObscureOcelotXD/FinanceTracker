import sqlite3
from datetime import datetime
import sqlite3
import pandas as pd

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
    """Inserts a new record into the database."""
    con = get_connection()
    cur = con.cursor()
    date_created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute('''
        INSERT INTO finance_data (account_name, source_name, source_value, date_created)
        VALUES (?, ?, ?, ?)
    ''', (account_name, source_name, float(source_value), date_created))
    con.commit()
    con.close()

def delete_record(row_id):
    """Deletes a record from the database based on Id."""
    con = get_connection()
    cur = con.cursor()
    print(f"Executing DELETE FROM finance_data WHERE id={row_id}")
    cur.execute('''
        DELETE FROM finance_data WHERE id=?
    ''', (row_id,))
    con.commit()
    con.close()
    print(f"Record with Id: {row_id} deleted from the database")

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