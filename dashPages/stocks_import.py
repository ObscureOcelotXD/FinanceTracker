# stocks_import.py — single portfolio CSV upload / download
import dash
from dash import Input, Output, State, dcc, html, no_update
import dash_bootstrap_components as dbc

from api import portfolio_import as pi
from api import portfolio_sync as ps

dash.register_page(
    __name__,
    path="/stocks_import",
    name="Import CSV",
)

dash_app = dash.get_app()

_sync_status = ps.status()
_sync_configured = _sync_status["configured"]

layout = html.Div(
    [
        dcc.Store(id="import-refresh-store", data=0),
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
                                html.I(className="bi bi-upload stocks-hero-icon"),
                                html.Div(
                                    [
                                        html.H2("Import portfolio", className="stocks-hero-title"),
                                        html.P(
                                            "One portfolio CSV is the source of truth for holdings and covered calls. "
                                            "Download, edit, upload — each upload replaces both datasets.",
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
                dbc.Alert(
                    [
                        html.Strong("Tip: "),
                        "Wipe All Data from Home → Admin if you want a clean slate first. "
                        "Otherwise download your current file, edit premiums/shares, then upload. "
                        "Optional: sync to Umbrel Files (Home → Documents → Portfolio; see docs/PORTFOLIO_SYNC.md).",
                    ],
                    color="info",
                    className="mb-3",
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
                                        html.Div("Portfolio CSV", className="neon-title"),
                                        html.Div(
                                            "One download file · one upload file",
                                            className="neon-subtitle",
                                        ),
                                    ],
                                    className="neon-card-header",
                                ),
                                html.A(
                                    dbc.Button(
                                        [
                                            html.I(className="bi bi-download me-2"),
                                            "Download portfolio CSV",
                                        ],
                                        color="info",
                                        outline=True,
                                        className="w-100 mb-3",
                                    ),
                                    href="/api/export/portfolio.csv",
                                ),
                                html.Ul(
                                    [
                                        html.Li(
                                            [
                                                html.Strong("Columns: "),
                                                "type (stock|call), brokerage, account, ticker, shares, ",
                                                "cost_basis/premium, strike, expiration_date, contracts, ",
                                                "open_date, status, notes.",
                                            ]
                                        ),
                                        html.Li(
                                            "cost_basis/premium = stock cost basis, or cash premium on call rows."
                                        ),
                                        html.Li("Upload replaces all holdings and covered calls."),
                                    ],
                                    className="text-secondary mb-3 small",
                                ),
                                dcc.Upload(
                                    id="import-auto-upload",
                                    children=html.Div(
                                        [
                                            "Drag & drop or ",
                                            html.A("select portfolio CSV"),
                                        ]
                                    ),
                                    className="cc-upload-box mb-2",
                                    multiple=False,
                                    accept=".csv,.xlsx,.xls",
                                ),
                                dbc.Alert(id="import-auto-result", is_open=False, className="mb-0"),
                            ]
                        )
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
                                        html.Div("Umbrel / Tailscale sync", className="neon-title"),
                                        html.Div(
                                            "Writes to Umbrel Files: Home → Documents → Portfolio",
                                            className="neon-subtitle",
                                        ),
                                    ],
                                    className="neon-card-header",
                                ),
                                html.Div(id="import-sync-status", className="text-secondary small mb-3"),
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            dbc.Button(
                                                [
                                                    html.I(className="bi bi-cloud-upload me-2"),
                                                    "Push to Umbrel",
                                                ],
                                                id="import-sync-push",
                                                color="success",
                                                outline=True,
                                                className="w-100 mb-2",
                                                disabled=not _sync_configured,
                                            ),
                                            md=6,
                                        ),
                                        dbc.Col(
                                            dbc.Button(
                                                [
                                                    html.I(className="bi bi-cloud-download me-2"),
                                                    "Pull from Umbrel",
                                                ],
                                                id="import-sync-pull",
                                                color="info",
                                                outline=True,
                                                className="w-100 mb-2",
                                                disabled=not _sync_configured,
                                            ),
                                            md=6,
                                        ),
                                    ]
                                ),
                                dbc.Alert(id="import-sync-result", is_open=False, className="mb-0"),
                            ]
                        )
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
                html.Div(
                    [
                        dbc.Button(
                            [html.I(className="bi bi-table me-2"), "Manage Stocks"],
                            href="/dashboard/stocks_manage",
                            color="secondary",
                            outline=True,
                            className="me-2 mb-2",
                        ),
                        dbc.Button(
                            [html.I(className="bi bi-currency-exchange me-2"), "Covered Calls"],
                            href="/dashboard/stocks_covered_calls",
                            color="secondary",
                            outline=True,
                            className="mb-2",
                        ),
                    ],
                    className="text-center",
                ),
                width=12,
            )
        ),
    ],
    className="stocks-page-shell px-3 px-md-4 py-3",
)


