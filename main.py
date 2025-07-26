import sys
from datetime import datetime
from collections import defaultdict
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QApplication, QMainWindow, QTableWidgetItem, QMessageBox
from PySide6.QtCore import Qt
from ui_main_window import Ui_FinanceTrackerHomeWindow
from threading import Thread
from dash import Dash, html, dcc
import dash_bootstrap_components as dbc  # Optional for styling
from handlers.add_handler import add_source
from handlers.edit_handler import handle_value_edit
from handlers.delete_handler import delete_selected_row
from runServer import flask_app
import db_manager

# print(flask_app.url_map)

# region PySide6 UI Code
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
        # self.ui.addSource.clicked.connect(self.handle_add_source)
        self.ui.sourceTable.itemChanged.connect(lambda item: handle_value_edit(self, item))
        self.ui.deleteRowButton.clicked.connect(lambda: delete_selected_row(self.ui))

        self.ui.resetButton.clicked.connect(self.reset_to_initial_state)
        db_manager.init_db()
         # ✅ Load existing data on startup
        self.populate_table_with_group_totals()



    def populate_table_with_group_totals(self):
        """
        Populates the table by grouping data rows by Account Name,
        then adds a totals row for each account with a green background.
        """
        records = db_manager.get_all_records()

        if records is None:
            QMessageBox.warning(self, "Warning", "db file may be missing or has an unexpected format.")
            return

        # Group rows by account name
        groups = defaultdict(list)
        for row in records:
            if len(row) < 4: continue #update to 5 when date is added in.
            id, account_name, source_name, source_value = row
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
            for id, account_name, source_name, source_value in account_rows:
                row_count = self.ui.sourceTable.rowCount()
                self.ui.sourceTable.insertRow(row_count)
                #print(f"Row count: {id}, {account_name}, {source_name}, {source_value}")
                formatted_value = "${:,.2f}".format(source_value)
                # Insert data into the row
                self.ui.sourceTable.setItem(row_count, 0, QTableWidgetItem(str(id)))
                self.ui.sourceTable.setItem(row_count, 1, QTableWidgetItem(account_name))
                self.ui.sourceTable.setItem(row_count, 2, QTableWidgetItem(source_name))
                self.ui.sourceTable.setItem(row_count, 3, QTableWidgetItem(formatted_value))
                # Hidden numeric value in column 4 for sorting
                float_item = QTableWidgetItem()
                float_item.setData(Qt.UserRole, source_value)
                self.ui.sourceTable.setItem(row_count, 4, float_item)

                account_total += source_value

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
            total_float_item = QTableWidgetItem()
            total_float_item.setData(Qt.UserRole, account_total)
            self.ui.sourceTable.setItem(totals_row, 4, total_float_item)

            # Set the background for every cell in the totals row to green
            for col in range(self.ui.sourceTable.columnCount()):
                item = self.ui.sourceTable.item(totals_row, col)
                if item:
                    item.setBackground(green_brush)

        # Force an update of the table view
        self.ui.sourceTable.viewport().update()
        self.ui.sourceTable.repaint()

    def sort_by_value(self):
        """
        Sorts the CSV data by the numeric value and then repopulates the table.
        The totals row is added after the sorted data, so it always stays at the bottom.
        """
        self.ui.sourceTable.setSortingEnabled(False)  # Disable built-in sorting
        
        # Get sorted rows from your CSV module. Toggle sort order based on a flag.
        records = db_manager.get_all_records()
        if records is None:
            QMessageBox.warning(self, "Warning", "CSV file may be missing or has an unexpected format.")
            return
        
        # Sort the data by Source Value (numeric value).
        sorted_rows = sorted(records, key=lambda x: x[3], reverse=not self.sort_ascending)

        self.ui.sourceTable.setRowCount(0)  # Clear table

        total_value = 0
        # Insert sorted data rows
        for id, account_name, source_name, source_value in sorted_rows:
            row_count = self.ui.sourceTable.rowCount()
            self.ui.sourceTable.insertRow(row_count)
            formatted_value = "${:,.2f}".format(source_value)
            self.ui.sourceTable.setItem(row_count, 0, QTableWidgetItem(str(id)))
            self.ui.sourceTable.setItem(row_count, 1, QTableWidgetItem(account_name))
            self.ui.sourceTable.setItem(row_count, 2, QTableWidgetItem(source_name))
            self.ui.sourceTable.setItem(row_count, 3, QTableWidgetItem(formatted_value))
            # Hidden numeric value for sorting purposes
            float_item = QTableWidgetItem()
            float_item.setData(Qt.UserRole, source_value)
            self.ui.sourceTable.setItem(row_count, 4, float_item)
            
            total_value += source_value

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


    def reset_to_initial_state(self):
        """Resets the table to its initial state by reloading from CSV and populating group totals."""
        
        self.populate_table_with_group_totals()
# endregion

def run_flask():
    # Optional: add callbacks to update your dashboard here.
    print("🚀 Starting Flask (with Dash) on http://127.0.0.1:5000")
    flask_app.run(host="127.0.0.1", port=5000, use_reloader=False)



if __name__ == '__main__':
    # Start Flask server in a separate thread
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    import dashApp as dashApp
    import dash_callbacks
    # Start the Qt application
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    # Update stock prices needs to run here so db has time to initialize.
    import api.alpha_api as av
    av.update_stock_prices()
    
    # Run the application event loop
    try:
        exit_code = app.exec()
    finally:
        # Perform any necessary cleanup here
        print("Shutting down the application...")

    sys.exit(exit_code)

