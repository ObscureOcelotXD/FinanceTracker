import csv
import os
from PySide6.QtWidgets import QMessageBox
import db_manager
CSV_FILENAME = "finance_data.csv"

def delete_selected_row(ui):
    """Deletes the selected row from the UI and database based on Id."""
    selected_row = ui.sourceTable.currentRow()
    if selected_row == -1:
        QMessageBox.warning(ui, "Selection Error", "Please select a row to delete.")
        return

    # Get the Id from the selected row
    row_id = ui.sourceTable.item(selected_row, 0).text()

    # Remove the row from the UI table
    ui.sourceTable.removeRow(selected_row)

    # Remove the row from the database
    remove_from_db(row_id)

def remove_from_db(row_id):
    """Removes a row from the database based on Id."""
    db_manager.delete_record(row_id)
