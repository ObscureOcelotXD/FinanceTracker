# stocks_realized.py
import dash
from dash import html, dcc, ctx
from dash.dash_table import DataTable, FormatTemplate
import dash_bootstrap_components as dbc
import db_manager
import pandas as pd
from datetime import datetime
from dash.dependencies import Output, Input, State
from dash.exceptions import PreventUpdate


dash.register_page(
    __name__,
    path="/stocks_realized",
    name="Realized Gains",
    layout=dbc.Container(
        [
            dcc.Store(id="realized-store", data=0),
            dcc.ConfirmDialog(id="confirm-realized-delete"),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Button(
                            [html.I(className="bi bi-house-door me-2"), "Home"],
                            href="/",
                            color="secondary",
                            className="mb-3 mt-2 stocks-home-btn",
                            external_link=True,
                        ),
                        width="auto",
                    )
                ],
                justify="start",
            ),
            dbc.Row(
                dbc.Col(
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.I(className="bi bi-cash-stack stocks-hero-icon"),
                                    html.Div(
                                        [
                                            html.H2(
                                                "Realized Gains",
                                                className="stocks-hero-title",
                                            ),
                                            html.P(
                                                "Record sales, proceeds, and tax-year realized P&L.",
                                                className="stocks-hero-subtitle mb-0",
                                            ),
                                        ],
                                        className="flex-grow-1",
                                    ),
                                ],
                                className="d-flex align-items-start gap-3",
                            ),
                        ],
                        className="neon-panel neon-green stocks-hero-banner mb-3",
                    ),
                    width=12,
                )
            ),
            dbc.Row(
                dbc.Col(
                    dbc.ButtonGroup(
                        [
                            dbc.Button(
                                "Unrealized",
                                href="/dashboard/stocks_manage",
                                color="secondary",
                                className="px-4",
                            ),
                            dbc.Button(
                                "Realized",
                                href="/dashboard/stocks_realized",
                                color="success",
                                className="px-4",
                            ),
                        ],
                        className="mb-4 stocks-mode-toggle",
                    ),
                    width="auto",
                ),
                justify="center",
            ),
            dbc.Row(
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.Div("Add or Update", className="neon-title"),
                                                    html.Div("Track realized gains by year", className="neon-subtitle"),
                                                ]
                                            ),
                                        ],
                                        className="neon-card-header",
                                    ),
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                dcc.Input(
                                                    id="realized-ticker-input",
                                                    type="text",
                                                    placeholder="Ticker (e.g. MSFT)",
                                                    className="form-control mb-2",
                                                ),
                                                width=2,
                                            ),
                                            dbc.Col(
                                                dcc.Input(
                                                    id="realized-shares-input",
                                                    type="number",
                                                    placeholder="Shares",
                                                    min=0,
                                                    step=1,
                                                    className="form-control mb-2",
                                                ),
                                                width=2,
                                            ),
                                            dbc.Col(
                                                dcc.Input(
                                                    id="realized-proceeds-input",
                                                    type="number",
                                                    placeholder="Proceeds",
                                                    min=0,
                                                    step=0.01,
                                                    className="form-control mb-2",
                                                ),
                                                width=2,
                                            ),
                                            dbc.Col(
                                                dcc.Input(
                                                    id="realized-cost-basis-input",
                                                    type="number",
                                                    placeholder="Cost basis",
                                                    min=0,
                                                    step=0.01,
                                                    className="form-control mb-2",
                                                ),
                                                width=2,
                                            ),
                                            dbc.Col(
                                                dcc.Input(
                                                    id="realized-fees-input",
                                                    type="number",
                                                    placeholder="Fees (optional)",
                                                    min=0,
                                                    step=0.01,
                                                    className="form-control mb-2",
                                                ),
                                                width=2,
                                            ),
                                            dbc.Col(
                                                dcc.Input(
                                                    id="realized-tax-year-input",
                                                    type="number",
                                                    placeholder="Tax year",
                                                    min=1900,
                                                    step=1,
                                                    className="form-control mb-2",
                                                ),
                                                width=2,
                                            ),
                                        ]
                                    ),
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                dcc.DatePickerSingle(
                                                    id="realized-buy-date-input",
                                                    placeholder="Buy date",
                                                    className="mb-2",
                                                ),
                                                width=3,
                                            ),
                                            dbc.Col(
                                                dcc.DatePickerSingle(
                                                    id="realized-sell-date-input",
                                                    placeholder="Sell date",
                                                    className="mb-2",
                                                ),
                                                width=3,
                                            ),
                                            dbc.Col(
                                                dbc.Button(
                                                    [html.I(className="bi bi-plus-lg me-1"), "Add / Update"],
                                                    id="add-realized-button",
                                                    color="success",
                                                    className="w-100 mb-2 neon-action-btn",
                                                ),
                                                width=3,
                                            ),
                                        ],
                                        className="align-items-end",
                                    ),
                                    dbc.Alert(id="realized-form-output", color="success", is_open=False),
                                ]
                            ),
                        ],
                        className="mb-4 neon-panel neon-green",
                    ),
                    xs=12,
                    lg=10,
                    className="mx-auto",
                )
            ),
            dbc.Row(
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.Div("Realized Gains", className="neon-title"),
                                                    html.Div("Sales, proceeds, and profit", className="neon-subtitle"),
                                                ]
                                            ),
                                        ],
                                        className="neon-card-header",
                                    ),
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                dcc.Dropdown(
                                                    id="realized-year-filter",
                                                    options=[],
                                                    value=datetime.now().year,
                                                    placeholder="Select tax year...",
                                                    className="chart-dropdown",
                                                ),
                                                width=4,
                                            )
                                        ],
                                        className="mb-3",
                                    ),
                                    html.Button(id="clear-realized-active-cell-btn", style={"display": "none"}),
                                    DataTable(
                                        id="realized-table",
                                        editable=True,
                                        cell_selectable=True,
                                        row_deletable=False,
                                        row_selectable="single",
                                        columns=[
                                            {"name": "Ticker", "id": "ticker"},
                                            {"name": "Shares", "id": "shares", "type": "numeric", "editable": True},
                                            {"name": "Buy Date", "id": "buy_date", "editable": True},
                                            {"name": "Sell Date", "id": "sell_date", "editable": True},
                                            {
                                                "name": "Proceeds",
                                                "id": "proceeds",
                                                "type": "numeric",
                                                "format": FormatTemplate.money(2),
                                                "editable": True,
                                            },
                                            {
                                                "name": "Cost Basis",
                                                "id": "cost_basis",
                                                "type": "numeric",
                                                "format": FormatTemplate.money(2),
                                                "editable": True,
                                            },
                                            {
                                                "name": "Fees",
                                                "id": "fees",
                                                "type": "numeric",
                                                "format": FormatTemplate.money(2),
                                                "editable": True,
                                            },
                                            {
                                                "name": "Realized Gain",
                                                "id": "realized_gain",
                                                "type": "numeric",
                                                "format": FormatTemplate.money(2),
                                                "editable": False,
                                            },
                                            {
                                                "name": "% Gain",
                                                "id": "realized_gain_pct",
                                                "type": "numeric",
                                                "format": FormatTemplate.percentage(2),
                                                "editable": False,
                                            },
                                            {"name": "Tax Year", "id": "tax_year", "editable": True},
                                        ],
                                        data=[],
                                        style_table={"overflowX": "auto"},
                                        style_cell={"textAlign": "center"},
                                        style_header={
                                            "backgroundColor": "rgba(6, 78, 59, 0.92)",
                                            "fontWeight": "bold",
                                            "color": "#d1fae5",
                                            "borderBottom": "1px solid rgba(16, 185, 129, 0.35)",
                                        },
                                        style_data={"backgroundColor": "#11181f"},
                                        style_data_conditional=[
                                            {
                                                "if": {"filter_query": "{ticker} = 'TOTAL'"},
                                                "backgroundColor": "#1a242f",
                                                "fontWeight": "bold",
                                            },
                                            {
                                                "if": {"filter_query": "{ticker} = 'TOTAL'"},
                                                "pointerEvents": "none",
                                            },
                                            {
                                                "if": {"filter_query": "{realized_gain} > 0", "column_id": "realized_gain"},
                                                "color": "#22c55e",
                                            },
                                            {
                                                "if": {"filter_query": "{realized_gain} < 0", "column_id": "realized_gain"},
                                                "color": "#ef4444",
                                            },
                                            {
                                                "if": {"filter_query": "{realized_gain_pct} > 0", "column_id": "realized_gain_pct"},
                                                "color": "#22c55e",
                                            },
                                            {
                                                "if": {"filter_query": "{realized_gain_pct} < 0", "column_id": "realized_gain_pct"},
                                                "color": "#ef4444",
                                            },
                                            {
                                                "if": {"state": "active"},
                                                "backgroundColor": "#ffffff",
                                                "color": "#000000",
                                                "border": "1px solid #000000",
                                            },
                                            {
                                                "if": {"state": "selected"},
                                                "backgroundColor": "#11181f",
                                                "color": "#ffffff",
                                            },
                                        ],
                                        filter_action="native",
                                        sort_action="native",
                                        page_size=10,
                                    ),
                                    html.Br(),
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                dbc.Button(
                                                    "Delete Selected",
                                                    id="delete-realized-btn",
                                                    color="danger",
                                                    className="mb-2",
                                                ),
                                                width="auto",
                                            ),
                                        ],
                                        justify="start",
                                    ),
                                    dbc.Alert(id="realized-edit-feedback", color="warning", is_open=False, className="mt-2"),
                                    dbc.Toast(
                                        "Saved",
                                        id="realized-save-toast",
                                        header="Auto-save",
                                        is_open=False,
                                        duration=2000,
                                        dismissable=True,
                                        icon="success",
                                        className="mt-2",
                                    ),
                                ]
                            ),
                        ],
                        className="mb-4 neon-panel neon-green privacy-sensitive-visual",
                    ),
                    xs=12,
                    lg=10,
                    className="mx-auto",
                )
            ),
        ],
        fluid=True,
        className="stocks-page-shell px-3 px-md-4 py-3",
    ),
)


