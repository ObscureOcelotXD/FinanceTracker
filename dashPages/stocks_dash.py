# pages/stocks_dash.py
import dash
from dash import html, dcc, Input, Output, State, get_app
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
from services import db_manager
from api import finnhub_api

# Register page
dash.register_page(__name__, path="/stocks_dash", name="Display")

dash_app = get_app()

# One auto-fetch per process when holdings lack quotes (avoids interval hammering).
_missing_price_fetch_attempted = False


def _ensure_missing_prices_fetched():
    """If any held ticker has no price yet, fetch quotes once this process."""
    global _missing_price_fetch_attempted
    if _missing_price_fetch_attempted:
        return
    _missing_price_fetch_attempted = True
    try:
        missing = db_manager.get_tickers_missing_prices()
        if not missing:
            return
        print(f"[Dashboard] Auto-fetching prices for {len(missing)} ticker(s) without quotes.")
        finnhub_api.update_stock_prices(forceUpdate=False)
    except Exception as exc:
        print(f"[Dashboard] Auto price fetch failed: {exc}")

def _normalize_price_df(df):
    if df.empty:
        return df
    df = df.copy()
    df["closing_price"] = pd.to_numeric(df["closing_price"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"])
    return df

def _merge_monthly_first_trading_day(df):
    if df.empty:
        return df
    df = df.sort_values("date").copy()
    df["month_key"] = df["date"].dt.to_period("M")
    merged = (
        df.groupby(["ticker", "month_key"], as_index=False)
        .first()
        .drop(columns=["month_key"])
    )
    return merged

def _value_chart(df, chart_type):
    if df.empty:
        return px.bar(title="No Data Available", template="plotly_dark")
    chart_df = df[df["position_value"].fillna(0) > 0].copy()
    if chart_df.empty:
        return px.bar(title="No priced holdings yet — try Refresh Prices", template="plotly_dark")
    if chart_type == "treemap":
        fig = px.treemap(
            chart_df,
            path=["ticker"],
            values="position_value",
            title="Your Stock Values (Treemap)",
        )
    else:
        fig = px.bar(
            chart_df,
            x="ticker",
            y="position_value",
            title="Your Stock Values",
            labels={"position_value": "Value"},
        )
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20), template="plotly_dark")
    return fig

def _allocation_chart(df, chart_type):
    if df.empty:
        return px.pie(title="No Data Available", template="plotly_dark")
    chart_df = df[df["position_value"].fillna(0) > 0].copy()
    if chart_df.empty:
        return px.pie(title="No priced holdings yet — try Refresh Prices", template="plotly_dark")
    hole = 0.5 if chart_type == "donut" else 0
    fig = px.pie(
        chart_df,
        names="ticker",
        values="position_value",
        title="Allocation",
        hole=hole,
    )
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20), template="plotly_dark")
    return fig

def _historical_chart(df, tickers, chart_type, start_date, end_date):
    if df.empty:
        return px.line(title="No Data Available", template="plotly_dark")
    df = _merge_monthly_first_trading_day(_normalize_price_df(df))
    if tickers:
        df = df[df["ticker"].isin(tickers)]
    if start_date:
        df = df[df["date"] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df["date"] <= pd.to_datetime(end_date)]
    if df.empty:
        return px.line(title="No Data Available", template="plotly_dark")
    fig = px.area(
        df,
        x="date",
        y="closing_price",
        color="ticker",
        title="Historical Prices",
        labels={"closing_price": "Price", "date": "Date"},
    ) if chart_type == "area" else px.line(
        df,
        x="date",
        y="closing_price",
        color="ticker",
        markers=True,
        title="Historical Prices",
        labels={"closing_price": "Price", "date": "Date"},
    )
    y_min = df["closing_price"].min()
    y_max = df["closing_price"].max()
    if pd.notna(y_min) and pd.notna(y_max) and y_min != y_max:
        pad = (y_max - y_min) * 0.05
        y_range = [y_min - pad, y_max + pad]
    else:
        y_range = None
    fig.update_traces(line={"width": 2})
    fig.update_layout(
        margin=dict(l=20, r=20, t=50, b=20),
        template="plotly_dark",
        height=620,
        legend_title_text="",
    )
    if y_range:
        fig.update_yaxes(range=y_range)
    return fig

