# dashapp.py
import dash
from dash import Dash, html, dcc
import dash_bootstrap_components as dbc
from runServer import flask_app  # Import the Flask app instance


# Initialize the Dash app using the Flask server
dash_app = Dash(
    __name__,
    server=flask_app,
    url_base_pathname='/dashboard/',
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True,
    use_pages=True, 
    pages_folder='dashPages'
)

# Update the layout to use container cards for each graph
dash_app.layout = html.Div([
    dcc.Location(id="url", refresh=False),
    dbc.NavbarSimple(
    children=[
        dbc.NavLink("Display", href=" /dashboard/stocks_dash", active="exact"),
        dbc.NavLink("Manage Stocks", href="/dashboard/stocks_manage", active="exact")
    ],
    brand="Stocks App",
    color="primary",
    dark=True,
    ),
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
    
    dcc.Interval(id='interval-component', interval=60*1000, n_intervals=0),
    dcc.Store(id="stocks-store", data=0),
    html.Div(id="dummy-output-delete", style={"display": "none"}),
    # This container renders the layout of the current page.
    dash.page_container
])

import dashPages.stocks_dash as stocksDash
import dashPages.stocks_manage as stocksManage