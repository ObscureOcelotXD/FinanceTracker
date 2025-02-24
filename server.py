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
        
    return app

if __name__ == '__main__':
    app = create_flask_app()
    app.run(host="0.0.0.0", port=5000, debug=True)
