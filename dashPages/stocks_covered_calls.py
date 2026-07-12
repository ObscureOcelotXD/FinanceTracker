# stocks_covered_calls.py
from datetime import date

import dash
from dash import Input, Output, State, dash_table, html, no_update
from dash.dash_table import FormatTemplate
from dash.dash_table.Format import Format, Scheme
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
from dash import dcc

from api import covered_calls as cc_api
from services import db_manager

dash.register_page(
    __name__,
    path="/stocks_covered_calls",
    name="Covered Calls",
)

dash_app = dash.get_app()

_money = FormatTemplate.money(2)
_pct = Format(precision=2, scheme=Scheme.fixed).symbol_suffix("%")


def _calendar_children(calendar_rows):
    if not calendar_rows:
        return html.P("No open covered calls on the calendar.", className="text-secondary mb-0")
    blocks = []
    today = date.today()
    for block in calendar_rows:
        exp = block.get("expiration_date") or ""
        dte = block.get("days_to_expiration")
        header_cls = "text-success"
        if dte is not None:
            if dte < 0:
                header_cls = "text-secondary"
            elif dte <= 7:
                header_cls = "text-warning"
            elif dte <= 14:
                header_cls = "text-info"
        dte_label = "Expired" if dte is not None and dte < 0 else f"{dte} DTE" if dte is not None else ""
        items = []
        for row in block.get("items") or []:
            warn = row.get("assignment_warning")
            badge = (
                dbc.Badge(
                    row.get("assignment_reason") or "Watch",
                    color="danger",
                    className="ms-2",
                )
                if warn
                else None
            )
            items.append(
                html.Li(
                    [
                        html.Strong(f"{row.get('ticker')} "),
                        html.Span(
                            f"${row.get('strike', 0):.2f} × {row.get('contracts', 0)} ",
                            className="privacy-sensitive-text",
                        ),
                        html.Span(
                            f"({row.get('moneyness_label', '')})",
                            className="privacy-sensitive-text",
                        ),
                        badge,
                    ],
                    className="mb-1",
                )
            )
        blocks.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(exp, className="fw-semibold me-2"),
                            html.Small(dte_label, className=header_cls),
                        ],
                        className="mb-2",
                    ),
                    html.Ul(items, className="mb-3 ps-3"),
                ],
                className="cc-calendar-day border-bottom border-secondary pb-2 mb-2",
            )
        )
    return html.Div(blocks)


