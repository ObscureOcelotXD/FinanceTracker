from flask import Flask, render_template, jsonify, request
from plaid.configuration import Configuration,Environment
from plaid.api import plaid_api
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.country_code import CountryCode
from plaid.configuration import Configuration
from plaid.api_client import ApiClient
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.accounts_get_request import AccountsGetRequest
from flask import Flask, render_template
from dash import Dash, Input, Output  # Import Dash components
import dash_bootstrap_components as dbc  # Optional for styling
from datetime import datetime, timedelta
import logging
import os
import db_manager
import plotly.express as px
import alpha_api as av
# import finnhub_api as finn
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config["DEBUG"] = True
#region Plaid API Configuration

# Convert PLAID_ENV string to the correct Plaid Environment object
PLAID_ENV = os.getenv("PLAID_ENV", "sandbox").strip().lower()  # Ensure no spaces

# Map PLAID_ENV to Plaid Environment
environment = {
    'sandbox': Environment.Sandbox,
    'production': Environment.Production
}.get(PLAID_ENV)

if environment is None:
    raise ValueError(f"Invalid PLAID_ENV value: {PLAID_ENV}")

# Plaid client configuration
configuration = Configuration(
    host=environment,  # ✅ Now correctly mapped to Plaid's environment object
    api_key={
        'clientId': os.getenv('PLAID_CLIENT_ID'),
        'secret': os.getenv('PLAID_SECRET'),
    }
)

api_client = ApiClient(configuration)
client = plaid_api.PlaidApi(api_client)
# endregion

@app.route('/')
def index():
    return render_template('index.html')  # Serve the HTML page


def create_flask_app():
    # Configure logging
    logging.basicConfig(level=logging.DEBUG)

    app = Flask(__name__)

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/create_link_token', methods=['POST'])
    def create_link_token():
        try:
            # ✅ Use LinkTokenCreateRequestUser instead of a raw dictionary
            user = LinkTokenCreateRequestUser(client_user_id="unique_user_id")  # Replace with a unique user identifier
            
            request = LinkTokenCreateRequest(
                user=user,  # Pass the user object correctly
                client_name="Finance Tracker",  # Your app name
                products=[Products("auth"), Products("transactions")],
                country_codes=[CountryCode("US")],  # Ensure "US" is inside parentheses
                language="en",
                redirect_uri=os.getenv("PLAID_REDIRECT_URI")  # Must match the one registered in Plaid Dashboard
            )
            response = client.link_token_create(request)
            app.logger.debug("Link Token Creation Response: %s", response.to_dict() if hasattr(response, "to_dict") else response)
            return jsonify({"link_token": response.link_token})
        
        except Exception as e:
            print(f"❌ ERROR in /create_link_token: {str(e)}")  # Debugging output
            return jsonify({"error": str(e)}), 500


    
    @app.route('/exchange_public_token', methods=['POST'])
    def exchange_public_token():
        data = request.get_json()
        public_token = data.get("public_token")
        if not public_token:
            return jsonify({"error": "Missing public_token"}), 400
        try:
            exchange_request = ItemPublicTokenExchangeRequest(
                public_token=public_token
                #,webhook=os.getenv('PLAID_REDIRECT_URI_WEBHOOK')
                )
            exchange_response = client.item_public_token_exchange(exchange_request)
            access_token = exchange_response.access_token
            item_id = exchange_response.item_id

            db_manager.insert_items(item_id, access_token)

            store_accounts(client, access_token)
            store_transactions(client, access_token)

            return jsonify({"access_token": access_token, "item_id": item_id})
        except Exception as e:
            print(f"Error exchanging public token: {str(e)}")
            return jsonify({"error": str(e)}), 500
    

    def store_accounts(client, access_token):
        # Create a request to get accounts data
        request = AccountsGetRequest(access_token=access_token)
        response = client.accounts_get(request)
        accounts = response.accounts

        # Connect to SQLite and insert each account
        db_manager.store_accounts(accounts)



    def store_transactions(client, access_token):
        # Define a date range for transactions (e.g., last 30 days) as date objects
        start_date = (datetime.now() - timedelta(days=30)).date()
        end_date = datetime.now().date()
        
        request = TransactionsGetRequest(
            access_token=access_token,
            start_date=start_date,
            end_date=end_date
        )
        response = client.transactions_get(request)
        transactions = response.transactions
        db_manager.insert_transactions(transactions)


    @app.route('/webhook', methods=['POST'])
    def webhook():
        data = request.get_json()
        print("Received webhook:", data)
        return jsonify({"status": "received"}), 200
    

    app.register_blueprint(av.alpha_api)

    from finnhub_api import finnhub_api
    app.register_blueprint(finnhub_api)

    # app.register_blueprint(finn.finnhub_api)

    return app

if __name__ == '__main__':
    #app = create_flask_app() # uncomment to run app fron this file.
    app.run(host="0.0.0.0", port=5000, debug=True)
