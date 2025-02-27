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
import os
import sqlite3
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config["DEBUG"] = True

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

@app.route('/')
def index():
    return render_template('index.html')  # Serve the HTML page




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
            # Exchange the public token for an access token using Plaid API
            exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
            exchange_response = client.item_public_token_exchange(exchange_request)
            access_token = exchange_response.access_token
            item_id = exchange_response.item_id

            # Store the access token and item_id in a SQLite database
            conn = sqlite3.connect("finance_data.db")
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    item_id TEXT PRIMARY KEY,
                    access_token TEXT
                )
            """)
            c.execute("INSERT OR REPLACE INTO items (item_id, access_token) VALUES (?, ?)",
                      (item_id, access_token))
            conn.commit()
            conn.close()

            return jsonify({"access_token": access_token, "item_id": item_id})
        except Exception as e:
            print(f"❌ ERROR exchanging public token: {str(e)}")
            return jsonify({"error": str(e)}), 500
    
    from plaid.model.accounts_get_request import AccountsGetRequest

    @app.route('/get_accounts', methods=['GET'])
    def get_accounts():
        try:
            # You might retrieve the access token from your SQLite database based on the item_id
            access_token = "retrieved-access-token"  # Replace with actual retrieval logic
            accounts_request = AccountsGetRequest(access_token=access_token)
            accounts_response = client.accounts_get(accounts_request)
            return jsonify(accounts_response.to_dict())
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        
    return app

if __name__ == '__main__':
    app = create_flask_app()
    app.run(host="0.0.0.0", port=5000, debug=True)
