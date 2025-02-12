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
        
        # ✅ Append new data
        with open(CSV_FILENAME, "a", newline="") as file:
            writer = csv.writer(file)
            if os.stat(CSV_FILENAME).st_size == 0:  # If empty, write header
                writer.writerow(["Id", "AccountName", "SourceName", "SourceValue", "DateCreated"])
            writer.writerow([next_id, account_name, source_name, source_value.strip('"'), date_created])

        # ✅ Reload & sort CSV data
        self.load_from_csv()
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

            rows = [] 
            for row in reader:
                if len(row) < 5:
                    continue  # Skip malformed rows

                row_id, account_name, source_name, source_value = row[0], row[1], row[2], row[3]

                # ✅ Debug: Print how values are being read
                print(f"🔹 Read from CSV: {row}")

                # ✅ Remove quotes if present
                source_value = source_value.strip('"')

                # ✅ Convert SourceValue to float for sorting
                try:
                    numeric_value = float(source_value.replace("$", "").replace(",", ""))
                except ValueError:
                    numeric_value = 0  # Handle invalid cases

                rows.append((numeric_value, row_id, account_name, source_name, source_value))


            # Sort rows numerically by the float value
            rows.sort(key=lambda x: x[0])

            # ✅ Debug: Print sorted list before inserting into UI
            print(f"✅ Sorted Rows: {rows}")

            # ✅ Clear table before inserting data
            self.ui.sourceTable.setRowCount(0)

            # ✅ Insert data into UI Table
            for numeric_value, row_id, account_name, source_name, source_value in rows:
                print(f"✅ Inserting into UI: {row_id}, {account_name}, {source_name}, {source_value}")  # Debug output

                row_count = self.ui.sourceTable.rowCount()
                self.ui.sourceTable.insertRow(row_count)
                self.ui.sourceTable.setItem(row_count, 0, QTableWidgetItem(row_id))
                self.ui.sourceTable.setItem(row_count, 1, QTableWidgetItem(account_name))
                self.ui.sourceTable.setItem(row_count, 2, QTableWidgetItem(source_name))
                self.ui.sourceTable.setItem(row_count, 3, QTableWidgetItem(source_value))
                num = float(source_value.replace("$", "").replace(",", ""))
                self.ui.sourceTable.setItem(row_count, 4, QTableWidgetItem(num))
                # ✅ Lock Id, Account Name, and Source Name
                for col in range(3):
                    self.ui.sourceTable.item(row_count, col).setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

        # ✅ Debug: Print final table row count
        print(f"✅ Final Table Row Count: {self.ui.sourceTable.rowCount()}")

        self.ui.sourceTable.viewport().update()  # ✅ Force UI update after loading
        self.ui.sourceTable.repaint()  # ✅ Ensures table reflects the sorted data



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
        """Sorts the table numerically using the hidden float column (column 4)."""
        self.ui.sourceTable.setSortingEnabled(False)  # Temporarily disable sorting

        # ✅ Determine sort order
        order = Qt.AscendingOrder if self.sort_ascending else Qt.DescendingOrder

        if not os.path.exists(CSV_FILENAME):
            return  # No file yet, so nothing to load

        with open(CSV_FILENAME, "r", newline="") as file:
            reader = csv.reader(file)
            headers = next(reader, None)  # Read header row

            if headers != ["Id", "AccountName", "SourceName", "SourceValue", "DateCreated"]:
                QMessageBox.warning(self, "Warning", "CSV file format may be incorrect.")
                return

            rows = [] 
            for row in reader:
                if len(row) < 5:
                    continue  # Skip malformed rows

                row_id, account_name, source_name, source_value = row[0], row[1], row[2], row[3]

                # ✅ Debug: Print how values are being read
                print(f"🔹 Read from CSV: {row}")

                # ✅ Remove quotes if present
                source_value = source_value.strip('"')

                # ✅ Convert SourceValue to float for sorting
                try:
                    numeric_value = float(source_value.replace("$", "").replace(",", ""))
                except ValueError:
                    numeric_value = 0  # Handle invalid cases

                rows.append((numeric_value, row_id, account_name, source_name, source_value))


        # ✅ Apply sorting order explicitly using an `if` statement
        if order == Qt.AscendingOrder:
            rows.sort(key=lambda x: x[0])  # ✅ Ascending order
        else:
            rows.sort(key=lambda x: x[0], reverse=True)  # ✅ Descending order
            
        print(f"✅ Sorted Rows on Sort: {rows}")

        # Reinsert sorted data into the table
        self.ui.sourceTable.setRowCount(0)  # Clear existing rows
        for numeric_value, row_id, account_name, source_name, source_value in rows:
            row_count = self.ui.sourceTable.rowCount()
            
            self.ui.sourceTable.insertRow(row_count)
            self.ui.sourceTable.setItem(row_count, 0, QTableWidgetItem(row_id))
            self.ui.sourceTable.setItem(row_count, 1, QTableWidgetItem(account_name))
            self.ui.sourceTable.setItem(row_count, 2, QTableWidgetItem(source_name))
            self.ui.sourceTable.setItem(row_count, 3, QTableWidgetItem(source_value))
            # # Store formatted currency in visible column
            # currency_item = QTableWidgetItem(f"${numeric_value:,.2f}")
            # self.ui.sourceTable.setItem(row_count, 3, currency_item)

            # Store float value in hidden column for sorting
            float_item = QTableWidgetItem(str(numeric_value))
            float_item.setData(Qt.UserRole, numeric_value)  # Ensure numeric sorting
            self.ui.sourceTable.setItem(row_count, 4, float_item)



        # self.ui.sourceTable.setSortingEnabled(True)  # Re-enable sorting
        # self.ui.sourceTable.sortItems(5, order)  # Sort using the hidden column
        # ✅ Toggle sort direction for next click

        self.ui.sourceTable.viewport().update()  # ✅ Force UI update after loading
        self.ui.sourceTable.repaint()  # ✅ Ensures table reflects the sorted data
        self.sort_ascending = not self.sort_ascending

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
