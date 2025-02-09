import csv
import os
from PySide6.QtWidgets import QMessageBox

CSV_FILENAME = "finance_data.csv"

def handle_value_edit(ui, item):
    """Detects changes to the 'Source Value' column and updates the CSV file."""
    row = item.row()
    column = item.column()

    if column != 2:  # Only allow editing of 'Source Value' column
        return

    # Get updated value
    new_value = item.text().strip()
    cleaned_value = clean_currency_input(new_value)
    if cleaned_value is None:
        QMessageBox.warning(ui, "Input Error", "Invalid currency format. Please use numbers only (e.g., 100, 100.00).")
        return

    # Update the table with formatted value
    ui.sourceTable.item(row, column).setText(cleaned_value)

    # Retrieve other row details to identify the correct entry
    account_name = ui.sourceTable.item(row, 0).text()
    source_name = ui.sourceTable.item(row, 1).text()

    # Update CSV file
    update_csv(account_name, source_name, cleaned_value)

def clean_currency_input(value):
    """Cleans and validates currency input."""
    value = value.replace("$", "").replace(",", "")
    if not value.replace(".", "", 1).isdigit():
        return None
    return f"${float(value):,.2f}"

def update_csv(account_name, source_name, new_value):
    """Updates the CSV file with an edited Source Value."""
    if not os.path.exists(CSV_FILENAME):
        return

    temp_filename = CSV_FILENAME + ".tmp"
    with open(CSV_FILENAME, "r", newline="") as infile, open(temp_filename, "w", newline="") as outfile:
        reader = csv.reader(infile)
        writer = csv.writer(outfile)

        headers = next(reader, None)
        writer.writerow(headers)

        for row in reader:
            if len(row) < 5:
                continue

            if row[1] == account_name and row[2] == source_name:
                row[3] = new_value  # Update the Source Value

            writer.writerow(row)

    os.replace(temp_filename, CSV_FILENAME)
