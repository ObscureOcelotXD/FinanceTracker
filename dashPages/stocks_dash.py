import dash
from dash import html, dcc
import plotly.express as px
import db_manager

# Register this page. When the user visits /stocks_dash the following layout will be shown.
dash.register_page(
    __name__,
    path="/stocks_dash",
    name="Display",
    layout=html.Div(
        children=[
            html.H1(
                "Stocks Dashboard",
                style={
                    'textAlign': 'center',
                    'marginBottom': '20px',
                    'fontFamily': 'Arial, sans-serif'
                }
            ),
            # Responsive container for all three graphs in a row
            html.Div(
                children=[
                    html.Div(
                        children=[dcc.Graph(id='stocks-chart')],
                        style={
                            'padding': '20px',
                            'margin': '10px',
                            'flex': '1 1 0',
                            'minWidth': '300px',
                            'boxShadow': '0 4px 8px 0 rgba(0,0,0,0.2)',
                            'borderRadius': '8px',
                            'backgroundColor': '#fff'
                        }
                    ),
                    html.Div(
                        children=[dcc.Graph(id='stocks-value-bar-chart')],
                        style={
                            'padding': '20px',
                            'margin': '10px',
                            'flex': '1 1 0',
                            'minWidth': '300px',
                            'boxShadow': '0 4px 8px 0 rgba(0,0,0,0.2)',
                            'borderRadius': '8px',
                            'backgroundColor': '#fff'
                        }
                    ),
                    html.Div(
                        children=[dcc.Graph(id='stocks-value-pie-chart')],
                        style={
                            'padding': '20px',
                            'margin': '10px',
                            'flex': '1 1 0',
                            'minWidth': '300px',
                            'boxShadow': '0 4px 8px 0 rgba(0,0,0,0.2)',
                            'borderRadius': '8px',
                            'backgroundColor': '#fff'
                        }
                    )
                ],
                style={
                    'display': 'flex',
                    'flexDirection': 'row',
                    'flexWrap': 'wrap',  # Allows wrapping for smaller screens
                    'justifyContent': 'space-around',
                    'padding': '20px',
                    'margin': 'auto',
                    'width': '100%'
                }
            ),
            # Extra div to provide additional scrolling space at the bottom
            html.Div(style={'height': '100px'})
        ],
        style={
            'paddingTop': '50px',    
            'paddingBottom': '100px',
            'backgroundColor': '#f9f9f9'
        }
    )
)

# Combined callback for all charts.
@dash.callback(
    dash.dependencies.Output('stocks-chart', 'figure'),
    dash.dependencies.Output('stocks-value-bar-chart', 'figure'),
    dash.dependencies.Output('stocks-value-pie-chart', 'figure'),
    [dash.dependencies.Input('interval-component', 'n_intervals'),
     dash.dependencies.Input('stocks-store', 'data')]
)
def update_all_charts(n_intervals, store_data):
    # First chart: Stocks bar chart
    df_stocks = db_manager.get_stocks()  # Expect a DataFrame with columns: id, ticker, shares
    if df_stocks.empty:
        fig_stocks = px.bar(title="No Data Available")
    else:
        fig_stocks = px.bar(
            df_stocks,
            x='ticker',
            y='shares',
            title="Your Stocks",
            labels={'ticker': 'Ticker', 'shares': 'Shares'}
        )
        fig_stocks.update_layout(margin=dict(l=20, r=20, t=50, b=20))
    
    # Second charts: Stock values bar and pie charts
    df_values = db_manager.get_value_stocks()  # Expect a DataFrame with columns: id, ticker, position_value, etc.
    if df_values.empty:
        fig_value_bar = px.bar(title="No Data Available")
        fig_value_pie = px.pie(title="No Data Available")
    else:
        fig_value_bar = px.bar(
            df_values,
            x='ticker',
            y='position_value',
            title="Your Stock Values",
            labels={'ticker': 'Ticker', 'position_value': 'Value'}
        )
        fig_value_bar.update_layout(margin=dict(l=20, r=20, t=50, b=20))
        
        fig_value_pie = px.pie(
            df_values,
            names='ticker',
            values='position_value',
            title="Your Stock Values (Pie Chart)"
        )
        fig_value_pie.update_layout(margin=dict(l=20, r=20, t=50, b=20))
    
    return fig_stocks, fig_value_bar, fig_value_pie
