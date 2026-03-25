import dash
from dash import html, dcc, ctx
from dash.dash_table import DataTable, FormatTemplate
import dash_bootstrap_components as dbc
import db_manager
from dash.dependencies import Output, Input, State
from dash.exceptions import PreventUpdate

dash.register_page(
    __name__,
    path="/stocks_manage",
    name="Manage Stocks",
    layout=dbc.Container(
        [
            dcc.Store(id="stocks-store", data=0),
            dcc.Store(id="stocks-filter-state", data={}),
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
                                    html.I(className="bi bi-sliders2-vertical stocks-hero-icon"),
                                    html.Div(
                                        [
                                            html.H2(
                                                "Manage Stocks",
                                                className="stocks-hero-title",
                                            ),
                                            html.P(
                                                "Edit positions in the table, add rows, or delete with the row trash icon.",
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
                                color="success",
                                className="px-4",
                            ),
                            dbc.Button(
                                "Realized",
                                href="/dashboard/stocks_realized",
                                color="secondary",
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
                                                    html.Div("Positions", className="neon-title"),
                                                    html.Div(
                                                        "All changes save when you leave a cell or delete a row.",
                                                        className="neon-subtitle small",
                                                    ),
                                                ]
                                            ),
                                        ],
                                        className="neon-card-header",
                                    ),
                                    html.Div(
                                        id="stocks-summary-bar",
                                        className="stocks-summary-inline mb-3",
                                        children="",
                                    ),
                                    dbc.Row(
                                        dbc.Col(
                                            dbc.Button(
                                                [
                                                    html.I(className="bi bi-plus-lg me-1"),
                                                    "Add row",
                                                ],
                                                id="stocks-add-row",
                                                color="success",
                                                className="neon-action-btn mb-2",
                                                size="sm",
                                            ),
                                            width="auto",
                                        ),
                                    ),
                                    html.Div(
                                        [
                                            dbc.Row(
                                                [
                                                    dbc.Col(
                                                        [
                                                            html.Span(
                                                                [
                                                                    html.I(className="bi bi-funnel me-2"),
                                                                    "Filter rows (all optional)",
                                                                ],
                                                                className="small fw-semibold text-light",
                                                            ),
                                                            html.Div(
                                                                "Set options below, then click Apply filters.",
                                                                className="stocks-filter-hint mt-1",
                                                            ),
                                                        ],
                                                        xs=12,
                                                        md=True,
                                                        className="pe-md-2",
                                                    ),
                                                    dbc.Col(
                                                        dbc.ButtonGroup(
                                                            [
                                                                dbc.Button(
                                                                    [
                                                                        html.I(className="bi bi-check2 me-1"),
                                                                        "Apply filters",
                                                                    ],
                                                                    id="stocks-filter-apply",
                                                                    color="success",
                                                                    size="sm",
                                                                    className="stocks-filter-apply-btn",
                                                                ),
                                                                dbc.Button(
                                                                    [
                                                                        html.I(className="bi bi-x-lg me-1"),
                                                                        "Clear all",
                                                                    ],
                                                                    id="stocks-filter-clear",
                                                                    color="secondary",
                                                                    outline=True,
                                                                    size="sm",
                                                                    className="stocks-filter-clear-btn",
                                                                ),
                                                            ],
                                                            className="stocks-filter-actions",
                                                        ),
                                                        xs=12,
                                                        md="auto",
                                                        className="text-md-end mt-2 mt-md-0 ps-0",
                                                    ),
                                                ],
                                                className="align-items-start mb-3",
                                            ),
                                            dbc.Row(
                                                [
                                                    dbc.Col(
                                                        [
                                                            dbc.Label(
                                                                "Ticker contains",
                                                                className="small mb-1 stocks-filter-label",
                                                            ),
                                                            dcc.Input(
                                                                id="stocks-filter-ticker",
                                                                type="text",
                                                                placeholder="e.g. NVDA or MS",
                                                                debounce=True,
                                                                className="form-control form-control-sm stocks-filter-text",
                                                            ),
                                                        ],
                                                        xs=12,
                                                        md=5,
                                                        lg=4,
                                                    ),
                                                    dbc.Col(
                                                        [
                                                            dbc.Label(
                                                                "And this number column is…",
                                                                className="small mb-1 stocks-filter-label",
                                                            ),
                                                            dbc.InputGroup(
                                                                [
                                                                    dbc.Select(
                                                                        id="stocks-filter-num-col",
                                                                        options=[
                                                                            {
                                                                                "label": "— choose column —",
                                                                                "value": "",
                                                                            },
                                                                            {
                                                                                "label": "Shares",
                                                                                "value": "shares",
                                                                            },
                                                                            {
                                                                                "label": "Cost basis ($)",
                                                                                "value": "cost_basis",
                                                                            },
                                                                            {
                                                                                "label": "Position value ($)",
                                                                                "value": "position_value",
                                                                            },
                                                                            {
                                                                                "label": "Gain / loss ($)",
                                                                                "value": "gain_loss",
                                                                            },
                                                                            {
                                                                                "label": "% gain (decimal)",
                                                                                "value": "gain_loss_pct",
                                                                            },
                                                                        ],
                                                                        value="",
                                                                        className="stocks-filter-select",
                                                                    ),
                                                                    dbc.Select(
                                                                        id="stocks-filter-num-op",
                                                                        options=[
                                                                            {
                                                                                "label": "≥ at least",
                                                                                "value": ">=",
                                                                            },
                                                                            {
                                                                                "label": "≤ at most",
                                                                                "value": "<=",
                                                                            },
                                                                        ],
                                                                        value=">=",
                                                                        className="stocks-filter-select stocks-filter-op-select",
                                                                    ),
                                                                    dcc.Input(
                                                                        id="stocks-filter-num-val",
                                                                        type="number",
                                                                        placeholder="Value",
                                                                        debounce=True,
                                                                        className="form-control form-control-sm stocks-filter-text stocks-filter-num-input",
                                                                    ),
                                                                ],
                                                                size="sm",
                                                                className="stocks-filter-inputgroup flex-wrap flex-md-nowrap",
                                                            ),
                                                            html.Small(
                                                                "% gain uses decimals (0.10 = 10%). Other $ columns use dollars.",
                                                                className="d-block mt-2 stocks-filter-hint",
                                                            ),
                                                        ],
                                                        xs=12,
                                                        md=7,
                                                        lg=8,
                                                    ),
                                                ],
                                                className="g-3",
                                            ),
                                        ],
                                        className="stocks-filter-panel mb-3",
                                    ),
                                    html.Button(
                                        id="clear-active-cell-btn",
                                        style={"display": "none"},
                                    ),
                                    html.Div(
                                        DataTable(
                                            id="stocks-table",
                                            editable=True,
                                            cell_selectable=True,
                                            row_deletable=True,
                                            row_selectable=False,
                                            columns=[
                                                {
                                                    "name": "Ticker",
                                                    "id": "ticker",
                                                    "hideable": False,
                                                },
                                                {
                                                    "name": "Shares",
                                                    "id": "shares",
                                                    "type": "numeric",
                                                    "editable": True,
                                                    "hideable": False,
                                                },
                                                {
                                                    "name": "Cost Basis",
                                                    "id": "cost_basis",
                                                    "type": "numeric",
                                                    "format": FormatTemplate.money(2),
                                                    "editable": True,
                                                    "hideable": False,
                                                },
                                                {
                                                    "name": "Position Value",
                                                    "id": "position_value",
                                                    "type": "numeric",
                                                    "format": FormatTemplate.money(2),
                                                    "editable": False,
                                                    "hideable": False,
                                                },
                                                {
                                                    "name": "Gain/Loss",
                                                    "id": "gain_loss",
                                                    "type": "numeric",
                                                    "format": FormatTemplate.money(2),
                                                    "editable": False,
                                                    "hideable": False,
                                                },
                                                {
                                                    "name": "% Gain",
                                                    "id": "gain_loss_pct",
                                                    "type": "numeric",
                                                    "format": FormatTemplate.percentage(2),
                                                    "editable": False,
                                                    "hideable": False,
                                                },
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
                                            ],
                                            sort_action="native",
                                            page_size=15,
                                        ),
                                        className="privacy-sensitive-visual",
                                    ),
                                    dbc.Alert(
                                        id="stocks-table-feedback",
                                        color="danger",
                                        is_open=False,
                                        dismissable=True,
                                        className="mt-2 mb-0",
                                    ),
                                    dbc.Toast(
                                        "Saved",
                                        id="edit-save-toast",
                                        header="Updated",
                                        is_open=False,
                                        duration=2000,
                                        dismissable=True,
                                        icon="success",
                                        className="mt-2",
                                    ),
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
                                                    html.Div("Plaid Holdings", className="neon-title"),
                                                    html.Div(
                                                        "Imported positions by institution",
                                                        className="neon-subtitle",
                                                    ),
                                                ]
                                            ),
                                        ],
                                        className="neon-card-header",
                                    ),
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                dcc.Dropdown(
                                                    id="institution-filter",
                                                    options=[],
                                                    value="All",
                                                    placeholder="Filter by institution...",
                                                    className="chart-dropdown",
                                                ),
                                                width=6,
                                            )
                                        ],
                                        className="mb-3",
                                    ),
                                    html.Div(
                                        DataTable(
                                            id="plaid-holdings-table",
                                            row_deletable=False,
                                            row_selectable=False,
                                            columns=[
                                                {
                                                    "name": "Institution",
                                                    "id": "institution_name",
                                                    "hideable": False,
                                                },
                                                {
                                                    "name": "Account",
                                                    "id": "account_name",
                                                    "hideable": False,
                                                },
                                                {"name": "Ticker", "id": "ticker", "hideable": False},
                                                {
                                                    "name": "Shares",
                                                    "id": "shares",
                                                    "type": "numeric",
                                                    "hideable": False,
                                                },
                                                {
                                                    "name": "Cost Basis",
                                                    "id": "cost_basis",
                                                    "type": "numeric",
                                                    "format": FormatTemplate.money(2),
                                                    "hideable": False,
                                                },
                                                {
                                                    "name": "Position Value",
                                                    "id": "position_value",
                                                    "type": "numeric",
                                                    "format": FormatTemplate.money(2),
                                                    "hideable": False,
                                                },
                                                {
                                                    "name": "Gain/Loss",
                                                    "id": "gain_loss",
                                                    "type": "numeric",
                                                    "format": FormatTemplate.money(2),
                                                    "hideable": False,
                                                },
                                                {
                                                    "name": "% Gain",
                                                    "id": "gain_loss_pct",
                                                    "type": "numeric",
                                                    "format": FormatTemplate.percentage(2),
                                                    "hideable": False,
                                                },
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
                                            ],
                                            filter_action="none",
                                            sort_action="native",
                                            page_size=10,
                                        ),
                                        className="privacy-sensitive-visual",
                                    ),
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
        ],
        fluid=True,
        className="stocks-page-shell px-3 px-md-4 py-3",
    ),
)


