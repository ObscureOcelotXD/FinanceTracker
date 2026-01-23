import dash
from dash import html, dcc, dash_table, ctx
from dash.dash_table import FormatTemplate
import dash_bootstrap_components as dbc
import db_manager
from dash.dependencies import Output, Input, State
from dash.exceptions import PreventUpdate

dash.register_page(
    __name__,
    path="/stocks_manage",
    name="Manage Stocks",
    layout=dbc.Container([
        dcc.Store(id="stocks-store", data=0),
        dcc.ConfirmDialog(id="confirm-delete"),
        dbc.Row(
            [
                dbc.Col(
                    dbc.Button(
                        "🏠 Home",
                        href="/",
                        color="secondary",
                        className="mb-3 mt-2",
                        external_link=True,
                    ),
                    width="auto",
                )
            ],
            justify="start",
        ),
        dbc.Row(dbc.Col(html.H1("Manage Stocks", className="text-center mb-4"), width=12)),

        # Add / update new stock
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
                                                html.Div("Manage positions and cost basis", className="neon-subtitle"),
                                            ]
                                        ),
                                    ],
                                    className="neon-card-header",
                                ),
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            dcc.Input(
                                                id="ticker-input",
                                                type="text",
                                                placeholder="Ticker (e.g. NVDA)",
                                                className="form-control mb-2",
                                            ),
                                            width=3,
                                        ),
                                        dbc.Col(
                                            dcc.Input(
                                                id="shares-input",
                                                type="number",
                                                placeholder="Shares",
                                                min=0,
                                                step=1,
                                                className="form-control mb-2",
                                            ),
                                            width=3,
                                        ),
                                        dbc.Col(
                                            dcc.Input(
                                                id="cost-basis-input",
                                                type="number",
                                                placeholder="Total cost basis",
                                                min=0,
                                                step=0.01,
                                                className="form-control mb-2",
                                            ),
                                            width=3,
                                        ),
                                        dbc.Col(
                                            dbc.Button(
                                                "Add / Update",
                                                id="add-stock-button",
                                                color="primary",
                                                className="w-100 mb-2",
                                            ),
                                            width=3,
                                        ),
                                    ]
                                ),
                                dbc.Alert(id="form-output", color="success", is_open=False),
                            ]
                        ),
                    ],
                    className="mb-4 neon-panel neon-green",
                ),
                width={"size": 6, "offset": 3}
            )
        ),

        # Stocks table & edit row UI
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
                                                html.Div("Stocks", className="neon-title"),
                                                html.Div("Holdings, performance, and edits", className="neon-subtitle"),
                                            ]
                                        ),
                                    ],
                                    className="neon-card-header",
                                ),
                                html.Button(id="clear-active-cell-btn", style={"display": "none"}),
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            dcc.Dropdown(
                                                id="stocks-columns-toggle",
                                                options=[
                                                    {"label": "Ticker", "value": "ticker"},
                                                    {"label": "Shares", "value": "shares"},
                                                    {"label": "Cost Basis", "value": "cost_basis"},
                                                    {"label": "Position Value", "value": "position_value"},
                                                    {"label": "Gain/Loss", "value": "gain_loss"},
                                                    {"label": "% Gain", "value": "gain_loss_pct"},
                                                ],
                                                value=[],
                                                multi=True,
                                                placeholder="Hide columns...",
                                                className="chart-dropdown",
                                            ),
                                            width=6,
                                        )
                                    ],
                                    className="mb-3",
                                ),
                                dash_table.DataTable(
                                    id="stocks-table",
                                    row_deletable=False,
                                    row_selectable="single",
                                    columns=[
                                        {"name": "Ticker", "id": "ticker"},
                                        {"name": "Shares", "id": "shares", "type": "numeric", "editable": True},
                                        {
                                            "name": "Cost Basis",
                                            "id": "cost_basis",
                                            "type": "numeric",
                                            "format": FormatTemplate.money(2),
                                            "editable": True,
                                        },
                                        {
                                            "name": "Position Value",
                                            "id": "position_value",
                                            "type": "numeric",
                                            "format": FormatTemplate.money(2),
                                        },
                                        {
                                            "name": "Gain/Loss",
                                            "id": "gain_loss",
                                            "type": "numeric",
                                            "format": FormatTemplate.money(2),
                                        },
                                        {
                                            "name": "% Gain",
                                            "id": "gain_loss_pct",
                                            "type": "numeric",
                                            "format": FormatTemplate.percentage(2),
                                        },
                                    ],
                                    data=[],
                                    style_table={"overflowX": "auto"},
                                    style_cell={"textAlign": "center"},
                                    style_header={"backgroundColor": "#1f2c3b", "fontWeight": "bold"},
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
                                            "if": {
                                                "filter_query": "{gain_loss} > 0",
                                                "column_id": "gain_loss",
                                            },
                                            "color": "#22c55e",
                                        },
                                        {
                                            "if": {
                                                "filter_query": "{gain_loss} < 0",
                                                "column_id": "gain_loss",
                                            },
                                            "color": "#ef4444",
                                        },
                                        {
                                            "if": {
                                                "filter_query": "{gain_loss_pct} > 0",
                                                "column_id": "gain_loss_pct",
                                            },
                                            "color": "#22c55e",
                                        },
                                        {
                                            "if": {
                                                "filter_query": "{gain_loss_pct} < 0",
                                                "column_id": "gain_loss_pct",
                                            },
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
                                            dcc.Input(
                                                id="edit-shares-input",
                                                type="number",
                                                placeholder="New shares",
                                                min=0,
                                                step=1,
                                                className="form-control",
                                            ),
                                            width=3,
                                        ),
                                        dbc.Col(
                                            dcc.Input(
                                                id="edit-cost-basis-input",
                                                type="number",
                                                placeholder="New total cost basis",
                                                min=0,
                                                step=0.01,
                                                className="form-control",
                                            ),
                                            width=3,
                                        ),
                                        dbc.Col(
                                            dbc.Button(
                                                "Update Selected Row",
                                                id="update-shares-btn",
                                                color="warning",
                                                className="mb-2",
                                            ),
                                            width="auto",
                                        ),
                                        dbc.Col(
                                            dbc.Button(
                                                "Delete Selected",
                                                id="delete-stock-btn",
                                                color="danger",
                                                className="mb-2",
                                            ),
                                            width="auto",
                                        ),
                                    ],
                                    justify="start",
                                ),
                                dbc.Alert(id="edit-feedback", color="warning", is_open=False, className="mt-2"),
                            ]
                        ),
                    ],
                    className="mb-4 neon-panel neon-yellow",
                ),
                width={"size": 8, "offset": 2}
            )
        )
    ], fluid=True)
)

