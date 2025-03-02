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
    df_sorted = df.sort_values(by='current_balance', ascending=True)
    if df.empty:
        # Return an empty figure if no data is available
        return px.bar(title="No Data Available")
    # Create a bar chart using Plotly Express
    fig = px.bar(df_sorted, x='account_id', y='current_balance',
                 title="Account Balances",
                 labels={'account_id': 'Account ID', 'current_balance': 'Balance'})
    return fig



@dash_app.callback(
    Output('pie-chart', 'figure'),
    [Input('interval-component', 'n_intervals')]
)
def update_pie_chart(n_intervals):
    df = db_manager.get_all_records_df()
    if df.empty:
        # Return an empty pie chart if no data is available
        return px.pie(title="No Data Available")
    
    # Create a pie chart with account_id as categories and current_balance as values
    fig = px.pie(
        df,
        names='source_name',
        values='source_value',
        title="Balance Distribution by Account"
    )
    return fig


@dash_app.callback(
    Output('line-graph', 'figure'),
    [Input('interval-component', 'n_intervals')]
)
def update_line_graph(n_intervals):
    df = db_manager.get_all_records_df()  # Replace this with your actual data query
    if df.empty:
        # Return an empty figure with a message if no data is available
        return px.line(title="No Data Available")
    
    # Create a line graph using Plotly Express.
    # Each unique source_name gets its own line.
    fig = px.line(
        df,
        x='date_created',
        y='source_value',
        color='source_name',
        title="Source Values Over Time",
        labels={
            'source_name': 'Source Name',
            'source_value': 'Value',
            'date_created': 'Date'
        }
    )
    return fig