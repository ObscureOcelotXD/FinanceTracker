document.addEventListener("click", (event) => {
  const table = document.getElementById("stocks-table");
  if (!table) return;

  const tableContainer = table.closest(".dash-table-container");
  if (!tableContainer) return;

  if (!tableContainer.contains(event.target)) {
    const clearButton = document.getElementById("clear-active-cell-btn");
    if (clearButton) {
      clearButton.click();
    }
  }
});
