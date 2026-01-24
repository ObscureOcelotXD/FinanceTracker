document.addEventListener("click", (event) => {
  const tables = [
    { id: "stocks-table", buttonId: "clear-active-cell-btn" },
    { id: "realized-table", buttonId: "clear-realized-active-cell-btn" },
  ];

  tables.forEach(({ id, buttonId }) => {
    const table = document.getElementById(id);
    if (!table) return;

    const tableContainer = table.closest(".dash-table-container");
    if (!tableContainer) return;

    if (!tableContainer.contains(event.target)) {
      const clearButton = document.getElementById(buttonId);
      if (clearButton) {
        clearButton.click();
      }
    }
  });
});