def _parse_row_id(row):
    rid = row.get("id")
    if rid is None or rid == "":
        return None
    try:
        return int(rid)
    except (TypeError, ValueError):
        return None


def _norm_cost_basis(val):
    if val is None or val == "":
        return None
    return float(val)


@dash.callback(
    Output("stocks-table", "data", allow_duplicate=True),
    Input("stocks-add-row", "n_clicks"),
    State("stocks-table", "data"),
    prevent_initial_call=True,
)
def add_draft_row(n_clicks, data):
    if not n_clicks:
        raise PreventUpdate
    draft = {
        "id": None,
        "ticker": "",
        "shares": None,
        "cost_basis": None,
        "position_value": None,
        "gain_loss": None,
        "gain_loss_pct": None,
    }
    return [draft] + list(data or [])


@dash.callback(
    Output("stocks-store", "data", allow_duplicate=True),
    Output("stocks-table-feedback", "children"),
    Output("stocks-table-feedback", "is_open"),
    Output("stocks-table-feedback", "color"),
    Output("edit-save-toast", "is_open", allow_duplicate=True),
    Input("stocks-table", "data_timestamp"),
    State("stocks-table", "data_previous"),
    State("stocks-table", "data"),
    State("stocks-store", "data"),
    prevent_initial_call=True,
)
def sync_stocks_from_table(_ts, prev, current, store_data):
    if prev is None or current is None:
        raise PreventUpdate

    prev_by_id = {}
    for r in prev:
        rid = _parse_row_id(r)
        if rid is not None:
            prev_by_id[rid] = r

    curr_by_id = {}
    curr_drafts = []
    for r in current:
        rid = _parse_row_id(r)
        if rid is None:
            curr_drafts.append(r)
        else:
            curr_by_id[rid] = r

    deleted_ids = set(prev_by_id.keys()) - set(curr_by_id.keys())
    for sid in deleted_ids:
        db_manager.delete_stock(sid)

    errors = []
    inserted = 0
    for dr in curr_drafts:
        t = (dr.get("ticker") or "").strip().upper()
        sh = dr.get("shares")
        if not t and (sh is None or sh == ""):
            continue
        if not t or sh is None or sh == "":
            continue
        try:
            sh_val = float(sh)
            if sh_val < 0:
                errors.append("Shares cannot be negative.")
                continue
            cb = _norm_cost_basis(dr.get("cost_basis"))
            db_manager.insert_stock(t, sh_val, cost_basis=cb)
            inserted += 1
        except Exception as exc:
            errors.append(str(exc))

    if errors:
        return (
            dash.no_update,
            errors[0],
            True,
            "danger",
            False,
        )

    updated = 0
    for rid, new_row in curr_by_id.items():
        if rid not in prev_by_id:
            continue
        old = prev_by_id[rid]
        nt = (new_row.get("ticker") or "").strip().upper()
        if not nt:
            return (
                dash.no_update,
                "Ticker cannot be empty.",
                True,
                "danger",
                False,
            )
        try:
            ns = float(new_row.get("shares"))
            if ns < 0:
                return (
                    dash.no_update,
                    "Shares cannot be negative.",
                    True,
                    "danger",
                    False,
                )
        except (TypeError, ValueError):
            return (
                dash.no_update,
                "Enter a valid number for shares.",
                True,
                "danger",
                False,
            )
        ncb = _norm_cost_basis(new_row.get("cost_basis"))
        ot = (old.get("ticker") or "").strip().upper()
        try:
            os_ = float(old.get("shares"))
        except (TypeError, ValueError):
            os_ = None
        ocb = _norm_cost_basis(old.get("cost_basis"))
        if nt != ot or ns != os_ or ncb != ocb:
            db_manager.update_stock(rid, ticker=nt, shares=ns, cost_basis=ncb)
            updated += 1

    if deleted_ids or inserted or updated:
        return (store_data or 0) + 1, "", False, "success", True
    raise PreventUpdate


