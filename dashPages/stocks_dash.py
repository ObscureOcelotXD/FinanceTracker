# pages/stocks_dash.py
import dash
from dash import html, dcc, callback, Input, Output
import plotly.express as px
import pandas as pd
import db_manager

# Register page
dash.register_page(__name__, path="/stocks_dash", name="Display")

def create_historical_graphs(df):
    graphs = []
    for i, ticker in enumerate(sorted(df['ticker'].unique())):
        dff = df[df['ticker'] == ticker].sort_values('date').copy()

        print(f"\n=== Filtered for {ticker} ===")
        print(dff[['date','closing_price']].to_string(index=False))
        
        dff['closing_price'] = pd.to_numeric(dff['closing_price'], errors='coerce')
        dff['date'] = pd.to_datetime(dff['date'])

        fig = px.line(
            dff,
            x='date',
            y='closing_price',
            markers=True,
            title=f"Historical prices for {ticker}",
            labels={'closing_price': 'Price', 'date': 'Date'}
        ) 

        tick_vals = dff['date'].tolist()
        tick_text = [d.strftime('%b %d, %Y') for d in tick_vals]

        fig.update_xaxes(
            tickmode='array',
            tickvals=tick_vals,
            ticktext=tick_text
        )

        fig.update_layout(margin=dict(l=20, r=20, t=50, b=20))
        graphs.append(dcc.Graph(id=f"hist-chart-{ticker}", figure=fig))
    return graphs

# Page layout
layout = html.Div([
    html.H1("Stocks Dashboard", style={
        'textAlign': 'center', 'marginBottom': '20px', 'fontFamily': 'Arial, sans-serif'
    }),
    # Value charts (initially empty, to be filled by callback)
    html.Div([
        dcc.Graph(id='stocks-value-bar-chart'),
        dcc.Graph(id='stocks-value-pie-chart'),
    ], style={
        'display': 'flex', 'flexWrap': 'wrap', 'justifyContent': 'space-around',
        'padding': '20px'
    }),
    # Historical ticker charts
    html.Div(
        create_historical_graphs(db_manager.get_value_stocks()),
        style={'display': 'flex', 'flexWrap': 'wrap', 'justifyContent': 'space-around'}
    ),
    # Interval and Store for live updates
    dcc.Interval(id='interval-component', interval=60 * 1000, n_intervals=0),
    dcc.Store(id='stocks-store')
], style={'paddingTop': '50px', 'backgroundColor': '#f9f9f9'})

# Combined callback to update value bar and pie charts
@callback(
    Output('stocks-value-bar-chart', 'figure'),
    Output('stocks-value-pie-chart', 'figure'),
    Input('interval-component', 'n_intervals'),
    Input('stocks-store', 'data')
)
def update_value_graphs(n_intervals, store_data):
    df = db_manager.get_value_stocks()
    if df.empty:
        return px.bar(title="No Data Available"), px.pie(title="No Data Available")

    fig_bar = px.bar(df, x='ticker', y='position_value',
                     title="Your Stock Values",
                     labels={'position_value': 'Value'})
    fig_bar.update_layout(margin=dict(l=20, r=20, t=50, b=20))

    fig_pie = px.pie(df, names='ticker', values='position_value',
                     title="Your Stock Values (Pie Chart)")
    fig_pie.update_layout(margin=dict(l=20, r=20, t=50, b=20))

    return fig_bar, fig_pie
