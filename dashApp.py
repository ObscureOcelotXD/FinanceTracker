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

# Update the layout to use container cards for each graph
dash_app.layout = html.Div([
    html.H1("Finance Dashboard", style={"textAlign": "center", "marginBottom": "20px"}),
    
    # Container for the two side-by-side graphs (bar and pie charts)
    html.Div([
        html.Div(
            dcc.Graph(id='sample-graph'),
            className="card",
            style={"display": "inline-block", "verticalAlign": "top", "width": "45%", "margin": "10px"}
        ),
        html.Div(
            dcc.Graph(id='pie-chart'),
            className="card",
            style={"display": "inline-block", "verticalAlign": "top", "width": "45%", "margin": "10px"}
        )
    ], style={"textAlign": "center"}),
    
    # Full-width container for the line graph
    html.Div(
        dcc.Graph(id='line-graph'),
        className="card",
        style={"width": "90%", "margin": "20px auto"}
    ),
    
    dcc.Interval(id='interval-component', interval=60*1000, n_intervals=0)
])