# Combined callback to update value bar and pie charts
@dash_app.callback(
    Output("stocks-value-chart", "figure"),
    Output("stocks-allocation-chart", "figure"),
    Input('interval-component', 'n_intervals'),
    Input("stocks-store-display", "data"),
    Input("value-chart-type", "value"),
    Input("allocation-chart-type", "value"),
)
def update_value_graphs(n_intervals, store_data, value_chart_type, allocation_chart_type):
    from api import security_type as st

    _ensure_missing_prices_fetched()
    df = st.filter_holdings_df_for_ui(db_manager.get_value_stocks())
    return _value_chart(df, value_chart_type), _allocation_chart(df, allocation_chart_type)

@dash_app.callback(
    Output("stocks-sector-chart", "figure"),
    Input("interval-component", "n_intervals"),
    Input("stocks-store-display", "data"),
)
def update_sector_chart(n_intervals, store_data):
    from api import security_type as st

    df = st.filter_holdings_df_for_ui(db_manager.get_value_stocks())
    if df.empty:
        return px.pie(title="No Data Available", template="plotly_dark")
    chart_df = df[df["position_value"].fillna(0) > 0].copy()
    if chart_df.empty:
        return px.pie(title="No priced holdings yet — try Refresh Prices", template="plotly_dark")
    tickers = chart_df["ticker"].tolist()
    sector_map = finnhub_api.get_sector_allocation_map(tickers)
    chart_df["sector"] = chart_df["ticker"].map(sector_map).fillna("Unknown")
    sector_df = chart_df.groupby("sector", as_index=False)["position_value"].sum()
    ticker_df = chart_df.groupby("sector")["ticker"].apply(lambda x: ", ".join(sorted(set(x)))).reset_index()
    sector_df = sector_df.merge(ticker_df, on="sector", how="left")
    fig = px.pie(
        sector_df,
        names="sector",
        values="position_value",
        title="Industry Allocation",
    )
    fig.update_traces(
        customdata=sector_df["ticker"],
        hovertemplate="<b>%{label}</b><br>Value: %{value:$,.2f}<br>Tickers: %{customdata}<extra></extra>",
        textfont_size=13,
    )
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20), template="plotly_dark")
    return fig


@dash_app.callback(
    Output("total-net-worth-banner", "children"),
    Input("interval-component", "n_intervals"),
    Input("stocks-store-display", "data"),
)
def update_total_net_worth(n_intervals, store_data):
    from api import security_type as st

    df = st.filter_holdings_df_for_ui(db_manager.get_value_stocks())
    total_value = df["position_value"].sum() if not df.empty else 0
    return html.Span(
        [
            html.Span("Total stock value: "),
            html.Span(f"${total_value:,.2f}", className="privacy-sensitive-text"),
        ]
    )

# 2. Add a new callback (or extend existing one) that reacts to the button
@dash_app.callback(
    Output("stocks-store-display", "data", allow_duplicate=True),
    Output("force-update-alert", "children"),
    Output("force-update-alert", "is_open"),
    Output("force-update-alert", "color"),
    Output("force-update-btn", "children"),
    Output("force-update-btn", "disabled"),
    Output("force-update-timer", "disabled"),
    Output("force-update-loading-target", "children"),
    Input("force-update-btn", "n_clicks"),
    State("stocks-store-display", "data"),
    prevent_initial_call=True,
)
def force_update_table(n_clicks, current_counter):
    print(f"Callback triggered! n_clicks: {n_clicks}, current_counter: {current_counter}")
    if n_clicks is None:
        return False, "", False, "info", "Refresh Prices", False, True, ""
    # Call the update function with forceUpdate=True
    try:
        from api.finnhub_api import update_stock_prices
        update_stock_prices(forceUpdate=True)
        tickers_df = db_manager.get_value_stocks()
        tickers = tickers_df["ticker"].tolist() if not tickers_df.empty else []
        print(f"[Sector] Force refresh tickers: {tickers}")
        if tickers:
            sector_map = finnhub_api.get_sector_allocation_map(tickers, force_refresh=True)
            print(f"[Sector] Force refresh complete. Count={len(sector_map)}")
        # Just increment the counter → this will trigger your existing load_stocks_table callback
        return (current_counter or 0) + 1, "Prices updated.", True, "success", "Refresh Prices", False, False, ""
    except Exception as exc:
        return dash.no_update, f"Update failed: {exc}", True, "danger", "Refresh Prices", False, False, ""
    
    
