# pages/stocks_dash.py
import dash
from dash import html, dcc, callback, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
import db_manager

# Register page
dash.register_page(__name__, path="/stocks_dash", name="Display")

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
    if chart_type == "treemap":
        fig = px.treemap(
            df,
            path=["ticker"],
            values="position_value",
            title="Your Stock Values (Treemap)",
        )
    else:
        fig = px.bar(
            df,
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
    hole = 0.5 if chart_type == "donut" else 0
    fig = px.pie(
        df,
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
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20), template="plotly_dark")
    return fig

# Combined callback to update value bar and pie charts
@callback(
    Output("stocks-value-chart", "figure"),
    Output("stocks-allocation-chart", "figure"),
    Input('interval-component', 'n_intervals'),
    Input("stocks-store-display", "data"),
    Input("value-chart-type", "value"),
    Input("allocation-chart-type", "value"),
)
def update_value_graphs(n_intervals, store_data, value_chart_type, allocation_chart_type):
    df = db_manager.get_value_stocks()
    return _value_chart(df, value_chart_type), _allocation_chart(df, allocation_chart_type)

# 2. Add a new callback (or extend existing one) that reacts to the button
@dash.callback(
    Output("stocks-store-display", "data", allow_duplicate=True),
    Input("force-update-btn", "n_clicks"),
    State("stocks-store-display", "data"),
    prevent_initial_call=True,
)
def force_update_table(n_clicks, current_counter):
    print(f"Callback triggered! n_clicks: {n_clicks}, current_counter: {current_counter}")
    if n_clicks is None:
        return False
    # Call the update function with forceUpdate=True
    from api.finnhub_api import update_stock_prices
    update_stock_prices(forceUpdate=True)
    # Just increment the counter → this will trigger your existing load_stocks_table callback
    return (current_counter or 0) + 1
    
    
# Page layout
_price_df = db_manager.get_stock_prices_df()
_price_df = _normalize_price_df(_price_df)
_min_date = _price_df["date"].min() if not _price_df.empty else None
_max_date = _price_df["date"].max() if not _price_df.empty else None
_ticker_options = (
    [{"label": t, "value": t} for t in sorted(_price_df["ticker"].unique())]
    if not _price_df.empty
    else []
)

layout = html.Div(
    [
        html.H1(
            "Stocks Dashboard",
            style={
                "textAlign": "center",
                "marginBottom": "20px",
                "fontFamily": "Arial, sans-serif",
            },
        ),
        dbc.Row(
            [
                dbc.Col(
                    dbc.Button(
                        "Force Update Table",
                        id="force-update-btn",
                        color="info",
                        className="mt-3",
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
                            dbc.CardHeader("Value Charts"),
                            dbc.CardBody(
                                [
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                [
                                                    html.Label("Value chart type"),
                                                    dcc.Dropdown(
                                                        id="value-chart-type",
                                                        options=[
                                                            {"label": "Bar", "value": "bar"},
                                                            {"label": "Treemap", "value": "treemap"},
                                                        ],
                                                        value="bar",
                                                        clearable=False,
                                                        className="chart-dropdown",
                                                    ),
                                                ],
                                                md=6,
                                            ),
                                            dbc.Col(
                                                [
                                                    html.Label("Allocation chart type"),
                                                    dcc.Dropdown(
                                                        id="allocation-chart-type",
                                                        options=[
                                                            {"label": "Pie", "value": "pie"},
                                                            {"label": "Donut", "value": "donut"},
                                                        ],
                                                        value="pie",
                                                        clearable=False,
                                                        className="chart-dropdown",
                                                    ),
                                                ],
                                                md=6,
                                            ),
                                        ],
                                        className="mb-3",
                                    ),
                                    dbc.Row(
                                        [
                                            dbc.Col(dcc.Graph(id="stocks-value-chart"), md=6),
                                            dbc.Col(dcc.Graph(id="stocks-allocation-chart"), md=6),
                                        ]
                                    ),
                                ]
                            ),
                        ],
                        className="mb-4",
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
                            dbc.CardHeader("Historical Prices"),
                            dbc.CardBody(
                                [
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                [
                                                    html.Label("Tickers"),
                                                    dcc.Dropdown(
                                                        id="historical-tickers",
                                                        options=_ticker_options,
                                                        value=[o["value"] for o in _ticker_options],
                                                        multi=True,
                                                        className="chart-dropdown",
                                                    ),
                                                ],
                                                md=6,
                                            ),
                                            dbc.Col(
                                                [
                                                    html.Label("Chart type"),
                                                    dcc.Dropdown(
                                                        id="historical-chart-type",
                                                        options=[
                                                            {"label": "Line", "value": "line"},
                                                            {"label": "Area", "value": "area"},
                                                        ],
                                                        value="line",
                                                        clearable=False,
                                                        className="chart-dropdown",
                                                    ),
                                                ],
                                                md=3,
                                            ),
                                            dbc.Col(
                                                [
                                                    html.Label("Date range"),
                                                    dcc.DatePickerRange(
                                                        id="stocks-date-range",
                                                        min_date_allowed=_min_date,
                                                        max_date_allowed=_max_date,
                                                        start_date=_min_date,
                                                        end_date=_max_date,
                                                        display_format="MMM D, YYYY",
                                                    ),
                                                ],
                                                md=3,
                                            ),
                                        ],
                                        className="mb-3",
                                    ),
                                    dcc.Graph(id="stocks-historical-chart"),
                                ]
                            ),
                        ],
                        className="mb-4",
                    ),
                    width=12,
                )
            ]
        ),
        dcc.Store(id="stocks-store-display"),
    ],
    style={"paddingTop": "50px"},
)


@callback(
    Output("stocks-historical-chart", "figure"),
    Input("interval-component", "n_intervals"),
    Input("stocks-store-display", "data"),
    Input("historical-tickers", "value"),
    Input("historical-chart-type", "value"),
    Input("stocks-date-range", "start_date"),
    Input("stocks-date-range", "end_date"),
)
def update_historical_chart(n_intervals, store_data, tickers, chart_type, start_date, end_date):
    df = db_manager.get_stock_prices_df()
    return _historical_chart(df, tickers, chart_type, start_date, end_date)


