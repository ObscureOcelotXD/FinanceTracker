import sys
import csv
import re
import os
from datetime import datetime
from collections import defaultdict
from PySide6.QtGui import QBrush, QColor
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

        self.ui.resetButton.clicked.connect(self.reset_to_initial_state)
         # ✅ Load existing data on startup
        self.populate_table_with_group_totals()



    def populate_table_with_group_totals(self):
        """
        Populates the table by grouping data rows by Account Name,
        then adds a totals row for each account with a green background.
        """
        # Load all CSV rows using your CSV module
        rows = csv_utils.load_csv_data()  # rows is a list of tuples:
        # Each tuple: (numeric_value, row_id, account_name, source_name, source_value)
        if not rows:
            QMessageBox.warning(self, "Warning", "CSV file may be missing or has an unexpected format.")
            return

        # Group rows by account name
        groups = defaultdict(list)
        for row in rows:
            numeric_value, row_id, account_name, source_name, source_value = row
            groups[account_name].append(row)

        # Clear the table
        self.ui.sourceTable.setRowCount(0)

        # Use a green brush for totals rows
        green_brush = QBrush(QColor(50, 10, 50))  # light green (you can adjust the color)

        # Iterate over each account group in sorted order (optional)
        for account in sorted(groups.keys()):
            account_rows = groups[account]
            # Optional: sort the rows within the group (e.g., by numeric value)
            account_rows.sort(key=lambda x: x[0])

            account_total = 0.0
            # Insert each data row for this account
            for numeric_value, row_id, account_name, source_name, source_value in account_rows:
                row_count = self.ui.sourceTable.rowCount()
                self.ui.sourceTable.insertRow(row_count)

                # Insert data into the row
                self.ui.sourceTable.setItem(row_count, 0, QTableWidgetItem(row_id))
                self.ui.sourceTable.setItem(row_count, 1, QTableWidgetItem(account_name))
                self.ui.sourceTable.setItem(row_count, 2, QTableWidgetItem(source_name))
                self.ui.sourceTable.setItem(row_count, 3, QTableWidgetItem(source_value))
                # Hidden numeric value in column 4 for sorting
                self.ui.sourceTable.setItem(row_count, 4, QTableWidgetItem(str(numeric_value)))

                account_total += numeric_value

                # Optionally lock the first three columns from editing
                for col in range(3):
                    self.ui.sourceTable.item(row_count, col).setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

            # After inserting the group rows, add a totals row for this account
            totals_row = self.ui.sourceTable.rowCount()
            self.ui.sourceTable.insertRow(totals_row)

            # Insert a dummy value or marker in the Id column to indicate a totals row
            dummy_id = QTableWidgetItem("total")
            dummy_id.setFlags(Qt.ItemIsEnabled)
            self.ui.sourceTable.setItem(totals_row, 0, dummy_id)

            # In the Account Name column, display the label for totals
            total_label = QTableWidgetItem(f"Total for {account}")
            total_label.setFlags(Qt.ItemIsEnabled)
            self.ui.sourceTable.setItem(totals_row, 1, total_label)

            # Optionally leave the Source Name column blank
            self.ui.sourceTable.setItem(totals_row, 2, QTableWidgetItem(""))

            # In the Source Value column, display the formatted total
            total_display = QTableWidgetItem("${:,.2f}".format(account_total))
            total_display.setFlags(Qt.ItemIsEnabled)
            self.ui.sourceTable.setItem(totals_row, 3, total_display)

            # Optionally fill the hidden numeric value column too
            self.ui.sourceTable.setItem(totals_row, 4, QTableWidgetItem(str(account_total)))

            # Set the background for every cell in the totals row to green
            for col in range(self.ui.sourceTable.columnCount()):
                item = self.ui.sourceTable.item(totals_row, col)
                if item:
                    item.setBackground(green_brush)

        # Force an update of the table view
        self.ui.sourceTable.viewport().update()
        self.ui.sourceTable.repaint()





    def load_from_csv(self):
        """Loads CSV data into the table and appends a totals row at the bottom."""
        rows = csv_utils.load_csv_data()  # Only data rows from CSV
        if not rows:
            QMessageBox.warning(self, "Warning", "CSV file may be missing or has an unexpected format.")
            return

        # Sort rows by numeric value (ascending by default)
        rows.sort(key=lambda x: x[0])
        self.ui.sourceTable.setSortingEnabled(False)  # Disable built-in sorting
        self.ui.sourceTable.setRowCount(0)  # Clear table

        total_value = 0
        # Insert each data row
        for numeric_value, row_id, account_name, source_name, source_value in rows:
            row_count = self.ui.sourceTable.rowCount()
            self.ui.sourceTable.insertRow(row_count)
            self.ui.sourceTable.setItem(row_count, 0, QTableWidgetItem(row_id))
            self.ui.sourceTable.setItem(row_count, 1, QTableWidgetItem(account_name))
            self.ui.sourceTable.setItem(row_count, 2, QTableWidgetItem(source_name))
            self.ui.sourceTable.setItem(row_count, 3, QTableWidgetItem(source_value))
            # Store numeric value in hidden column (for sorting, if needed)
            self.ui.sourceTable.setItem(row_count, 4, QTableWidgetItem(str(numeric_value)))
            
            total_value += numeric_value
            
            # Lock the first three columns so they’re not editable
            for col in range(3):
                self.ui.sourceTable.item(row_count, col).setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

        # Append the totals row
        totals_row = self.ui.sourceTable.rowCount()
        self.ui.sourceTable.insertRow(totals_row)

        # You might choose to display "Total" in the Account Name column (or whichever is appropriate)
        total_label = QTableWidgetItem("Total")
        total_label.setFlags(Qt.ItemIsEnabled)  # Make it read-only
        self.ui.sourceTable.setItem(totals_row, 1, total_label)

        # Display the total in the Source Value column; format as currency if desired.
        total_display = QTableWidgetItem("${:,.2f}".format(total_value))
        total_display.setFlags(Qt.ItemIsEnabled)
        self.ui.sourceTable.setItem(totals_row, 3, total_display)

        # Optionally, style the totals row (for example, set a background color)
        for col in range(self.ui.sourceTable.columnCount()):
            item = self.ui.sourceTable.item(totals_row, col)
            if item is not None:
                item.setBackground(Qt.lightGray)

        self.ui.sourceTable.viewport().update()
        self.ui.sourceTable.repaint()


    def sort_by_value(self):
        """
        Sorts the CSV data by the numeric value and then repopulates the table.
        The totals row is added after the sorted data, so it always stays at the bottom.
        """
        self.ui.sourceTable.setSortingEnabled(False)  # Disable built-in sorting
        
        # Get sorted rows from your CSV module. Toggle sort order based on a flag.
        rows = csv_utils.get_sorted_csv_data(self.sort_ascending)
        if not rows:
            QMessageBox.warning(self, "Warning", "CSV file may be missing or has an unexpected format.")
            return

        self.ui.sourceTable.setRowCount(0)  # Clear table

        total_value = 0
        # Insert sorted data rows
        for numeric_value, row_id, account_name, source_name, source_value in rows:
            row_count = self.ui.sourceTable.rowCount()
            self.ui.sourceTable.insertRow(row_count)
            self.ui.sourceTable.setItem(row_count, 0, QTableWidgetItem(row_id))
            self.ui.sourceTable.setItem(row_count, 1, QTableWidgetItem(account_name))
            self.ui.sourceTable.setItem(row_count, 2, QTableWidgetItem(source_name))
            self.ui.sourceTable.setItem(row_count, 3, QTableWidgetItem(source_value))
            # Hidden numeric value for sorting purposes
            float_item = QTableWidgetItem(str(numeric_value))
            float_item.setData(Qt.UserRole, numeric_value)
            self.ui.sourceTable.setItem(row_count, 4, float_item)
            
            total_value += numeric_value

            # Lock the first three columns from editing
            for col in range(3):
                self.ui.sourceTable.item(row_count, col).setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

        # Append the totals row after all data rows
        totals_row = self.ui.sourceTable.rowCount()
        self.ui.sourceTable.insertRow(totals_row)
        total_label = QTableWidgetItem("Total")
        total_label.setFlags(Qt.ItemIsEnabled)
        self.ui.sourceTable.setItem(totals_row, 1, total_label)

        total_display = QTableWidgetItem("${:,.2f}".format(total_value))
        total_display.setFlags(Qt.ItemIsEnabled)
        self.ui.sourceTable.setItem(totals_row, 3, total_display)
        
        darkBlue = QBrush(QColor(0, 0, 204))
        # Style the totals row
        for col in range(self.ui.sourceTable.columnCount()):
            item = self.ui.sourceTable.item(totals_row, col)
            if item is not None:
                item.setBackground(darkBlue)

        self.ui.sourceTable.viewport().update()
        self.ui.sourceTable.repaint()
        
        # Toggle the sort order for next time
        self.sort_ascending = not self.sort_ascending




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

    def reset_to_initial_state(self):
        """Resets the table to its initial state by reloading from CSV and populating group totals."""
        
        # Reload data from CSV file.
        self.load_from_csv()
        
        # Populate table with group totals again.
        self.populate_table_with_group_totals()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