@dash.callback(
    [
        Output("realized-form-output", "children"),
        Output("realized-form-output", "is_open"),
        Output("realized-store", "data"),
    ],
    Input("add-realized-button", "n_clicks"),
    [
        State("realized-ticker-input", "value"),
        State("realized-shares-input", "value"),
        State("realized-proceeds-input", "value"),
        State("realized-cost-basis-input", "value"),
        State("realized-fees-input", "value"),
        State("realized-buy-date-input", "date"),
        State("realized-sell-date-input", "date"),
        State("realized-tax-year-input", "value"),
        State("realized-store", "data"),
    ],
)
def add_realized_gain(
    n_clicks,
    ticker,
    shares,
    proceeds,
    cost_basis,
    fees,
    buy_date,
    sell_date,
    tax_year,
    store_data,
):
    if not n_clicks:
        raise PreventUpdate
    if not ticker or shares is None or proceeds is None or cost_basis is None:
        return "Enter ticker, shares, proceeds, and cost basis.", True, dash.no_update
    ticker = ticker.upper().strip()
    if not tax_year:
        if sell_date:
            tax_year = datetime.fromisoformat(sell_date).year
        else:
            return "Enter a tax year or sell date.", True, dash.no_update
    try:
        tax_year = int(tax_year)
    except (TypeError, ValueError):
        return "Tax year must be a number.", True, dash.no_update
    try:
        db_manager.insert_realized_gain(
            ticker=ticker,
            shares=shares,
            proceeds=proceeds,
            cost_basis=cost_basis,
            fees=fees,
            buy_date=buy_date,
            sell_date=sell_date,
            tax_year=tax_year,
        )
        msg = f"Added realized gain for {ticker}."
        return msg, True, (store_data or 0) + 1
    except Exception as e:
        return f"Error: {e}", True, dash.no_update


