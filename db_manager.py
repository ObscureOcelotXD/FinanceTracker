import sqlite3
from datetime import datetime

DATABASE = "finance_data.db"

def get_connection():
    return sqlite3.connect(DATABASE)

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
