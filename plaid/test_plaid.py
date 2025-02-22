import os
from dotenv import load_dotenv
import plaid
from plaid.api import plaid_api
from plaid.model.sandbox_public_token_create_request import SandboxPublicTokenCreateRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.products import Products  # 🛠 Import Plaid's Enum for Products
from plaid.configuration import Configuration
from plaid.api_client import ApiClient

# Load environment variables
load_dotenv()

# Get credentials from .env
PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID")
PLAID_SECRET = os.getenv("PLAID_SECRET")

# Configure Plaid API client
configuration = Configuration(
    host=plaid.Environment.Sandbox,
    api_key={
        "clientId": PLAID_CLIENT_ID,
        "secret": PLAID_SECRET,
    }
)

api_client = ApiClient(configuration)
client = plaid_api.PlaidApi(api_client)


# ✅ Step 1: Create a public token (simulating a user linking a bank account)
request = SandboxPublicTokenCreateRequest(
    institution_id="ins_109508",  # Simulated Chase Bank
    initial_products = [Products("auth"), Products("transactions")]  # 🛠 Use Products Enum instead of strings
)

response = client.sandbox_public_token_create(request)
public_token = response.public_token
print(f"🔗 Public Token: {public_token}")

# ✅ Step 2: Exchange public token for access token
exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
exchange_response = client.item_public_token_exchange(exchange_request)
access_token = exchange_response.access_token
print(f"✅ Access Token: {access_token}")

# ✅ Step 3: Retrieve test account data
accounts_request = AccountsGetRequest(access_token=access_token)
accounts_response = client.accounts_get(accounts_request)
print(f"🏦 Accounts: {accounts_response.to_dict()}")
