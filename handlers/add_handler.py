import csv
import os
from datetime import datetime
from PySide6.QtWidgets import QTableWidgetItem, QMessageBox
from PySide6.QtCore import Qt

CSV_FILENAME = "finance_data.csv"

def add_source(ui,next_id):
    """Handles adding a source name and value to the UI & CSV."""
    account_name = ui.accountNameEdit.toPlainText().strip()
    source_name = ui.textEdit.toPlainText().strip()
    source_value = ui.valueAmountEdit.toPlainText().strip()

    if not account_name or not source_name or not source_value:
        QMessageBox.warning(ui, "Input Error", "Account Name, Source Name, and Source Value are required!")
        return

    # Validate and clean the source value
    cleaned_value = clean_currency_input(source_value)
    if cleaned_value is None:
        QMessageBox.warning(ui, "Input Error", "Source Value must be a valid number format!")
        return

    # Add to the table UI
    row_count = ui.sourceTable.rowCount()
    ui.sourceTable.insertRow(row_count)
    ui.sourceTable.setItem(row_count, 0, QTableWidgetItem(str(next_id)))  # Id
    ui.sourceTable.setItem(row_count, 1, QTableWidgetItem(account_name))
    ui.sourceTable.setItem(row_count, 2, QTableWidgetItem(source_name))
    ui.sourceTable.setItem(row_count, 3, QTableWidgetItem(cleaned_value))

    # Lock Id, Account Name, and Source Name
    for col in range(3):
        ui.sourceTable.item(row_count, col).setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

    # Save to CSV
    save_to_csv(next_id,account_name, source_name, cleaned_value)

    # Clear input fields
    ui.accountNameEdit.clear()
    ui.textEdit.clear()
    ui.valueAmountEdit.clear()

def clean_currency_input(value):
    """Cleans and validates currency input."""
    value = value.replace("$", "").replace(",", "")
    if not value.replace(".", "", 1).isdigit():
        return None
    return f"${float(value):,.2f}"

def save_to_csv(row_id,account_name, source_name, source_value):
    """Saves a new entry to the CSV file."""
    date_created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    write_header = not os.path.exists(CSV_FILENAME)

    with open(CSV_FILENAME, "a", newline="") as file:
        writer = csv.writer(file)
        if write_header:
            writer.writerow(["Id", "AccountName", "SourceName", "SourceValue", "DateCreated"])
        writer.writerow([row_id, account_name, source_name, source_value, date_created])