@dash.callback(
    [
        Output("realized-store", "data", allow_duplicate=True),
        Output("realized-edit-feedback", "children", allow_duplicate=True),
        Output("realized-edit-feedback", "is_open", allow_duplicate=True),
        Output("realized-save-toast", "is_open", allow_duplicate=True),
    ],
    Input("realized-table", "data_timestamp"),
    [
        State("realized-table", "data_previous"),
        State("realized-table", "data"),
        State("realized-store", "data"),
    ],
    prevent_initial_call=True,
)
def sync_realized_modify(data_ts, prev, current, store_data):
    if prev is None:
        raise PreventUpdate
    prev_rows = [r for r in prev if r.get("ticker") != "TOTAL" and r.get("id") is not None]
    curr_rows = [r for r in current if r.get("ticker") != "TOTAL" and r.get("id") is not None]
    prev_ids = {r["id"] for r in prev_rows}
    curr_ids = {r["id"] for r in curr_rows}
    deleted = prev_ids - curr_ids
    edited = [
        (old, new)
        for old, new in zip(prev_rows, curr_rows)
        if any(
            old.get(k) != new.get(k)
            for k in [
                "ticker",
                "shares",
                "buy_date",
                "sell_date",
                "proceeds",
                "cost_basis",
                "fees",
                "tax_year",
            ]
        )
    ]
    if deleted:
        for rid in deleted:
            db_manager.delete_realized_gain(rid)
    if edited:
        for _, new_row in edited:
            db_manager.update_realized_gain(
                new_row["id"],
                ticker=new_row.get("ticker"),
                shares=new_row.get("shares"),
                proceeds=new_row.get("proceeds"),
                cost_basis=new_row.get("cost_basis"),
                fees=new_row.get("fees"),
                buy_date=new_row.get("buy_date"),
                sell_date=new_row.get("sell_date"),
                tax_year=new_row.get("tax_year"),
            )
    if not deleted and not edited:
        raise PreventUpdate
    return (store_data or 0) + 1, "", False, True