def _format_auto_result(result: dict) -> tuple:
    if not result:
        return no_update, False, no_update
    if result.get("errors"):
        return html.Div([html.Div(e) for e in result["errors"][:8]]), True, "danger"

    parts = []
    color = "success"
    h = result.get("holdings")
    c = result.get("covered_calls")
    if h:
        if h.get("ok"):
            parts.append(f"Holdings: imported {h.get('count', 0)} row(s) (replaced previous holdings).")
        else:
            color = "danger"
            parts.append("Holdings errors: " + "; ".join((h.get("errors") or [])[:5]))
    if c:
        if c.get("ok"):
            parts.append(
                f"Covered calls: imported {c.get('count', 0)} row(s) (replaced previous covered calls)."
            )
        else:
            color = "danger"
            parts.append("Covered call errors: " + "; ".join((c.get("errors") or [])[:5]))
    if result.get("note"):
        parts.append(result["note"])
    if result.get("message"):
        parts.insert(0, result["message"])
    if not parts:
        return "Nothing imported.", True, "warning"
    return html.Div([html.Div(p) for p in parts]), True, color


@dash_app.callback(
    Output("import-sync-status", "children"),
    Input("import-refresh-store", "data"),
)
def show_sync_status(_n):
    st = ps.status()
    if not st["configured"]:
        return (
            "Not configured. Set UMBREL_TAILSCALE_IP and UMBREL_PASSWORD "
            "(then look in Umbrel Files → Home → Documents → Portfolio)."
        )
    return st["message"]


@dash_app.callback(
    Output("import-sync-result", "children"),
    Output("import-sync-result", "is_open"),
    Output("import-sync-result", "color"),
    Output("import-refresh-store", "data"),
    Input("import-sync-push", "n_clicks"),
    Input("import-sync-pull", "n_clicks"),
    State("import-refresh-store", "data"),
    prevent_initial_call=True,
)
def on_sync_click(push_clicks, pull_clicks, refresh):
    triggered = dash.ctx.triggered_id
    next_refresh = (refresh or 0) + 1
    try:
        if triggered == "import-sync-push":
            result = ps.push_portfolio_csv()
            return result.get("message", "Pushed."), True, "success", next_refresh
        if triggered == "import-sync-pull":
            result = ps.pull_portfolio_csv()
            children, opened, color = _format_auto_result(result)
            return children, opened, color, next_refresh
        raise dash.exceptions.PreventUpdate
    except Exception as exc:
        return str(exc), True, "danger", refresh or 0


@dash_app.callback(
    Output("import-auto-result", "children"),
    Output("import-auto-result", "is_open"),
    Output("import-auto-result", "color"),
    Input("import-auto-upload", "contents"),
    State("import-auto-upload", "filename"),
    prevent_initial_call=True,
)
def on_auto_upload(contents, filename):
    if not contents:
        raise dash.exceptions.PreventUpdate
    try:
        result = pi.apply_auto_upload(contents, filename or "upload.csv")
    except Exception as exc:
        return str(exc), True, "danger"
    return _format_auto_result(result)
