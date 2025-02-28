from flask import Flask, redirect, request, session, url_for
from plaid.api import plaid_api
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.products import Products
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.configuration import Configuration
from plaid.api_client import ApiClient
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Ensure you have a secret key for session management

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



@app.route('/create_link_token', methods=['POST'])
def create_link_token():
    user = {
        'client_user_id': 'unique_user_id'  # Replace with a unique identifier for the user
    }
    request = LinkTokenCreateRequest(
        user=user,
        client_name='Your App Name',
        products=[Products.TRANSACTIONS],
        country_codes=[CountryCode.US],
        language='en',
        redirect_uri=os.getenv('PLAID_REDIRECT_URI'),
        webhook=os.getenv('PLAID_REDIRECT_URI_WEBHOOK') 
    )
    response = client.link_token_create(request)
    link_token = response['link_token']
    return {'link_token': link_token}


@app.route('/oauth/callback', methods=['GET'])
def oauth_callback():
    public_token = request.args.get('public_token')
    exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
    exchange_response = client.item_public_token_exchange(exchange_request)
    access_token = exchange_response['access_token']
    # Store access_token securely; it's needed for future API calls
    session['access_token'] = access_token
    return redirect(url_for('index'))
