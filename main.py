import re
import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QTableWidgetItem, QMessageBox
from ui_main_window import Ui_FinanceTrackerHomeWindow

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_FinanceTrackerHomeWindow()
        self.ui.setupUi(self)

        # ✅ Set table headers
        self.ui.sourceTable.setColumnCount(2)  # Ensure the table has 2 columns
        self.ui.sourceTable.setHorizontalHeaderLabels(["Source Name", "Source Value"])  # Set headers

        # ✅ Ensure the method exists before connecting
        self.ui.addSource.clicked.connect(self.add_source)

    def add_source(self):
        """Handles adding a source to the table."""
        source_name = self.ui.textEdit.toPlainText().strip()
        source_value = self.ui.valueAmountEdit.toPlainText().strip()

        if not source_name or not source_value:
            QMessageBox.warning(self, "Input Error", "Both Source Name and Value are required!")
            return

        # ✅ Validate and clean the source value
        cleaned_value = self.clean_currency_input(source_value)
        if cleaned_value is None:
            QMessageBox.warning(self, "Input Error", "Source Value must be a valid number format!")
            return

        # Add a new row to the table
        row_count = self.ui.sourceTable.rowCount()
        self.ui.sourceTable.insertRow(row_count)
        self.ui.sourceTable.setItem(row_count, 0, QTableWidgetItem(source_name))
        self.ui.sourceTable.setItem(row_count, 1, QTableWidgetItem(cleaned_value))

        # Clear the input fields after adding
        self.ui.textEdit.clear()
        self.ui.valueAmountEdit.clear()


    def clean_currency_input(self, value):
            """
            Cleans and validates currency input.  
            - Allows "$" and "," but removes them for conversion.
            - Ensures proper numeric format (e.g., "50,000.00" or "$500" is allowed, but "5,00.00" is not).
            """
            # Remove dollar signs and commas
            value = value.replace("$", "").replace(",", "")

            # Ensure valid numeric format
            if not re.match(r"^\d+(\.\d{1,2})?$", value):  # Allows whole numbers or 2 decimal places
                return None

            # Convert to float and format as currency
            currency_value = float(value)
            return f"${currency_value:,.2f}"  # Format as "$xx,xxx.xx"

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
