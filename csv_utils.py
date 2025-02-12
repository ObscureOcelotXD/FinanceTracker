# csv_manager.py (or csv_utils.py)

import csv
import os
from datetime import datetime

CSV_FILENAME = "finance_data.csv"
EXPECTED_HEADERS = ["Id", "AccountName", "SourceName", "SourceValue", "DateCreated"]

def load_csv_data():
    if not os.path.exists(CSV_FILENAME):
        return []
    with open(CSV_FILENAME, "r", newline="") as file:
        reader = csv.reader(file)
        headers = next(reader, None)
        if headers != EXPECTED_HEADERS:
            return []
        rows = []
        for row in reader:
            if len(row) < 5:
                continue
            row_id, account_name, source_name, source_value = row[0], row[1], row[2], row[3]
            source_value = source_value.strip('"')
            try:
                numeric_value = float(source_value.replace("$", "").replace(",", ""))
            except ValueError:
                numeric_value = 0
            rows.append((numeric_value, row_id, account_name, source_name, source_value))
    return rows

def save_entry(account_name, source_name, source_value):
    next_id = 1
    if os.path.exists(CSV_FILENAME):
        with open(CSV_FILENAME, "r", newline="") as file:
            reader = csv.reader(file)
            next(reader, None)
            ids = [int(row[0]) for row in reader if row[0].isdigit()]
            next_id = max(ids, default=0) + 1
    date_created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(CSV_FILENAME, "a", newline="") as file:
        writer = csv.writer(file)
        if os.stat(CSV_FILENAME).st_size == 0:
            writer.writerow(EXPECTED_HEADERS)
        writer.writerow([next_id, account_name, source_name, source_value.strip('"'), date_created])


def get_sorted_csv_data(ascending=True):
    """
    Returns CSV data sorted by the numeric value.
    """
    rows = load_csv_data()
    # If there is no data, rows is empty
    rows.sort(key=lambda x: x[0], reverse=not ascending)
    return rows