@dash.callback(
    [
        Output("confirm-realized-delete", "displayed"),
        Output("confirm-realized-delete", "message"),
        Output("realized-edit-feedback", "children", allow_duplicate=True),
        Output("realized-edit-feedback", "is_open", allow_duplicate=True),
    ],
    Input("delete-realized-btn", "n_clicks"),
    [State("realized-table", "selected_rows"), State("realized-table", "data")],
    prevent_initial_call=True,
)
def confirm_realized_delete(n_clicks, selected_rows, current):
    if not n_clicks:
        raise PreventUpdate
    if not selected_rows:
        return False, "", "Select a row to delete.", True
    row = current[selected_rows[0]]
    if row.get("ticker") == "TOTAL":
        return False, "", "Cannot delete totals row.", True
    msg = f"Delete {row.get('ticker')}?"
    return True, msg, "", False


@dash.callback(
    [
        Output("realized-store", "data", allow_duplicate=True),
        Output("realized-edit-feedback", "children", allow_duplicate=True),
        Output("realized-edit-feedback", "is_open", allow_duplicate=True),
    ],
    Input("confirm-realized-delete", "submit_n_clicks"),
    [
        State("realized-table", "selected_rows"),
        State("realized-table", "data"),
        State("realized-store", "data"),
    ],
    prevent_initial_call=True,
)
def delete_realized_selected(submit_n_clicks, selected_rows, current, store_data):
    if not submit_n_clicks:
        raise PreventUpdate
    if not selected_rows:
        return dash.no_update, "Select a row to delete.", True
    row = current[selected_rows[0]]
    if row.get("ticker") == "TOTAL":
        return dash.no_update, "Cannot delete totals row.", True
    db_manager.delete_realized_gain(row["id"])
    msg = f"Deleted {row.get('ticker')}."
    return (store_data or 0) + 1, msg, True


@dash.callback(
    Output("realized-table", "active_cell"),
    Output("realized-table", "selected_cells"),
    Output("realized-table", "selected_rows"),
    Input("clear-realized-active-cell-btn", "n_clicks"),
    prevent_initial_call=True,
)
def clear_realized_active_cell(n_clicks):
    return None, [], dash.no_update


@dash.callback(
    Output("realized-table", "data", allow_duplicate=True),
    Output("realized-year-filter", "options"),
    Output("realized-year-filter", "value"),
    [
        Input("realized-store", "modified_timestamp"),
        Input("realized-year-filter", "value"),
    ],
    State("realized-store", "data"),
    prevent_initial_call="initial_duplicate",
)
def load_realized_on_init(ts, year_value, store_data):
    df_all = db_manager.get_realized_gains()
    current_year = datetime.now().year
    year_options = [current_year - offset for offset in range(0, 20)]
    options = [{"label": str(y), "value": int(y)} for y in year_options]
    selected_year = int(year_value) if year_value else current_year
    if df_all.empty:
        return [], options, selected_year
    df_all["tax_year"] = pd.to_numeric(df_all["tax_year"], errors="coerce")
    df = df_all[df_all["tax_year"] == selected_year]
    if df.empty:
        return [], options, selected_year
    totals = {
        "ticker": "TOTAL",
        "shares": df["shares"].sum(),
        "proceeds": df["proceeds"].sum(),
        "cost_basis": df["cost_basis"].sum(),
        "fees": df["fees"].sum(),
        "realized_gain": df["realized_gain"].sum(),
        "tax_year": selected_year,
    }
    if totals["cost_basis"]:
        totals["realized_gain_pct"] = totals["realized_gain"] / totals["cost_basis"]
    return df.to_dict("records") + [totals], options, selected_year
