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
    external_stylesheets=[dbc.themes.DARKLY],
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
    color="dark",
    dark=True,
    ),
    dcc.Interval(id='interval-component', interval=60*1000, n_intervals=0),
    dcc.Store(id="stocks-store", data=0),
    html.Div(id="dummy-output-delete", style={"display": "none"}),
    # This container renders the layout of the current page.
    dash.page_container
])

import dashPages.accounts_dash as accountsDash
import dashPages.stocks_dash as stocksDash
import dashPages.stocks_manage as stocksManage