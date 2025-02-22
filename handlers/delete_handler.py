import csv
import os
from PySide6.QtWidgets import QMessageBox
from db_manager import delete_record

def delete_selected_row(ui):
    """Deletes the selected row from the UI and database based on Id."""
    selected_row = ui.sourceTable.currentRow()
    if selected_row == -1:
        QMessageBox.warning(ui, "Selection Error", "Please select a row to delete.")
        return

    # Get the Id from the selected row
    row_id = ui.sourceTable.item(selected_row, 0).text()
    #print(f"Deleting row with Id: {row_id}")

    # Remove the row from the UI table
    ui.sourceTable.removeRow(selected_row)

    # Remove the row from the database
    remove_from_db(row_id)

def remove_from_db(row_id):
    """Removes a row from the database based on Id."""
    #print(f"Calling delete_record with Id: {row_id}")
    delete_record(row_id)
    #print(f"Record with Id: {row_id} should be deleted from the database")
