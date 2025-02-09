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

CSV_FILENAME = "finance_data.csv"

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_FinanceTrackerHomeWindow()
        self.ui.setupUi(self)

        # ✅ Set table headers
        self.ui.sourceTable.setColumnCount(4)
        self.ui.sourceTable.setHorizontalHeaderLabels(["Id","Account Name","Source Name", "Source Value"])

        # ✅ Connect "Add Source" button to a single method for UI & CSV
        # Connect functions:
        self.ui.addSource.clicked.connect(self.handle_add_source)
        self.ui.sourceTable.itemChanged.connect(lambda item: handle_value_edit(self, item))
        self.ui.deleteRowButton.clicked.connect(lambda: delete_selected_row(self.ui))

         # ✅ Load existing data on startup
        self.load_from_csv()

    def save_to_csv(self, account_name, source_name, source_value):
        self.load_from_csv()
        """Saves a single source entry to the CSV file."""
        next_id = 1  # Default to 1
        if os.path.exists(CSV_FILENAME):
            with open(CSV_FILENAME, "r", newline="") as file:
                reader = csv.reader(file)
                next(reader, None)  # Skip header row
                ids = [int(row[0]) for row in reader if row[0].isdigit()]
                next_id = max(ids, default=0) + 1  # Get the highest Id and increment



        date_created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        with open(CSV_FILENAME, "a", newline="") as file:
            writer = csv.writer(file)
            if next_id == 1:  # Write header if file is new
                writer.writerow(["Id", "AccountName", "SourceName", "SourceValue", "DateCreated"])
            writer.writerow([next_id, account_name, source_name, source_value, date_created])

        QMessageBox.information(self, "Success", "Source added and saved to CSV!")


    def load_from_csv(self):
            """Loads existing CSV data into the table on startup."""
            if not os.path.exists(CSV_FILENAME):
                return  # No file yet, so nothing to load

            with open(CSV_FILENAME, "r", newline="") as file:
                reader = csv.reader(file)
                headers = next(reader, None)  # Read header row

                if headers != ["Id", "AccountName", "SourceName", "SourceValue", "DateCreated"]:
                    QMessageBox.warning(self, "Warning", "CSV file format may be incorrect.")
                    return

                for row in reader:
                    if len(row) < 5:
                        continue  # Skip malformed rows
                    
                    row_id, account_name, source_name, source_value = row[0], row[1], row[2], row[3]

                    row_count = self.ui.sourceTable.rowCount()
                    self.ui.sourceTable.insertRow(row_count)
                    self.ui.sourceTable.setItem(row_count, 0, QTableWidgetItem(row_id))  # Id
                    self.ui.sourceTable.setItem(row_count, 1, QTableWidgetItem(account_name))
                    self.ui.sourceTable.setItem(row_count, 2, QTableWidgetItem(source_name))
                    self.ui.sourceTable.setItem(row_count, 3, QTableWidgetItem(source_value))

                    # ✅ Lock Id, Account Name, and Source Name
                    for col in range(3):
                        self.ui.sourceTable.item(row_count, col).setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)


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

            
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
