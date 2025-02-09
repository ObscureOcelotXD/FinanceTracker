import sys
import csv
import re
import os
from datetime import datetime
from PySide6.QtWidgets import QApplication, QMainWindow, QTableWidgetItem, QMessageBox
from PySide6.QtCore import Qt
from ui_main_window import Ui_FinanceTrackerHomeWindow

CSV_FILENAME = "finance_data.csv"

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_FinanceTrackerHomeWindow()
        self.ui.setupUi(self)

        # ✅ Set table headers
        self.ui.sourceTable.setColumnCount(3)
        self.ui.sourceTable.setHorizontalHeaderLabels(["Account Name","Source Name", "Source Value"])

        # ✅ Connect "Add Source" button to a single method for UI & CSV
        self.ui.addSource.clicked.connect(self.add_source)
        self.ui.deleteRowButton.clicked.connect(self.delete_selected_row)  # Ensure this button exists in the UI

        # ✅ Allow editing only in the "Source Value" column
        self.ui.sourceTable.itemChanged.connect(self.handle_value_edit)

         # ✅ Load existing data on startup
        self.load_from_csv()

    def add_source(self):
        """Handles adding a source name and value to the UI & CSV."""
        source_name = self.ui.textEdit.toPlainText().strip()
        source_value = self.ui.valueAmountEdit.toPlainText().strip()
        account_name = self.ui.accountNameEdit.toPlainText().strip()  # ✅ Ensure account name is used

        if not source_name or not source_value:
            QMessageBox.warning(self, "Input Error", "Both Source Name and Value are required!")
            return

        if not account_name:
            QMessageBox.warning(self, "Input Error", "Please enter an account name before adding sources.")
            return

        # ✅ Validate and clean the source value
        cleaned_value = self.clean_currency_input(source_value)
        if cleaned_value is None:
            QMessageBox.warning(self, "Input Error", "Source Value must be a valid number format!")
            return

        # ✅ Add to the table UI
        row_count = self.ui.sourceTable.rowCount()
        self.ui.sourceTable.insertRow(row_count)
        self.ui.sourceTable.setItem(row_count, 0, QTableWidgetItem(account_name))
        self.ui.sourceTable.setItem(row_count, 1, QTableWidgetItem(source_name))
        self.ui.sourceTable.setItem(row_count, 2, QTableWidgetItem(cleaned_value))

       # ✅ Set Account Name and Source Name as **non-editable**
        self.ui.sourceTable.item(row_count, 0).setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.ui.sourceTable.item(row_count, 1).setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)


        # ✅ Save to CSV immediately
        self.save_to_csv(account_name, source_name, cleaned_value)

        # ✅ Clear input fields
        self.ui.textEdit.clear()
        self.ui.valueAmountEdit.clear()

    def clean_currency_input(self, value):
        """
        Cleans and validates currency input.
        - Allows "$" and "," but removes them for conversion.
        - Ensures proper numeric format.
        """
        value = value.replace("$", "").replace(",", "")

        if not re.match(r"^\d+(\.\d{1,2})?$", value):
            return None

        currency_value = float(value)
        return f"${currency_value:,.2f}"

    def save_to_csv(self, account_name, source_name, source_value):
        """Saves a single source entry to the CSV file."""
        next_id = 1
        if os.path.exists(CSV_FILENAME):
            with open(CSV_FILENAME, "r", newline="") as file:
                reader = csv.reader(file)
                next_id = sum(1 for _ in reader)  # Auto-increment ID based on existing rows

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
                    
                    account_name = row[1]
                    source_name = row[2]  # Column index for SourceName
                    source_value = row[3]  # Column index for SourceValue

                    row_count = self.ui.sourceTable.rowCount()
                    self.ui.sourceTable.insertRow(row_count)

                    self.ui.sourceTable.setItem(row_count, 0, QTableWidgetItem(account_name))
                    self.ui.sourceTable.setItem(row_count, 1, QTableWidgetItem(source_name))
                    self.ui.sourceTable.setItem(row_count, 2, QTableWidgetItem(source_value))
                
                    # ✅ Make Account Name & Source Name **non-editable**
                    self.ui.sourceTable.item(row_count, 0).setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    self.ui.sourceTable.item(row_count, 1).setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)


    def delete_selected_row(self):
        """Deletes the selected row from the UI and CSV file."""
        selected_row = self.ui.sourceTable.currentRow()
        if selected_row == -1:
            QMessageBox.warning(self, "Selection Error", "Please select a row to delete.")
            return

        # Get values from the selected row
        account_name = self.ui.sourceTable.item(selected_row, 0).text()
        source_name = self.ui.sourceTable.item(selected_row, 1).text()
        source_value = self.ui.sourceTable.item(selected_row, 2).text()

        # Remove the row from the table UI
        self.ui.sourceTable.removeRow(selected_row)

        # ✅ Remove the row from CSV
        self.remove_from_csv(account_name, source_name, source_value)

    def remove_from_csv(self, account_name, source_name, source_value):
        """Removes a row from the CSV file by rewriting it without the deleted row."""
        if not os.path.exists(CSV_FILENAME):
            return

        temp_filename = CSV_FILENAME + ".tmp"
        with open(CSV_FILENAME, "r", newline="") as infile, open(temp_filename, "w", newline="") as outfile:
            reader = csv.reader(infile)
            writer = csv.writer(outfile)

            headers = next(reader, None)  # Read header row
            writer.writerow(headers)  # Copy headers

            for row in reader:
                if len(row) < 5:
                    continue  # Skip malformed rows

                # Compare values; if they match the deleted row, skip writing it
                if row[1] == account_name and row[2] == source_name and row[3] == source_value:
                    continue

                writer.writerow(row)  # Write all other rows

        # Replace original CSV with updated file
        os.replace(temp_filename, CSV_FILENAME)

        QMessageBox.information(self, "Success", "Row deleted successfully.")

    def handle_value_edit(self, item):
        """Detects changes to the 'Source Value' column and updates the CSV file."""
        row = item.row()
        column = item.column()

        if column != 2:  # Only allow editing of 'Source Value' column
            return

        # Get updated value
        new_value = item.text().strip()
        cleaned_value = self.clean_currency_input(new_value)
        if cleaned_value is None:
            QMessageBox.warning(self, "Input Error", "Invalid currency format. Please use numbers only (e.g., 100, 100.00).")
            return

        # Update the table with formatted value
        self.ui.sourceTable.item(row, column).setText(cleaned_value)

        # Retrieve other row details to identify the correct entry
        account_name = self.ui.sourceTable.item(row, 0).text()
        source_name = self.ui.sourceTable.item(row, 1).text()

        # ✅ Update CSV file with new value
        self.update_csv(account_name, source_name, cleaned_value)

    def update_csv(self, account_name, source_name, new_value):
        """Updates the CSV file with an edited Source Value."""
        if not os.path.exists(CSV_FILENAME):
            return

        temp_filename = CSV_FILENAME + ".tmp"
        with open(CSV_FILENAME, "r", newline="") as infile, open(temp_filename, "w", newline="") as outfile:
            reader = csv.reader(infile)
            writer = csv.writer(outfile)

            headers = next(reader, None)
            writer.writerow(headers)

            for row in reader:
                if len(row) < 5:
                    continue

                if row[1] == account_name and row[2] == source_name:
                    row[3] = new_value  # Update the Source Value

                writer.writerow(row)

        os.replace(temp_filename, CSV_FILENAME)
        QMessageBox.information(self, "Success", "Value updated successfully!")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