layout = html.Div(
    [
        dcc.Store(id="cc-store", data=0),
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
                                html.I(className="bi bi-currency-exchange stocks-hero-icon"),
                                html.Div(
                                    [
                                        html.H2("Covered Calls", className="stocks-hero-title"),
                                        html.P(
                                            "Coverable lots by account, open positions, and expiration calendar.",
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
                dbc.Card(
                    [
                        dbc.CardBody(
                            [
                                html.Div(
                                    [
                                        html.Div("Coverable holdings", className="neon-title"),
                                        html.Div(
                                            "100+ share positions per brokerage account",
                                            className="neon-subtitle",
                                        ),
                                    ],
                                    className="neon-card-header",
                                ),
                                dash_table.DataTable(
                                    id="cc-coverable-table",
                                    columns=[
                                        {"name": "Brokerage", "id": "brokerage"},
                                        {"name": "Account", "id": "account"},
                                        {"name": "Ticker", "id": "ticker"},
                                        {
                                            "name": "Shares",
                                            "id": "shares",
                                            "type": "numeric",
                                            "format": Format(precision=0, scheme=Scheme.fixed),
                                        },
                                        {"name": "Coverable lots", "id": "coverable_lots", "type": "numeric"},
                                        {"name": "Uncovered", "id": "uncovered_shares", "type": "numeric"},
                                        {
                                            "name": "Price",
                                            "id": "latest_price",
                                            "type": "numeric",
                                            "format": _money,
                                        },
                                    ],
                                    data=[],
                                    style_table={"overflowX": "auto"},
                                    style_header={
                                        "backgroundColor": "#0f172a",
                                        "fontWeight": "bold",
                                        "color": "#d1fae5",
                                        "borderBottom": "1px solid rgba(16, 185, 129, 0.35)",
                                    },
                                    style_data={"backgroundColor": "#11181f", "color": "#e5e7eb"},
                                    page_size=12,
                                    sort_action="native",
                                    filter_action="native",
                                ),
                            ]
                        )
                    ],
                    className="mb-4 neon-panel neon-green privacy-sensitive-visual",
                ),
                xs=12,
                lg=10,
                className="mx-auto",
            )
        ),
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.Div(
                                        [
                                            html.Div("Add covered call", className="neon-title"),
                                            html.Div(
                                                "Log an outstanding short call position",
                                                className="neon-subtitle",
                                            ),
                                        ],
                                        className="neon-card-header",
                                    ),
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                dcc.Input(
                                                    id="cc-ticker-input",
                                                    type="text",
                                                    placeholder="Ticker",
                                                    className="form-control mb-2",
                                                ),
                                                width=2,
                                            ),
                                            dbc.Col(
                                                dcc.Input(
                                                    id="cc-strike-input",
                                                    type="number",
                                                    placeholder="Strike",
                                                    min=0,
                                                    step=0.01,
                                                    className="form-control mb-2",
                                                ),
                                                width=2,
                                            ),
                                            dbc.Col(
                                                dcc.DatePickerSingle(
                                                    id="cc-expiration-input",
                                                    placeholder="Expiration",
                                                    className="mb-2",
                                                ),
                                                width=3,
                                            ),
                                            dbc.Col(
                                                dcc.Input(
                                                    id="cc-contracts-input",
                                                    type="number",
                                                    placeholder="Contracts",
                                                    min=1,
                                                    step=1,
                                                    value=1,
                                                    className="form-control mb-2",
                                                ),
                                                width=2,
                                            ),
                                            dbc.Col(
                                                dcc.Input(
                                                    id="cc-premium-input",
                                                    type="number",
                                                    placeholder="Premium ($)",
                                                    min=0,
                                                    step=0.01,
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
                                                    id="cc-open-date-input",
                                                    placeholder="Open date (optional)",
                                                    className="mb-2",
                                                ),
                                                width=3,
                                            ),
                                            dbc.Col(
                                                dcc.Input(
                                                    id="cc-notes-input",
                                                    type="text",
                                                    placeholder="Notes (optional)",
                                                    className="form-control mb-2",
                                                ),
                                                width=6,
                                            ),
                                            dbc.Col(
                                                dbc.Button(
                                                    [html.I(className="bi bi-plus-lg me-1"), "Add"],
                                                    id="cc-add-button",
                                                    color="success",
                                                    className="w-100 mb-2 neon-action-btn",
                                                ),
                                                width=3,
                                            ),
                                        ],
                                        className="align-items-end",
                                    ),
                                    dbc.Alert(id="cc-form-output", color="success", is_open=False),
                                ]
                            )
                        ],
                        className="mb-4 neon-panel neon-green",
                    ),
                    xs=12,
                    lg=10,
                    className="mx-auto",
                )
            ],
            id="cc-manual-form-section",
        ),
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.Div(
                                        [
                                            html.Div("Open covered calls", className="neon-title"),
                                            html.Div(
                                                "Live metrics use latest stored stock prices",
                                                className="neon-subtitle",
                                            ),
                                        ],
                                        className="neon-card-header",
                                    ),
                                    dash_table.DataTable(
                                        id="cc-open-table",
                                        columns=[
                                            {"name": "Ticker", "id": "ticker"},
                                            {
                                                "name": "Strike",
                                                "id": "strike",
                                                "type": "numeric",
                                                "format": _money,
                                            },
                                            {"name": "Expiration", "id": "expiration_date"},
                                            {"name": "Contracts", "id": "contracts", "type": "numeric"},
                                            {
                                                "name": "Premium received",
                                                "id": "premium_received",
                                                "type": "numeric",
                                                "format": _money,
                                            },
                                            {"name": "Open", "id": "open_date"},
                                            {
                                                "name": "Price",
                                                "id": "current_price",
                                                "type": "numeric",
                                                "format": _money,
                                            },
                                            {"name": "Moneyness", "id": "moneyness_label"},
                                            {"name": "DTE", "id": "days_to_expiration", "type": "numeric"},
                                            {"name": "Shares at risk", "id": "shares_at_risk", "type": "numeric"},
                                            {
                                                "name": "Prem %",
                                                "id": "premium_yield_pct",
                                                "type": "numeric",
                                                "format": _pct,
                                            },
                                            {"name": "Assignment", "id": "assignment_reason"},
                                        ],
                                        data=[],
                                        row_selectable="single",
                                        selected_rows=[],
                                        style_table={"overflowX": "auto"},
                                        style_header={
                                            "backgroundColor": "#0f172a",
                                            "fontWeight": "bold",
                                            "color": "#d1fae5",
                                            "borderBottom": "1px solid rgba(16, 185, 129, 0.35)",
                                        },
                                        style_data={"backgroundColor": "#11181f", "color": "#e5e7eb"},
                                        style_data_conditional=[
                                            {
                                                "if": {"filter_query": '{assignment_reason} != ""'},
                                                "backgroundColor": "rgba(239, 68, 68, 0.18)",
                                            },
                                            {
                                                "if": {"state": "selected"},
                                                "backgroundColor": "#1e293b",
                                                "color": "#ffffff",
                                            },
                                        ],
                                        hidden_columns=["id", "assignment_warning"],
                                        page_size=10,
                                        sort_action="native",
                                    ),
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                dbc.Button(
                                                    "Delete selected",
                                                    id="cc-delete-button",
                                                    color="danger",
                                                    className="mt-2",
                                                ),
                                                width="auto",
                                            ),
                                        ],
                                        id="cc-manual-delete-section",
                                    ),
                                    dbc.Alert(id="cc-delete-feedback", color="warning", is_open=False, className="mt-2"),
                                ]
                            )
                        ],
                        className="mb-4 neon-panel neon-green privacy-sensitive-visual",
                    ),
                    xs=12,
                    lg=7,
                    className="mx-auto",
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.Div(
                                        [
                                            html.Div("Expiration calendar", className="neon-title"),
                                            html.Div(
                                                "Grouped by expiry (open positions only)",
                                                className="neon-subtitle",
                                            ),
                                        ],
                                        className="neon-card-header",
                                    ),
                                    html.Div(id="cc-calendar", className="cc-calendar-panel"),
                                ]
                            )
                        ],
                        className="mb-4 neon-panel neon-green privacy-sensitive-visual",
                    ),
                    xs=12,
                    lg=3,
                    className="mx-auto",
                ),
            ],
            className="g-3",
        ),
    ],
    className="stocks-page-shell px-3 px-md-4 py-3",
)


