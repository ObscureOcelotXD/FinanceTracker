import dash
from dash import html, dcc, dash_table, ctx
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
        dbc.Row(dbc.Col(html.H1("Manage Stocks", className="text-center mb-4"), width=12)),

        # Add / update new stock
        dbc.Row(
            dbc.Col(
                dbc.Card([
                    dbc.CardHeader(html.H4("Add Stock")),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col(dcc.Input(id="ticker-input", type="text",
                                              placeholder="Ticker (e.g. NVDA)",
                                              className="form-control mb-2"), width=4),
                            dbc.Col(dcc.Input(id="shares-input", type="number",
                                              placeholder="Shares", min=0, step=1,
                                              className="form-control mb-2"), width=4),
                            dbc.Col(dbc.Button("Add / Update", id="add-stock-button",
                                               color="primary", className="w-100 mb-2"), width=4),
                        ]),
                        html.Div(id="form-output", className="text-success")
                    ])
                ], className="mb-4"),
                width={"size": 8, "offset": 2}
            )
        ),

        # Stocks table & edit row UI
        dbc.Row(
            dbc.Col(
                dbc.Card([
                    dbc.CardHeader(html.H4("Stocks")),
                    dbc.CardBody([
                        dash_table.DataTable(
                            id='stocks-table',
                            row_deletable=True,
                            row_selectable='single',
                            columns=[
                                {"name": "Ticker", "id": "ticker"},
                                {"name": "Shares", "id": "shares", "type": "numeric"}
                            ],
                            data=[],
                            style_table={'overflowX': 'auto'},
                            style_cell={'textAlign': 'center'},
                            page_action="none",
                            style_header={'backgroundColor': '#f4f4f4', 'fontWeight': 'bold'},
                        ),
                        html.Br(),
                        dbc.Row([
                            dbc.Col(dcc.Input(id='edit-shares-input', type='number',
                                              placeholder='New shares', min=0, step=1,
                                              className='form-control'), width=4),
                            dbc.Col(dbc.Button('Update Selected Row', id='update-shares-btn',
                                               color='warning', className='mb-2'), width='auto'),
                        ], justify='start'),
                        html.Div(id='edit-feedback', className='mt-2 text-warning')
                    ])
                ], className="mb-4"),
                width={"size": 8, "offset": 2}
            )
        )
    ], fluid=True)
)

# Add or update new stock
@dash.callback(
    [Output("form-output", "children"),
     Output("stocks-store", "data")],
    Input("add-stock-button", "n_clicks"),
    [State("ticker-input", "value"),
     State("shares-input", "value"),
     State("stocks-store", "data")]
)
def add_stock(n_clicks, ticker, shares, store_data):
    if not n_clicks:
        raise PreventUpdate
    if not ticker or shares is None:
        return "Enter both ticker and shares.", dash.no_update
    ticker = ticker.upper().strip()
    try:
        df = db_manager.get_stocks()
        db_manager.insert_stock(ticker, shares)
        msg = f"Added {ticker} → {shares} shares."
        return msg, (store_data or 0) + 1
    except Exception as e:
        return f"Error: {e}", dash.no_update

# Single callback to sync deletion, edit button, and in-table edits (if any)
@dash.callback(
    [Output('stocks-store', 'data', allow_duplicate=True),
     Output('edit-feedback', 'children')],
    [Input('stocks-table', 'data_previous'),
     Input('update-shares-btn', 'n_clicks')],
    [State('stocks-table', 'data'),
     State('stocks-table', 'selected_rows'),
     State('edit-shares-input', 'value'),
     State('stocks-store', 'data')],
    prevent_initial_call=True
)
def sync_modify(prev, n_clicks_btn, current, selected_rows, new_shares, store_data):
    triggered = ctx.triggered_id
    # deletion or inline change
    if prev is not None and triggered == 'stocks-table':
        prev_ids = {r['id'] for r in prev}
        curr_ids = {r['id'] for r in current}
        deleted = prev_ids - curr_ids
        edited = [(old, new) for old, new in zip(prev, current)
                  if old.get('shares') != new.get('shares')]
        if deleted:
            for sid in deleted:
                db_manager.delete_stock(sid)
        if edited:
            for _, new_row in edited:
                db_manager.update_stock(new_row['id'], None, new_row['shares'])
        if not deleted and not edited:
            raise PreventUpdate
        return (store_data or 0) + 1, ""
    # update via numeric input and button
    elif triggered == 'update-shares-btn':
        if not selected_rows or new_shares is None:
            return dash.no_update, "Select a row and enter valid number."
        row = current[selected_rows[0]]
        try:
            db_manager.update_stock(row['id'], row['ticker'], new_shares)
            msg = f"Updated {row['ticker']} to {new_shares} shares."
            return (store_data or 0) + 1, msg
        except Exception as e:
            return dash.no_update, f"Error: {e}"
    else:
        raise PreventUpdate
    

@dash.callback(
    Output('stocks-table', 'data', allow_duplicate=True),
    [Input('stocks-store', 'modified_timestamp')],
    [State('stocks-store', 'data')],
    prevent_initial_call='initial_duplicate'
)
def load_stocks_on_init(ts, store_data):
    df = db_manager.get_stocks()
    return df.to_dict('records') if not df.empty else []

