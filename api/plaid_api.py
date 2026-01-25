from flask import Blueprint, jsonify, request
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
from plaid.model.investments_holdings_get_request import InvestmentsHoldingsGetRequest
from datetime import datetime, timedelta
import logging
import os
import db_manager

plaid_bp = Blueprint('plaid_api', __name__)
#region Plaid API Configuration

# Convert PLAID_ENV string to the correct Plaid Environment object
PLAID_ENV = os.getenv("PLAID_ENV", "sandbox").strip().lower()  # Ensure no spaces

# Map PLAID_ENV to Plaid Environment
environment_map = {
    'sandbox': Environment.Sandbox,
    'production': Environment.Production,
}
if hasattr(Environment, "Development"):
    environment_map["development"] = Environment.Development
else:
    # Older SDKs don't expose Development; fallback to Sandbox.
    environment_map["development"] = Environment.Sandbox

environment = environment_map.get(PLAID_ENV)

if environment is None:
    raise ValueError(f"Invalid PLAID_ENV value: {PLAID_ENV}")

if PLAID_ENV == "development" and not hasattr(Environment, "Development"):
    effective_env_name = "sandbox"
else:
    effective_env_name = PLAID_ENV

print(f"[Plaid] Environment: {effective_env_name}")

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


@plaid_bp.route('/create_link_token', methods=['POST'])
def create_link_token():
    try:
        # ✅ Use LinkTokenCreateRequestUser instead of a raw dictionary
        user = LinkTokenCreateRequestUser(client_user_id="unique_user_id")  # Replace with a unique user identifier

        request_kwargs = {
            "user": user,
            "client_name": "Finance Tracker",
            "products": [Products("auth"), Products("transactions"), Products("investments")],
            "country_codes": [CountryCode("US")],
            "language": "en",
            "redirect_uri": os.getenv("PLAID_REDIRECT_URI"),
        }
        webhook = os.getenv("PLAID_WEBHOOK")
        if webhook:
            request_kwargs["webhook"] = webhook

        request = LinkTokenCreateRequest(**request_kwargs)
        response = client.link_token_create(request)
        # plaid_api.logger.debug("Link Token Creation Response: %s", response.to_dict() if hasattr(response, "to_dict") else response)
        return jsonify({"link_token": response.link_token, "plaid_env": effective_env_name})
    
    except Exception as e:
        print(f"❌ ERROR in /create_link_token: {str(e)}")  # Debugging output
        return jsonify({"error": str(e)}), 500


    
@plaid_bp.route('/exchange_public_token', methods=['POST'])
def exchange_public_token():
    data = request.get_json()
    public_token = data.get("public_token")
    institution_name = data.get("institution_name")
    institution_id = data.get("institution_id")
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
        if institution_name or institution_id:
            db_manager.update_item_institution(item_id, institution_name, institution_id)

        errors = []
        store_accounts(client, access_token, item_id=item_id)
        try:
            store_transactions(client, access_token)
        except Exception as exc:
            errors.append(f"transactions: {exc}")
        try:
            store_investment_holdings(client, access_token)
        except Exception as exc:
            errors.append(f"holdings: {exc}")

        payload = {"item_id": item_id, "status": "linked"}
        if errors:
            payload["warnings"] = errors
        return jsonify(payload)
    except Exception as e:
        print(f"Error exchanging public token: {str(e)}")
        return jsonify({"error": str(e)}), 500


def store_accounts(client, access_token, item_id=None):
    # Create a request to get accounts data
    request = AccountsGetRequest(access_token=access_token)
    response = client.accounts_get(request)
    accounts = response.accounts

    # Connect to SQLite and insert each account
    db_manager.store_accounts(accounts, item_id=item_id)



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


def store_investment_holdings(client, access_token):
    request = InvestmentsHoldingsGetRequest(access_token=access_token)
    response = client.investments_holdings_get(request)
    holdings = response.holdings
    securities = {sec.security_id: sec for sec in response.securities}
    imported = 0
    skipped = 0
    for holding in holdings:
        security = securities.get(holding.security_id)
        ticker = getattr(security, "ticker_symbol", None) if security else None
        if not ticker:
            skipped += 1
            continue
        quantity = float(holding.quantity) if holding.quantity is not None else 0.0
        cost_basis_per_share = holding.cost_basis
        total_cost_basis = None
        if cost_basis_per_share is not None:
            total_cost_basis = float(cost_basis_per_share) * quantity
        db_manager.upsert_plaid_holding(holding.account_id, ticker.upper(), quantity, total_cost_basis)
        imported += 1
    print(f"[Plaid] Holdings import complete. Imported={imported}, Skipped={skipped}")


@plaid_bp.route('/plaid/import_holdings', methods=['POST'])
def import_holdings():
    try:
        items = db_manager.get_items()
        if not items:
            return jsonify({"error": "No linked Plaid items found."}), 400
        total_imported = 0
        errors = []
        for item in items:
            try:
                store_investment_holdings(client, item["access_token"])
                total_imported += 1
            except Exception as exc:
                errors.append(str(exc))
        payload = {"status": "ok", "items_processed": total_imported}
        if errors:
            payload["warnings"] = errors
        return jsonify(payload)
    except Exception as e:
        print(f"[Plaid] Error importing holdings: {str(e)}")
        return jsonify({"error": str(e)}), 500


@plaid_bp.route('/plaid/import_transactions', methods=['POST'])
def import_transactions():
    try:
        items = db_manager.get_items()
        if not items:
            return jsonify({"error": "No linked Plaid items found."}), 400
        total = 0
        errors = []
        for item in items:
            try:
                store_transactions(client, item["access_token"])
                total += 1
            except Exception as exc:
                errors.append(str(exc))
        payload = {"status": "ok", "items_processed": total}
        if errors:
            payload["warnings"] = errors
        return jsonify(payload)
    except Exception as e:
        print(f"[Plaid] Error importing transactions: {str(e)}")
        return jsonify({"error": str(e)}), 500