import csv
import os
from PySide6.QtWidgets import QMessageBox

CSV_FILENAME = "finance_data.csv"

def handle_value_edit(main_window, item):
    """Detects changes to the 'Source Value' column and updates the CSV file."""
    row = item.row()
    column = item.column()

    if column != 2:  # Only allow editing of 'Source Value' column
        return

    # Get updated value
    new_value = item.text().strip()
    cleaned_value = clean_currency_input(new_value)
    if cleaned_value is None:
        QMessageBox.warning(main_window.ui, "Input Error", "Invalid currency format.")
        return

    # Update the table with formatted value
    main_window.ui.sourceTable.blockSignals(True)  # Block signals before update
    main_window.ui.sourceTable.item(row, column).setText(cleaned_value)
    main_window.ui.sourceTable.blockSignals(False)  # Re-enable signals after update


    # Retrieve other row details to identify the correct entry
    id_item = main_window.ui.sourceTable.item(row, 0)
    row_id = id_item.text() if id_item else None

    if row_id is None:
        QMessageBox.warning(main_window.ui, "Error", "Cannot determine row Id.")
        return


    # Update CSV file
    update_csv(row_id, cleaned_value)

def clean_currency_input(value):
    """Cleans and validates currency input."""
    value = value.replace("$", "").replace(",", "")
    if not value.replace(".", "", 1).isdigit():
        return None
    return f"${float(value):,.2f}"

def update_csv(row_id, new_value):
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

            if row[0] == row_id:
                row[3] = new_value  # Update SourceValue (column 3)

            writer.writerow(row)

    os.replace(temp_filename, CSV_FILENAME)
