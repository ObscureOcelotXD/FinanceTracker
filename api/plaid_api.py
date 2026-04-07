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
from plaid.model.item_remove_request import ItemRemoveRequest
from datetime import datetime, timedelta
import logging
import os
import db_manager

_LOG = logging.getLogger(__name__)

plaid_bp = Blueprint('plaid_api', __name__)
#region Plaid API Configuration


def _parse_csv_env(name, default_values):
    raw_value = os.getenv(name, "")
    values = [part.strip() for part in raw_value.split(",") if part.strip()]
    return values or list(default_values)


def _get_link_products():
    # Default to the narrowest PFM scope this app uses today.
    return [Products(name) for name in _parse_csv_env("PLAID_PRODUCTS", ["transactions", "investments"])]


def _get_country_codes():
    return [CountryCode(code.upper()) for code in _parse_csv_env("PLAID_COUNTRY_CODES", ["US"])]


def _get_client_name():
    return (
        os.getenv("PLAID_CLIENT_NAME")
        or os.getenv("PUBLIC_APP_NAME")
        or "FinanceTracker"
    ).strip()


def _is_nonfatal_investments_skip(exc):
    text = str(exc)
    return (
        "ADDITIONAL_CONSENT_REQUIRED" in text
        and "PRODUCT_INVESTMENTS" in text
    )


def _investments_skip_message():
    return "Skipped investment holdings import because this item does not have investment consent or investment accounts."

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

# Use environment-specific credentials: sandbox vs production
if PLAID_ENV == "production":
    _client_id = os.getenv("PLAID_CLIENT_ID")
    _secret = os.getenv("PLAID_SECRET")
else:
    # Sandbox or development: prefer PLAID_SANDBOX_* for testing, fallback to PLAID_*
    _client_id = os.getenv("PLAID_SANDBOX_CLIENT_ID") or os.getenv("PLAID_CLIENT_ID")
    _secret = os.getenv("PLAID_SANDBOX_SECRET") or os.getenv("PLAID_SECRET")

configuration = Configuration(
    host=environment,
    api_key={
        "clientId": _client_id,
        "secret": _secret,
    },
)

api_client = ApiClient(configuration)
client = plaid_api.PlaidApi(api_client)
# endregion


def _plaid_item_remove(access_token: str) -> None:
    client.item_remove(ItemRemoveRequest(access_token=access_token))


def _remove_stale_plaid_items_for_institution(
    institution_id,
    institution_name,
    new_item_id: str,
) -> list[str]:
    """
    When the user links an institution again, Plaid returns a new item_id.
    Remove prior Items for the same institution locally and at Plaid.
    """
    if not institution_id and not institution_name:
        return []
    stale = db_manager.find_plaid_items_matching_institution(
        institution_id=institution_id,
        institution_name=institution_name,
        exclude_item_id=new_item_id,
    )
    removed_ids: list[str] = []
    for row in stale:
        old_id = row["item_id"]
        try:
            _plaid_item_remove(row["access_token"])
        except Exception as exc:
            _LOG.warning("Plaid item_remove failed for item_id=%s: %s", old_id, exc)
        db_manager.delete_plaid_item_data(old_id)
        removed_ids.append(old_id)
    return removed_ids


@plaid_bp.route('/create_link_token', methods=['POST'])
def create_link_token():
    try:
        # ✅ Use LinkTokenCreateRequestUser instead of a raw dictionary
        user = LinkTokenCreateRequestUser(client_user_id="unique_user_id")  # Replace with a unique user identifier

        request_kwargs = {
            "user": user,
            "client_name": _get_client_name(),
            "products": _get_link_products(),
            "country_codes": _get_country_codes(),
            "language": "en",
        }
        link_customization = (os.getenv("PLAID_LINK_CUSTOMIZATION_NAME") or "").strip()
        if link_customization:
            request_kwargs["link_customization_name"] = link_customization
        redirect_uri = (os.getenv("PLAID_REDIRECT_URI") or "").strip()
        if redirect_uri:
            request_kwargs["redirect_uri"] = redirect_uri
        webhook = (os.getenv("PLAID_WEBHOOK") or "").strip()
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

        replaced_ids = _remove_stale_plaid_items_for_institution(
            institution_id, institution_name, item_id
        )

        db_manager.insert_items(item_id, access_token)
        if institution_name or institution_id:
            db_manager.update_item_institution(item_id, institution_name, institution_id)

        errors = []
        messages = []
        holdings_status = "imported"
        store_accounts(client, access_token, item_id=item_id)
        try:
            store_transactions(client, access_token)
        except Exception as exc:
            errors.append(f"transactions: {exc}")
        try:
            store_investment_holdings(client, access_token)
        except Exception as exc:
            if _is_nonfatal_investments_skip(exc):
                holdings_status = "skipped"
                messages.append(_investments_skip_message())
            else:
                holdings_status = "error"
                errors.append(f"holdings: {exc}")

        payload = {
            "item_id": item_id,
            "status": "linked",
            "holdings_status": holdings_status,
            "link_action": "updated" if replaced_ids else "linked",
            "replaced_item_ids": replaced_ids,
        }
        if messages:
            payload["messages"] = messages
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


@plaid_bp.route("/plaid/items", methods=["GET"])
def list_plaid_items():
    return jsonify({"items": db_manager.list_plaid_items_public()})


@plaid_bp.route("/plaid/disconnect", methods=["POST"])
def disconnect_plaid_item_route():
    data = request.get_json(silent=True) or {}
    item_id = (data.get("item_id") or "").strip()
    if not item_id:
        return jsonify({"error": "Missing item_id"}), 400
    row = db_manager.get_plaid_item_by_id(item_id)
    if not row:
        return jsonify({"error": "Unknown item_id"}), 404
    warn = None
    try:
        _plaid_item_remove(row["access_token"])
    except Exception as exc:
        warn = str(exc)
        _LOG.warning("Plaid item_remove on disconnect failed item_id=%s: %s", item_id, exc)
    deleted = db_manager.delete_plaid_item_data(item_id)
    payload = {"status": "ok", "item_id": item_id, "deleted": deleted}
    if warn:
        payload["warning"] = warn
    return jsonify(payload)


@plaid_bp.route('/plaid/import_holdings', methods=['POST'])
def import_holdings():
    try:
        items = db_manager.get_items()
        if not items:
            return jsonify({"error": "No linked Plaid items found."}), 400
        total_imported = 0
        total_skipped = 0
        errors = []
        messages = []
        for item in items:
            try:
                store_investment_holdings(client, item["access_token"])
                total_imported += 1
            except Exception as exc:
                if _is_nonfatal_investments_skip(exc):
                    total_skipped += 1
                else:
                    errors.append(str(exc))
        if total_skipped:
            messages.append(
                f"Skipped holdings import for {total_skipped} item(s) because investment consent or investment accounts were not available."
            )
        payload = {"status": "ok", "items_processed": total_imported, "items_skipped": total_skipped}
        if messages:
            payload["messages"] = messages
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