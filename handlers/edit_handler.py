import csv
import os
import re
import time
import threading
from PySide6.QtWidgets import QMessageBox

CSV_FILENAME = "finance_data.csv"

def handle_value_edit(main_window, item):
    """Detects changes to the 'Source Value' column and updates the CSV file."""
    row = item.row()
    column = item.column()

    # Ensure we are editing the correct column (Source Value)
    if column != 3:
        return

    # Get updated value and print debug info
    new_value = item.text().strip()
    print(f"🔹 Editing Row {row}, Column {column}, New Value: '{new_value}'")

    # Ignore empty edits
    if not new_value:
        return

    # Validate and clean currency input
    cleaned_value = clean_currency_input(new_value)

    # If invalid, prevent multiple alerts
    if cleaned_value is None:
        print(f"Invalid Input Detected: {new_value}")
        if not hasattr(main_window, "_alert_shown") or not main_window._alert_shown:
            QMessageBox.warning(main_window, "Input Error", "Invalid currency format.")
            main_window._alert_shown = True
        return

    # Update table with formatted value
    main_window.ui.sourceTable.blockSignals(True)
    main_window.ui.sourceTable.item(row, column).setText(cleaned_value)
    main_window.ui.sourceTable.blockSignals(False)

    # Retrieve row Id from the first column
    id_item = main_window.ui.sourceTable.item(row, 0)
    row_id = id_item.text() if id_item else None

    # Check if this is the totals row (or an invalid row) and skip processing
    if row_id is None or not row_id.isdigit():
        # If the row doesn't have a valid numeric id, assume it's the totals row
        print(f"Skipping edit on totals or non-data row at row {row}")
        return
    

def clean_currency_input(value):
    """Cleans and validates currency input."""
    if not value or value.strip() == "":
        return None  # ✅ Prevents empty values from triggering the error

    value = value.replace("$", "").replace(",", "").strip()

    # ✅ Ensure the value is a valid number (allows integers & decimals)
    if not re.match(r"^\d+(\.\d{1,2})?$", value):
        print(f" Invalid Input Detected: {value}")  # ✅ Debugging line
        return None

    return f"${float(value):,.2f}"


def update_csv(row_id, new_value):
    """Updates the CSV file with the edited Source Value."""
    temp_filename = CSV_FILENAME + ".tmp"

    print(f"🔹 Attempting to update row {row_id} with value {new_value}")

    # ✅ Read entire CSV into memory before writing
    with open(CSV_FILENAME, "r", newline="") as infile:
        reader = csv.reader(infile)
        rows = list(reader)  # ✅ Read everything first
        print(f"✅ Read {len(rows)} rows from {CSV_FILENAME}")

    # ✅ Write to temp file
    with open(temp_filename, "w", newline="") as outfile:
        writer = csv.writer(outfile)
        for row in rows:
            if len(row) < 5:
                continue

            if row[0] == row_id:
                row[3] = new_value  # ✅ Update SourceValue

            writer.writerow(row)

    print(f"✅ Temporary CSV file written: {temp_filename}")

    # ✅ Ensure the temp file exists before replacing the original
    if not os.path.exists(temp_filename):
        print(f" Error: Temporary file {temp_filename} not found. Cannot update CSV.")
        return

    # ✅ Retry renaming file if Windows still locks it
    max_retries = 5
    for attempt in range(max_retries):
        try:
            os.remove(CSV_FILENAME)  # ✅ Explicitly remove old CSV first
            time.sleep(0.1)  # ✅ Short delay
            os.rename(temp_filename, CSV_FILENAME)  # ✅ Now rename safely
            print("✅ CSV successfully updated.")
            break  # ✅ Exit loop if successful
        except PermissionError:
            print(f"⚠️ Attempt {attempt+1}: PermissionError - Retrying in 0.5s...")
            time.sleep(0.5)  # ✅ Wait before retrying
    else:
        print(f" Failed to replace {CSV_FILENAME} after {max_retries} attempts.")



