import sys
import csv
import re
import os
from datetime import datetime
from PySide6.QtWidgets import QApplication, QMainWindow, QTableWidgetItem, QMessageBox
from PySide6.QtCore import Qt
from ui_main_window import Ui_FinanceTrackerHomeWindow
from handlers.add_handler import add_source
from handlers.edit_handler import handle_value_edit
from handlers.delete_handler import delete_selected_row
import csv_utils

CSV_FILENAME = "finance_data.csv"

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_FinanceTrackerHomeWindow()
        self.ui.setupUi(self)
        # ✅ Initialize alert flag to prevent crashes
        self._alert_shown = False

        # ✅ Set table headers
        self.ui.sourceTable.setColumnCount(5)  # ✅ Add a hidden column for float values
        self.ui.sourceTable.setHorizontalHeaderLabels(["Id", "Account Name", "Source Name", "Source Value", "Hidden Float Value"])
        self.ui.sourceTable.setColumnHidden(4, True)  # ✅ Hide the float column

        self.ui.sourceTable.setSortingEnabled(True)  # Enable sorting
        self.sort_ascending = True # track sorting direction
        self.ui.sourceTable.horizontalHeader().sectionClicked.connect(lambda index: self.sort_by_value() if index == 3 else None)

        # ✅ Connect "Add Source" button to a single method for UI & CSV
        # Connect functions:
        self.ui.addSource.clicked.connect(self.handle_add_source)
        self.ui.sourceTable.itemChanged.connect(lambda item: handle_value_edit(self, item))
        self.ui.deleteRowButton.clicked.connect(lambda: delete_selected_row(self.ui))

         # ✅ Load existing data on startup
        self.load_from_csv()




    def load_from_csv(self):
        """Loads CSV data into the table on startup."""
        rows = csv_utils.load_csv_data()
        if not rows:
            QMessageBox.warning(self, "Warning", "CSV file may be missing or has an unexpected format.")
            return

        # Sort rows numerically by the float value
        rows.sort(key=lambda x: x[0])
        self.ui.sourceTable.setRowCount(0)

        for numeric_value, row_id, account_name, source_name, source_value in rows:
            row_count = self.ui.sourceTable.rowCount()
            self.ui.sourceTable.insertRow(row_count)
            self.ui.sourceTable.setItem(row_count, 0, QTableWidgetItem(row_id))
            self.ui.sourceTable.setItem(row_count, 1, QTableWidgetItem(account_name))
            self.ui.sourceTable.setItem(row_count, 2, QTableWidgetItem(source_name))
            self.ui.sourceTable.setItem(row_count, 3, QTableWidgetItem(source_value))
            self.ui.sourceTable.setItem(row_count, 4, QTableWidgetItem(str(numeric_value)))
            for col in range(3):
                self.ui.sourceTable.item(row_count, col).setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

        self.ui.sourceTable.viewport().update()
        self.ui.sourceTable.repaint()

    def save_to_csv(self, account_name, source_name, source_value):
        """Saves a new entry and reloads the table."""
        csv_utils.save_entry(account_name, source_name, source_value)
        self.load_from_csv()
        QMessageBox.information(self, "Success", "Source added and saved to CSV!")



    def get_next_id(self):  
            """Finds the next available Id by reading the CSV."""
            if not os.path.exists(CSV_FILENAME):
                return 1  # Start at 1 if file doesn't exist

            with open(CSV_FILENAME, "r", newline="") as file:
                reader = csv.reader(file)
                next(reader, None)  # Skip headers
                ids = [int(row[0]) for row in reader if row[0].isdigit()]
                return max(ids, default=0) + 1  # Get next available Id
            
    def handle_add_source(self):
        """Handles calling add_source with the correct Id"""
        add_source(self.ui, self.get_next_id())



    def sort_by_value(self):
        """Sorts CSV data and updates the table based on the numeric value."""
        self.ui.sourceTable.setSortingEnabled(False)

        rows = csv_utils.get_sorted_csv_data(self.sort_ascending)
        if not rows:
            QMessageBox.warning(self, "Warning", "CSV file may be missing or has an unexpected format.")
            return

        self.ui.sourceTable.setRowCount(0)  # Clear the table

        for numeric_value, row_id, account_name, source_name, source_value in rows:
            row_count = self.ui.sourceTable.rowCount()
            self.ui.sourceTable.insertRow(row_count)
            self.ui.sourceTable.setItem(row_count, 0, QTableWidgetItem(row_id))
            self.ui.sourceTable.setItem(row_count, 1, QTableWidgetItem(account_name))
            self.ui.sourceTable.setItem(row_count, 2, QTableWidgetItem(source_name))
            self.ui.sourceTable.setItem(row_count, 3, QTableWidgetItem(source_value))
            
            # Update the hidden column with the numeric value
            float_item = QTableWidgetItem(str(numeric_value))
            float_item.setData(Qt.UserRole, numeric_value)
            self.ui.sourceTable.setItem(row_count, 4, float_item)

        self.ui.sourceTable.viewport().update()
        self.ui.sourceTable.repaint()
        self.sort_ascending = not self.sort_ascending

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
