import csv
import os
from PySide6.QtWidgets import QMessageBox

CSV_FILENAME = "finance_data.csv"

def delete_selected_row(ui):
    """Deletes the selected row from the UI and CSV file based on Id."""
    selected_row = ui.sourceTable.currentRow()
    if selected_row == -1:
        QMessageBox.warning(ui, "Selection Error", "Please select a row to delete.")
        return

    # Get the Id from the selected row
    row_id = ui.sourceTable.item(selected_row, 0).text()

    # Remove the row from the UI table
    ui.sourceTable.removeRow(selected_row)

    # Remove the row from the CSV file
    remove_from_csv(row_id)

def remove_from_csv(row_id):
    """Removes a row from the CSV file based on Id and reassigns sequential Ids."""
    if not os.path.exists(CSV_FILENAME):
        return

    temp_filename = CSV_FILENAME + ".tmp"
    updated_rows = []
    
    with open(CSV_FILENAME, "r", newline="") as infile:
        reader = csv.reader(infile)
        headers = next(reader, None)
        updated_rows.append(headers)  # Keep the headers

        for row in reader:
            if row and row[0] == row_id:  # Skip the row with the matching Id
                continue
            updated_rows.append(row)

    # Rewrite CSV without the deleted row
    with open(temp_filename, "w", newline="") as outfile:
        writer = csv.writer(outfile)
        writer.writerows(updated_rows)

    os.replace(temp_filename, CSV_FILENAME)

    # ✅ After deleting, reassign sequential Ids
    reassign_ids()

def reassign_ids():
    """Reassigns sequential Ids to maintain correct numbering after deletion."""
    if not os.path.exists(CSV_FILENAME):
        return

    temp_filename = CSV_FILENAME + ".tmp"
    updated_rows = []
    
    with open(CSV_FILENAME, "r", newline="") as infile:
        reader = csv.reader(infile)
        headers = next(reader, None)
        updated_rows.append(headers)  # Keep the headers

        new_id = 1
        for row in reader:
            if row:
                row[0] = str(new_id)  # Update the Id
                updated_rows.append(row)
                new_id += 1

    # Rewrite CSV with updated Ids
    with open(temp_filename, "w", newline="") as outfile:
        writer = csv.writer(outfile)
        writer.writerows(updated_rows)

    os.replace(temp_filename, CSV_FILENAME)
