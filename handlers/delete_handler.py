import csv
import os
from PySide6.QtWidgets import QMessageBox

CSV_FILENAME = "finance_data.csv"

def delete_selected_row(ui):
    """Deletes the selected row from the UI and CSV file."""
    selected_row = ui.sourceTable.currentRow()
    if selected_row == -1:
        QMessageBox.warning(ui, "Selection Error", "Please select a row to delete.")
        return

    # Get values from the selected row
    account_name = ui.sourceTable.item(selected_row, 0).text()
    source_name = ui.sourceTable.item(selected_row, 1).text()
    source_value = ui.sourceTable.item(selected_row, 2).text()

    # Remove the row from the table UI
    ui.sourceTable.removeRow(selected_row)

    # Remove from CSV
    remove_from_csv(account_name, source_name, source_value)

def remove_from_csv(account_name, source_name, source_value):
    """Removes a row from the CSV file by rewriting it without the deleted row."""
    if not os.path.exists(CSV_FILENAME):
        return

    temp_filename = CSV_FILENAME + ".tmp"
    with open(CSV_FILENAME, "r", newline="") as infile, open(temp_filename, "w", newline="") as outfile:
        reader = csv.reader(infile)
        writer = csv.writer(outfile)

        headers = next(reader, None)
        writer.writerow(headers)

        for row in reader:
            if row[1] == account_name and row[2] == source_name and row[3] == source_value:
                continue  # Skip writing this row

            writer.writerow(row)

    os.replace(temp_filename, CSV_FILENAME)
