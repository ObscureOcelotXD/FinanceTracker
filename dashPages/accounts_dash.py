import dash
from dash import html, dcc
import plotly.express as px
import db_manager

# Register this page. When the user visits /accounts_dash the following layout will be shown.
dash.register_page(
    __name__,
    path="/accounts_dash",
    name="Accounts",
    layout=html.Div(
        children=[
            html.H1(
                "Accounts Dashboard",
                style={
                    'textAlign': 'center',
                    'marginBottom': '20px',
                    'fontFamily': 'Arial, sans-serif'
                }
            ),
            # Container for the two side-by-side graphs (bar and pie charts)
            html.Div(
                children=[
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
                ],
                style={"textAlign": "center"}
            ),
            # Full-width container for the line graph
            html.Div(
                children=[
                    dcc.Graph(id='line-graph')
                ],
                className="card",
                style={"width": "90%", "margin": "20px auto"}
            )
        ],
        style={
            'paddingTop': '50px',    
            'paddingBottom': '100px',
            'backgroundColor': '#f9f9f9'
        }
    )
)
