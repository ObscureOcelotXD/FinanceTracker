import plotly.express as px
from dash import Input, Output
import db_manager
from dashApp import dash_app  # Import the dash_app instance from dashapp.py

@dash_app.callback(
    Output('sample-graph', 'figure'),
    [Input('interval-component', 'n_intervals')]
)
def update_graph(n_intervals):
    print("Callback triggered with n_intervals:", n_intervals)
    df = db_manager.get_account_balances()
    if df.empty:
        # Return an empty figure if no data is available
        return px.bar(title="No Data Available")
    # Create a bar chart using Plotly Express
    fig = px.bar(df, x='account_id', y='current_balance',
                 title="Account Balances",
                 labels={'account_id': 'Account ID', 'current_balance': 'Balance'})
    return fig
