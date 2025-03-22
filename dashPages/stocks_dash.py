import dash
from dash import html, dcc
import plotly.express as px
import db_manager

# Register this page. When the user visits /stocks_dash the following layout will be shown.
dash.register_page(
    __name__,
    path="/stocks_dash",
    name="Display",
    layout=html.Div([
        html.H1("Stocks Dashboard", style={'textAlign': 'center', 'marginBottom': '20px'}),
        html.Div([
            dcc.Graph(id='stocks-chart')
        ], className="card", style={'padding': '20px', 'margin': 'auto', 'maxWidth': '600px'}),
    ])
)

# Callback for updating the chart.
@dash.callback(
    dash.dependencies.Output('stocks-chart', 'figure'),
    [dash.dependencies.Input('interval-component', 'n_intervals'),
     dash.dependencies.Input('stocks-store', 'data')]
)
def update_stocks_chart(n_intervals, store_data):
    df = db_manager.get_stocks()  # Expect a DataFrame with columns: id, ticker, shares
    if df.empty:
        return px.bar(title="No Data Available")
    fig = px.bar(df, x='ticker', y='shares', title="Your Stocks",
                 labels={'ticker': 'Ticker', 'shares': 'Shares'})
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20))
    return fig