# Add or update new stock
@dash.callback(
    [Output("form-output", "children"),
     Output("form-output", "is_open"),
     Output("stocks-store", "data")],
    Input("add-stock-button", "n_clicks"),
    [State("ticker-input", "value"),
     State("shares-input", "value"),
     State("cost-basis-input", "value"),
     State("stocks-store", "data")]
)
def add_stock(n_clicks, ticker, shares, cost_basis, store_data):
    if not n_clicks:
        raise PreventUpdate
    if not ticker or shares is None:
        return "Enter ticker and shares.", True, dash.no_update
    ticker = ticker.upper().strip()
    try:
        df = db_manager.get_stocks()
        existing = df[df["ticker"] == ticker]
        if not existing.empty:
            stock_id = int(existing.iloc[0]["id"])
            db_manager.update_stock(stock_id, ticker=ticker, shares=shares, cost_basis=cost_basis)
            msg = f"Updated {ticker} → {shares} shares."
        else:
            db_manager.insert_stock(ticker, shares, cost_basis=cost_basis)
            msg = f"Added {ticker} → {shares} shares."
        return msg, True, (store_data or 0) + 1
    except Exception as e:
        return f"Error: {e}", True, dash.no_update

# Single callback to sync deletion, edit button, and in-table edits (if any)
@dash.callback(
    [Output("stocks-store", "data", allow_duplicate=True),
     Output("edit-feedback", "children", allow_duplicate=True),
     Output("edit-feedback", "is_open", allow_duplicate=True)],
    [Input('stocks-table', 'data_previous'),
     Input('update-shares-btn', 'n_clicks')],
    [State('stocks-table', 'data'),
     State('stocks-table', 'selected_rows'),
     State('edit-shares-input', 'value'),
     State('edit-cost-basis-input', 'value'),
     State('stocks-store', 'data')],
    prevent_initial_call=True
)
def sync_modify(prev, n_clicks_btn, current, selected_rows, new_shares, new_cost_basis, store_data):
    triggered = ctx.triggered_id
    # deletion or inline change
    if prev is not None and triggered == 'stocks-table':
        prev_ids = {r['id'] for r in prev}
        curr_ids = {r['id'] for r in current}
        deleted = prev_ids - curr_ids
        edited = [(old, new) for old, new in zip(prev, current)
                  if old.get('shares') != new.get('shares') or old.get('cost_basis') != new.get('cost_basis')]
        if deleted:
            for sid in deleted:
                db_manager.delete_stock(sid)
        if edited:
            for _, new_row in edited:
                db_manager.update_stock(
                    new_row['id'],
                    ticker=new_row['ticker'],
                    shares=new_row['shares'],
                    cost_basis=new_row.get('cost_basis'),
                )
        if not deleted and not edited:
            raise PreventUpdate
        return (store_data or 0) + 1, "", False
    # update via numeric input and button
    elif triggered == 'update-shares-btn':
        if not selected_rows or (new_shares is None and new_cost_basis is None):
            return dash.no_update, "Select a row and enter valid values.", True
        row = current[selected_rows[0]]
        try:
            db_manager.update_stock(
                row['id'],
                ticker=row['ticker'],
                shares=new_shares,
                cost_basis=new_cost_basis,
            )
            msg = f"Updated {row['ticker']}."
            return (store_data or 0) + 1, msg, True
        except Exception as e:
            return dash.no_update, f"Error: {e}", True
    else:
        raise PreventUpdate


