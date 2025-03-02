# dashapp.py
from dash import Dash, html, dcc
import dash_bootstrap_components as dbc
from runServer import flask_app  # Import the Flask app instance

# Initialize the Dash app using the Flask server
dash_app = Dash(
    __name__,
    server=flask_app,
    url_base_pathname='/dashboard/',
    # routes_pathname_prefix='/dashboard/',
    # requests_pathname_prefix='/dashboard/',
    external_stylesheets=[dbc.themes.BOOTSTRAP]
)

# Define a minimal layout for the Dash app
dash_app.layout = html.Div([
    html.H1("Finance Dashboard"),
    dcc.Graph(id='sample-graph'),  # The graph will be updated via callbacks
    dcc.Graph(id='pie-chart'),
    dcc.Graph(id='line-graph'),   
    dcc.Interval(id='interval-component', interval=60*1000, n_intervals=0)
])
