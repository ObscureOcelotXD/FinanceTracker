from flask import Flask, render_template, jsonify, request
from plaid.api import plaid_api
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.products import Products
from plaid.model.country_code import CountryCode
from plaid.configuration import Configuration
from plaid.api_client import ApiClient
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Plaid client configuration
configuration = Configuration(
    host=os.getenv('PLAID_ENV', 'sandbox'),
    api_key={
        'clientId': os.getenv('PLAID_CLIENT_ID'),
        'secret': os.getenv('PLAID_SECRET'),
    }
)
api_client = ApiClient(configuration)
client = plaid_api.PlaidApi(api_client)

@app.route('/')
def index():
    return render_template('index.html')  # Serve the HTML page

@app.route('/create_link_token', methods=['POST'])
def create_link_token():
    request = LinkTokenCreateRequest(
        user={'client_user_id': 'unique_user_id'},  # Replace with unique user ID
        client_name='Your App Name',
        products=[Products.TRANSACTIONS],
        country_codes=[CountryCode.US],
        language='en',
        redirect_uri=os.getenv('PLAID_REDIRECT_URI')
    )
    response = client.link_token_create(request)
    return jsonify({'link_token': response.link_token})

@app.route('/exchange_public_token', methods=['POST'])
def exchange_public_token():
    public_token = request.json.get('public_token')
    exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
    exchange_response = client.item_public_token_exchange(exchange_request)
    access_token = exchange_response.access_token
    # Store access_token securely for future use
    return jsonify({'status': 'success'})


def create_flask_app():
    app = Flask(__name__)

    @app.route('/')
    def index():
        return render_template('index.html')

    return app

if __name__ == '__main__':
    app.run(port=5000)
