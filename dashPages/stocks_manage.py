import dash
from dash import html, dcc, dash_table
import dash_bootstrap_components as dbc
import db_manager

# Register this page for managing stocks.
dash.register_page(
    __name__,
    path="/stocks_manage",
    name="Manage Stocks",
    layout=dbc.Container([
        dbc.Row(
            dbc.Col(
                html.H1("Manage Stocks", className="text-center mb-4"),
                width=12
            )
        ),
        dbc.Row([
            dbc.Col(
                dbc.Card([
                    dbc.CardHeader(html.H4("Add / Edit Stock", className="card-title")),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col(
                                dcc.Input(
                                    id="ticker-input", type="text", placeholder="Ticker (e.g., NVDA)",
                                    className="form-control", style={"marginBottom": "10px"}
                                ),
                                width=4
                            ),
                            dbc.Col(
                                dcc.Input(
                                    id="shares-input", type="number", placeholder="Shares", min=0, step="any",
                                    className="form-control", style={"marginBottom": "10px"}
                                ),
                                width=4
                            ),
                            dbc.Col(
                                html.Button("Add/Update", id="add-stock-button", n_clicks=0,
                                            className="btn btn-primary btn-block"),
                                width=4
                            )
                        ]),
                        html.Div(id="form-output", className="mt-2 text-success")
                    ])
                ], className="mb-4"),
                width={"size": 8, "offset": 2}
            )
        ]),
        dbc.Row(
            dbc.Col(
                dbc.Card([
                    dbc.CardHeader(html.H4("Stocks List", className="card-title")),
                    dbc.CardBody(
                        dash_table.DataTable(
                            id='stocks-table',
                            columns=[
                                {"name": "ID", "id": "id", "hideable": True, "hidden": True},
                                {"name": "Ticker", "id": "ticker"},
                                {"name": "Shares", "id": "shares"},
                                {"name": "Actions", "id": "actions", "presentation": "markdown"}
                            ],
                            data=[],
                            style_table={'overflowX': 'auto'},
                            style_cell={'textAlign': 'center'},
                            page_action="none",
                            style_header={'backgroundColor': '#f4f4f4', 'fontWeight': 'bold'},
                            markdown_options={"html": True},
                        )
                    )
                ], className="mb-4"),
                width={"size": 8, "offset": 2}
            )
        )
    ], fluid=True)
)

# Callback for loading the stocks table data.
@dash.callback(
    dash.dependencies.Output('stocks-table', 'data'),
    [dash.dependencies.Input('interval-component', 'n_intervals'),
     dash.dependencies.Input('stocks-store', 'data')]
)
def load_stocks_table(n_intervals, store_data):
    df = db_manager.get_stocks()
    if df.empty:
        return []
    data = df.to_dict("records")
    for record in data:
        # Use Bootstrap classes for a nicely styled delete button.
        record["actions"] = f'<button class="btn btn-danger btn-sm" data-id="{record["id"]}">Delete</button>'
    return data

# Callback for adding/updating a stock.
@dash.callback(
    [dash.dependencies.Output("form-output", "children"), dash.dependencies.Output("stocks-store", "data")],
    [dash.dependencies.Input("add-stock-button", "n_clicks")],
    [dash.dependencies.State("ticker-input", "value"), 
     dash.dependencies.State("shares-input", "value"), 
     dash.dependencies.State("stocks-store", "data")]
)
def add_update_stock(n_clicks, ticker, shares, store_data):
    if n_clicks:
        if not ticker or shares is None:
            return "Please enter both ticker and shares.", store_data
        ticker = ticker.upper().strip()
        try:
            df = db_manager.get_stocks()
            if not df.empty and ticker in df["ticker"].values:
                record = df[df["ticker"] == ticker].iloc[0]
                db_manager.update_stock(record["id"], ticker, shares)
                message = f"Updated {ticker} with {shares} shares."
            else:
                db_manager.insert_stock(ticker, shares)
                message = f"Added {ticker} with {shares} shares."
            store_data = (store_data + 1) if isinstance(store_data, int) else 1
            return message, store_data
        except Exception as e:
            return f"Error: {str(e)}", store_data
    return "", store_data

# Callback for deleting a stock.
@dash.callback(
    dash.dependencies.Output("dummy-output-delete", "children"),
    [dash.dependencies.Input("stocks-table", "active_cell")],
    [dash.dependencies.State("stocks-table", "data")]
)
def delete_stock(active_cell, table_data):
    if active_cell and table_data:
        row = active_cell.get("row")
        col = active_cell.get("column_id")
        if col == "actions" and row is not None and row < len(table_data):
            stock_id = table_data[row].get("id")
            try:
                db_manager.delete_stock(stock_id)
                return f"Deleted stock {stock_id}"
            except Exception as e:
                return f"Error deleting stock: {str(e)}"
    return ""