@dash.callback(
    [Output("confirm-delete", "displayed"),
     Output("confirm-delete", "message"),
     Output("edit-feedback", "children", allow_duplicate=True),
     Output("edit-feedback", "is_open", allow_duplicate=True)],
    Input("delete-stock-btn", "n_clicks"),
    [State("stocks-table", "selected_rows"),
     State("stocks-table", "data")],
    prevent_initial_call=True,
)
def confirm_delete(n_clicks, selected_rows, current):
    if not n_clicks:
        raise PreventUpdate
    if not selected_rows:
        return False, "", "Select a row to delete.", True
    row = current[selected_rows[0]]
    msg = f"Delete {row['ticker']}?"
    return True, msg, "", False


@dash.callback(
    [Output("stocks-store", "data", allow_duplicate=True),
     Output("edit-feedback", "children", allow_duplicate=True),
     Output("edit-feedback", "is_open", allow_duplicate=True)],
    Input("confirm-delete", "submit_n_clicks"),
    [State("stocks-table", "selected_rows"),
     State("stocks-table", "data"),
     State("stocks-store", "data")],
    prevent_initial_call=True,
)
def delete_selected(submit_n_clicks, selected_rows, current, store_data):
    if not submit_n_clicks:
        raise PreventUpdate
    if not selected_rows:
        return dash.no_update, "Select a row to delete.", True
    row = current[selected_rows[0]]
    db_manager.delete_stock(row["id"])
    msg = f"Deleted {row['ticker']}."
    return (store_data or 0) + 1, msg, True
    

@dash.callback(
    Output("stocks-table", "hidden_columns"),
    Input("stocks-columns-toggle", "value"),
)
def toggle_columns(hidden_columns):
    return hidden_columns or []


@dash.callback(
    Output("stocks-table", "active_cell"),
    Output("stocks-table", "selected_cells"),
    Output("stocks-table", "selected_rows"),
    Input("clear-active-cell-btn", "n_clicks"),
    prevent_initial_call=True,
)
def clear_active_cell(n_clicks):
    return None, [], []


@dash.callback(
    Output('stocks-table', 'data', allow_duplicate=True),
    [Input('stocks-store', 'modified_timestamp')],
    [State('stocks-store', 'data')],
    prevent_initial_call='initial_duplicate'
)
def load_stocks_on_init(ts, store_data):
    df = db_manager.get_stocks()
    if df.empty:
        return []
    totals = {
        "ticker": "TOTAL",
        "shares": df["shares"].sum(),
        "cost_basis": df["cost_basis"].sum(),
        "position_value": df["position_value"].sum(),
        "gain_loss": df["gain_loss"].sum(),
    }
    if totals["cost_basis"]:
        totals["gain_loss_pct"] = totals["gain_loss"] / totals["cost_basis"]
    return df.to_dict("records") + [totals]

