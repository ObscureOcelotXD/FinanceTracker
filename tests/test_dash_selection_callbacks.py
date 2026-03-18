import dash

import dashApp  # noqa: F401
from dashPages.stocks_manage import clear_active_cell
from dashPages.stocks_realized import clear_realized_active_cell


def test_clear_active_cell_preserves_selected_rows():
    active_cell, selected_cells, selected_rows = clear_active_cell(1)
    assert active_cell is None
    assert selected_cells == []
    assert selected_rows is dash.no_update


def test_clear_realized_active_cell_preserves_selected_rows():
    active_cell, selected_cells, selected_rows = clear_realized_active_cell(1)
    assert active_cell is None
    assert selected_cells == []
    assert selected_rows is dash.no_update