def apply_filter_to_df(df, filter_state):
    """Filter a stocks DataFrame using criteria from the filter store."""
    if not filter_state or df.empty:
        return df
    ticker = (filter_state.get("ticker") or "").strip()
    if ticker:
        mask = df["ticker"].str.contains(ticker, case=False, na=False)
        df = df[mask]
    col = (filter_state.get("col") or "").strip()
    op = filter_state.get("op")
    val = filter_state.get("val")
    if col and col in df.columns and op in (">=", "<=") and val is not None:
        try:
            v = float(val)
            if op == ">=":
                df = df[df[col].astype(float) >= v]
            else:
                df = df[df[col].astype(float) <= v]
        except (TypeError, ValueError):
            pass
    return df


@dash.callback(
    Output("stocks-filter-state", "data"),
    Output("stocks-filter-ticker", "value", allow_duplicate=True),
    Output("stocks-filter-num-col", "value", allow_duplicate=True),
    Output("stocks-filter-num-op", "value", allow_duplicate=True),
    Output("stocks-filter-num-val", "value", allow_duplicate=True),
    Input("stocks-filter-apply", "n_clicks"),
    Input("stocks-filter-clear", "n_clicks"),
    State("stocks-filter-ticker", "value"),
    State("stocks-filter-num-col", "value"),
    State("stocks-filter-num-op", "value"),
    State("stocks-filter-num-val", "value"),
    prevent_initial_call=True,
)
def apply_or_clear_filters(apply_n, clear_n, ticker_sub, num_col, num_op, num_val):
    trigger = ctx.triggered_id
    if trigger == "stocks-filter-clear":
        return {}, "", "", ">=", None
    if trigger == "stocks-filter-apply":
        state = {}
        t = (ticker_sub or "").strip()
        if t:
            state["ticker"] = t
        col = (num_col or "").strip()
        if col and num_op in (">=", "<=") and num_val is not None and str(num_val).strip():
            try:
                state["col"] = col
                state["op"] = num_op
                state["val"] = float(num_val)
            except (TypeError, ValueError):
                pass
        return state, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    raise PreventUpdate


