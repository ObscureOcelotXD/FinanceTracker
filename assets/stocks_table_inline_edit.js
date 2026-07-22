// Auto-enter edit mode for editable cells in the Manage Stocks table so that
// a single click puts the cell in text-input mode. This makes Backspace/Delete
// behave like in any normal text field (deleting a character at a time)
// instead of the Dash DataTable default which clears the entire cell when it
// is only "active" (selected) but not yet in edit mode.
(function () {
  "use strict";

  var TABLE_ID = "stocks-table";
  var EDITABLE_COLUMNS = new Set([
    "brokerage",
    "account",
    "ticker",
    "shares",
    "cost_basis",
  ]);

  function dispatchDoubleClick(cell) {
    if (!cell) return;
    if (cell.querySelector("input, textarea")) return; // already editing
    var evt = new MouseEvent("dblclick", {
      bubbles: true,
      cancelable: true,
      view: window,
    });
    cell.dispatchEvent(evt);
  }

  document.addEventListener("click", function (event) {
    var cell = event.target.closest(
      "#" + TABLE_ID + " td.dash-cell[data-dash-column]"
    );
    if (!cell) return;
    var colId = cell.getAttribute("data-dash-column");
    if (!colId || !EDITABLE_COLUMNS.has(colId)) return;
    setTimeout(function () {
      dispatchDoubleClick(cell);
    }, 30);
  });
})();