@dash_app.callback(
    Output("cc-manual-form-section", "style"),
    Output("cc-manual-delete-section", "style"),
    Output("cc-open-table", "row_selectable"),
    Input("interval-component", "n_intervals"),
    Input("cc-store", "data"),
)
def cc_sync_manual_entry_visibility(_n, _store):
    if db_manager.get_hide_manual_entry():
        hidden = {"display": "none"}
        return hidden, hidden, False
    return {}, {}, "single"


@dash_app.callback(
    Output("cc-coverable-table", "data"),
    Input("cc-store", "data"),
    Input("interval-component", "n_intervals"),
)
def load_coverable_holdings(_store, _n):
    return cc_api.get_coverable_holdings_records()


@dash_app.callback(
    Output("cc-open-table", "data"),
    Output("cc-calendar", "children"),
    Input("cc-store", "data"),
    Input("interval-component", "n_intervals"),
)
def load_open_calls(_store, _n):
    rows = cc_api.get_open_covered_calls_enriched()
    for row in rows:
        if not row.get("assignment_warning"):
            row["assignment_reason"] = ""
    return rows, _calendar_children(cc_api.build_expiration_calendar(rows))


@dash_app.callback(
    Output("cc-form-output", "children"),
    Output("cc-form-output", "is_open"),
    Output("cc-form-output", "color"),
    Output("cc-store", "data", allow_duplicate=True),
    Input("cc-add-button", "n_clicks"),
    State("cc-ticker-input", "value"),
    State("cc-strike-input", "value"),
    State("cc-expiration-input", "date"),
    State("cc-contracts-input", "value"),
    State("cc-premium-input", "value"),
    State("cc-open-date-input", "date"),
    State("cc-notes-input", "value"),
    State("cc-store", "data"),
    prevent_initial_call=True,
)
def add_covered_call(
    n_clicks,
    ticker,
    strike,
    expiration,
    contracts,
    premium,
    open_date,
    notes,
    store_data,
):
    if not n_clicks:
        raise PreventUpdate
    if db_manager.get_hide_manual_entry():
        return "Manual entry is disabled. Use Import CSV.", True, "warning", no_update
    if not ticker or strike is None or not expiration:
        return "Enter ticker, strike, and expiration.", True, "warning", no_update
    try:
        strike_val = float(strike)
        if strike_val <= 0:
            raise ValueError("strike")
    except (TypeError, ValueError):
        return "Strike must be a positive number.", True, "warning", no_update
    contract_count = int(contracts or 1)
    if contract_count < 1:
        return "Contracts must be at least 1.", True, "warning", no_update
    try:
        db_manager.insert_covered_call(
            ticker=ticker,
            strike=strike_val,
            expiration_date=expiration,
            contracts=contract_count,
            premium_received=float(premium or 0),
            open_date=open_date,
            notes=(notes or "").strip() or None,
        )
        return f"Added covered call for {ticker.upper().strip()}.", True, "success", (store_data or 0) + 1
    except Exception as exc:
        return f"Error: {exc}", True, "danger", no_update


@dash_app.callback(
    Output("cc-delete-feedback", "children"),
    Output("cc-delete-feedback", "is_open"),
    Output("cc-delete-feedback", "color"),
    Output("cc-store", "data", allow_duplicate=True),
    Output("cc-open-table", "selected_rows"),
    Input("cc-delete-button", "n_clicks"),
    State("cc-open-table", "selected_rows"),
    State("cc-open-table", "data"),
    State("cc-store", "data"),
    prevent_initial_call=True,
)
def delete_covered_call(n_clicks, selected_rows, table_data, store_data):
    if not n_clicks:
        raise PreventUpdate
    if db_manager.get_hide_manual_entry():
        return "Manual delete is disabled. Use Import CSV.", True, "warning", no_update, []
    if not selected_rows:
        return "Select a row to delete.", True, "warning", no_update, []
    idx = selected_rows[0]
    if not table_data or idx >= len(table_data):
        return "Invalid selection.", True, "warning", no_update, []
    row_id = table_data[idx].get("id")
    if row_id is None:
        return "Could not delete row.", True, "danger", no_update, []
    try:
        db_manager.delete_covered_call(row_id)
        return "Deleted covered call.", True, "success", (store_data or 0) + 1, []
    except Exception as exc:
        return f"Error: {exc}", True, "danger", no_update, selected_rows