# Page layout
_price_df = db_manager.get_stock_prices_df()
_price_df = _normalize_price_df(_price_df)
_min_date = _price_df["date"].min() if not _price_df.empty else None
_max_date = _price_df["date"].max() if not _price_df.empty else None
_min_date_str = _min_date.date().isoformat() if _min_date is not None else None
_max_date_str = _max_date.date().isoformat() if _max_date is not None else None
_ticker_options = (
    [{"label": t, "value": t} for t in sorted(_price_df["ticker"].unique())]
    if not _price_df.empty
    else []
)

layout = html.Div(
    [
        html.Div(id="force-update-loading-target"),
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
                                html.I(className="bi bi-graph-up-arrow stocks-hero-icon"),
                                html.Div(
                                    [
                                        html.H2(
                                            "Stocks Dashboard",
                                            className="stocks-hero-title",
                                        ),
                                        html.P(
                                            "Portfolio value, allocation, sector mix, and price history.",
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
            [
                dbc.Col(
                    html.Div(
                        id="total-net-worth-banner",
                        className="stocks-net-worth-tile text-center mb-3",
                        children=html.Span(
                            [
                                html.Span("Total stock value: "),
                                html.Span("$0.00", className="privacy-sensitive-text"),
                            ]
                        ),
                    ),
                    width=12,
                )
            ],
        ),
        dbc.Row(
            [
                dbc.Col(
                    dbc.Button(
                        [html.I(className="bi bi-arrow-repeat me-2"), "Refresh Prices"],
                        id="force-update-btn",
                        color="success",
                        className="mt-1 mb-2 neon-action-btn",
                    ),
                    width="auto",
                )
            ],
            justify="center",
        ),
        dcc.Interval(id="force-update-timer", interval=4000, n_intervals=0, disabled=True),
        dbc.Row(
            [
                dbc.Col(
                    dbc.Alert(
                        id="force-update-alert",
                        is_open=False,
                        dismissable=True,
                        className="mt-2",
                    ),
                    width="auto",
                )
            ],
            justify="center",
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
                                            html.Div(
                                                [
                                                    html.Div("Value Charts", className="neon-title"),
                                                    html.Div("Portfolio value and allocation", className="neon-subtitle"),
                                                ]
                                            ),
                                        ],
                                        className="neon-card-header",
                                    ),
                                    dbc.Row(
                                        dbc.Col(
                                            html.Div(
                                                dbc.Row(
                                                    [
                                                        dbc.Col(
                                                            [
                                                                html.Label(
                                                                    "Value chart type",
                                                                    className="small mb-1 stocks-filter-label",
                                                                ),
                                                                dbc.Select(
                                                                    id="value-chart-type",
                                                                    options=[
                                                                        {"label": "Bar", "value": "bar"},
                                                                        {"label": "Treemap", "value": "treemap"},
                                                                    ],
                                                                    value="bar",
                                                                    className="stocks-filter-select",
                                                                ),
                                                            ],
                                                            md=6,
                                                        ),
                                                        dbc.Col(
                                                            [
                                                                html.Label(
                                                                    "Allocation chart type",
                                                                    className="small mb-1 stocks-filter-label",
                                                                ),
                                                                dbc.Select(
                                                                    id="allocation-chart-type",
                                                                    options=[
                                                                        {"label": "Pie", "value": "pie"},
                                                                        {"label": "Donut", "value": "donut"},
                                                                    ],
                                                                    value="pie",
                                                                    className="stocks-filter-select",
                                                                ),
                                                            ],
                                                            md=6,
                                                        ),
                                                    ],
                                                    className="g-3",
                                                ),
                                                className="stocks-filter-panel mb-3",
                                            ),
                                            width=12,
                                        ),
                                    ),
                                    dbc.Row(
                                        [
                                            dbc.Col(dcc.Graph(id="stocks-value-chart"), md=6),
                                            dbc.Col(dcc.Graph(id="stocks-allocation-chart"), md=6),
                                        ]
                                    ),
                                    dbc.Row(
                                        [
                                            dbc.Col(dcc.Graph(id="stocks-sector-chart"), md=12),
                                        ],
                                        className="mt-3",
                                    ),
                                ]
                            ),
                        ],
                        className="mb-4 neon-panel neon-green privacy-sensitive-visual",
                    ),
                    width=12,
                )
            ]
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
                                            html.Div(
                                                [
                                                    html.Div("Historical Prices", className="neon-title"),
                                                    html.Div("Filter and compare performance", className="neon-subtitle"),
                                                ]
                                            ),
                                        ],
                                        className="neon-card-header",
                                    ),
                                    html.Div(
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        html.Label("Tickers", className="small mb-1 stocks-filter-label"),
                                                        dbc.Checklist(
                                                            id="historical-tickers",
                                                            options=_ticker_options,
                                                            value=[o["value"] for o in _ticker_options],
                                                            inline=True,
                                                            className="display-stocks-ticker-checklist",
                                                            input_class_name="display-stocks-ticker-check-input",
                                                            label_class_name="display-stocks-ticker-check-label me-3",
                                                        ),
                                                        html.Small(
                                                            "Toggle symbols to include in the chart.",
                                                            className="stocks-filter-hint mt-2 d-block",
                                                        ),
                                                    ],
                                                    md=5,
                                                ),
                                                dbc.Col(
                                                    [
                                                        html.Label("Chart type", className="small mb-1 stocks-filter-label"),
                                                        dbc.Select(
                                                            id="historical-chart-type",
                                                            options=[
                                                                {"label": "Line", "value": "line"},
                                                                {"label": "Area", "value": "area"},
                                                            ],
                                                            value="line",
                                                            className="stocks-filter-select",
                                                        ),
                                                    ],
                                                    md=3,
                                                ),
                                                dbc.Col(
                                                    [
                                                        html.Label("Date range", className="small mb-1 stocks-filter-label"),
                                                        html.Div(
                                                            [
                                                                dbc.Input(
                                                                    id="stocks-start-date",
                                                                    type="date",
                                                                    value=_min_date_str,
                                                                    min=_min_date_str,
                                                                    max=_max_date_str,
                                                                    className="stocks-filter-text",
                                                                ),
                                                                dbc.Input(
                                                                    id="stocks-end-date",
                                                                    type="date",
                                                                    value=_max_date_str,
                                                                    min=_min_date_str,
                                                                    max=_max_date_str,
                                                                    className="stocks-filter-text",
                                                                ),
                                                            ],
                                                            className="display-stocks-date-wrap",
                                                        ),
                                                    ],
                                                    md=4,
                                                ),
                                            ],
                                            className="g-3 align-items-end",
                                        ),
                                        className="stocks-filter-panel mb-3",
                                    ),
                                    dcc.Graph(
                                        id="stocks-historical-chart",
                                        style={"height": "540px"},
                                        config={"displayModeBar": False},
                                    ),
                                ]
                            ),
                        ],
                        className="mb-4 neon-panel neon-green privacy-sensitive-visual",
                    ),
                    width=12,
                )
            ]
        ),
        dcc.Store(id="stocks-store-display"),
    ],
    className="stocks-page-shell container-fluid px-3 px-md-4 pt-3",
)


@dash_app.callback(
    Output("stocks-historical-chart", "figure"),
    Input("interval-component", "n_intervals"),
    Input("stocks-store-display", "data"),
    Input("historical-tickers", "value"),
    Input("historical-chart-type", "value"),
    Input("stocks-start-date", "value"),
    Input("stocks-end-date", "value"),
)
def update_historical_chart(n_intervals, store_data, tickers, chart_type, start_date, end_date):
    from api import security_type as st

    df = db_manager.get_stock_prices_df()
    if not df.empty:
        allowed = set(st.filter_tickers_for_ui(df["ticker"].astype(str).unique().tolist()))
        df = df[df["ticker"].isin(allowed)]
        if tickers:
            tickers = [t for t in tickers if t in allowed]
    return _historical_chart(df, tickers, chart_type, start_date, end_date)


@dash_app.callback(
    Output("force-update-alert", "is_open", allow_duplicate=True),
    Output("force-update-timer", "disabled", allow_duplicate=True),
    Input("force-update-timer", "n_intervals"),
    State("force-update-alert", "is_open"),
    prevent_initial_call=True,
)
def auto_hide_force_update_alert(n_intervals, is_open):
    if not is_open:
        return False, True
    return False, True

