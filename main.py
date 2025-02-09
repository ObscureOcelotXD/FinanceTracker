import sys
import csv
import re
import os
from datetime import datetime
from PySide6.QtWidgets import QApplication, QMainWindow, QTableWidgetItem, QMessageBox
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



if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