@dash.callback(
    Output("stocks-table", "active_cell"),
    Output("stocks-table", "selected_cells"),
    Output("stocks-table", "selected_rows"),
    Input("clear-active-cell-btn", "n_clicks"),
    prevent_initial_call=True,
)
def clear_active_cell(n_clicks):
    return None, [], dash.no_update


@dash.callback(
    Output("stocks-table", "data", allow_duplicate=True),
    Input("stocks-store", "modified_timestamp"),
    Input("stocks-filter-state", "data"),
    State("stocks-store", "data"),
    prevent_initial_call="initial_duplicate",
)
def load_stocks_table(_ts, filter_state, _store_data):
    df = db_manager.get_stocks()
    if df.empty:
        return []
    df = apply_filter_to_df(df, filter_state)
    return df.to_dict("records")


@dash.callback(
    Output("stocks-summary-bar", "children"),
    Input("stocks-store", "modified_timestamp"),
    State("stocks-store", "data"),
)
def update_positions_summary(_ts, _store_data):
    df = db_manager.get_stocks()
    if df.empty:
        return html.Span(
            "No positions yet — use Add row to create one.",
            className="text-secondary",
        )
    total_v = float(df["position_value"].sum())
    total_cb = float(df["cost_basis"].sum())
    gl = float(df["gain_loss"].sum())
    gl_pct = (gl / total_cb) if total_cb else None
    pct_txt = f"{gl_pct * 100:.2f}%" if gl_pct is not None else "—"
    return html.Div(
        [
            html.Span("Total value: ", className="text-secondary me-1"),
            html.Span(f"${total_v:,.2f}", className="privacy-sensitive-text fw-bold text-light me-3"),
            html.Span("Cost basis: ", className="text-secondary me-1"),
            html.Span(f"${total_cb:,.2f}", className="privacy-sensitive-text me-3"),
            html.Span("Gain / loss: ", className="text-secondary me-1"),
            html.Span(
                f"${gl:,.2f} ({pct_txt})",
                className="privacy-sensitive-text fw-bold",
                style={"color": "#22c55e" if gl >= 0 else "#f87171"},
            ),
        ],
        className="d-flex flex-wrap align-items-baseline gap-1",
    )


@dash.callback(
    Output("plaid-holdings-table", "data"),
    Output("institution-filter", "options"),
    [
        Input("stocks-store", "modified_timestamp"),
        Input("institution-filter", "value"),
    ],
)
def load_plaid_holdings(ts, institution_value):
    institutions = db_manager.get_institutions()
    options = [{"label": "All", "value": "All"}] + [
        {"label": name, "value": name} for name in institutions
    ]
    selected = None if institution_value in (None, "All") else institution_value
    df = db_manager.get_plaid_holdings(selected)
    if df.empty:
        return [], options
    totals = {
        "institution_name": "All",
        "account_name": "TOTAL",
        "ticker": "TOTAL",
        "shares": df["shares"].sum(),
        "cost_basis": df["cost_basis"].sum(),
        "position_value": df["position_value"].sum(),
        "gain_loss": df["gain_loss"].sum(),
    }
    if totals["cost_basis"]:
        totals["gain_loss_pct"] = totals["gain_loss"] / totals["cost_basis"]
    return df.to_dict("records") + [totals], options
