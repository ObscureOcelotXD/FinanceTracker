from types import SimpleNamespace

import pytest


def _enum_values(values):
    return [getattr(value, "value", str(value)) for value in values]


@pytest.fixture
def temp_db(tmp_path):
    import db_manager

    db_manager.DATABASE = str(tmp_path / "test_finance_data.db")
    db_manager.init_db()
    return db_manager.DATABASE


@pytest.fixture
def client(temp_db):
    from server import create_flask_app

    app = create_flask_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_create_link_token_uses_env_configuration(client, monkeypatch):
    import api.plaid_api as plaid_module

    captured = {}

    def fake_link_token_create(request):
        captured["client_name"] = request.client_name
        captured["products"] = _enum_values(request.products)
        captured["country_codes"] = _enum_values(request.country_codes)
        captured["redirect_uri"] = getattr(request, "redirect_uri", None)
        captured["webhook"] = getattr(request, "webhook", None)
        captured["link_customization_name"] = getattr(request, "link_customization_name", None)
        return SimpleNamespace(link_token="link-token-123")

    monkeypatch.setenv("PUBLIC_APP_NAME", "FinanceTracker Test")
    monkeypatch.setenv("PLAID_PRODUCTS", "transactions, investments")
    monkeypatch.setenv("PLAID_COUNTRY_CODES", "US, CA")
    monkeypatch.setenv("PLAID_REDIRECT_URI", "https://example.com/oauth/callback")
    monkeypatch.setenv("PLAID_WEBHOOK", "https://example.com/webhook")
    monkeypatch.setenv("PLAID_LINK_CUSTOMIZATION_NAME", "pfm-readonly")
    monkeypatch.setattr(plaid_module.client, "link_token_create", fake_link_token_create)

    response = client.post("/create_link_token")

    assert response.status_code == 200
    assert response.get_json()["link_token"] == "link-token-123"
    assert captured["client_name"] == "FinanceTracker Test"
    assert captured["products"] == ["transactions", "investments"]
    assert captured["country_codes"] == ["US", "CA"]
    assert captured["redirect_uri"] == "https://example.com/oauth/callback"
    assert captured["webhook"] == "https://example.com/webhook"
    assert captured["link_customization_name"] == "pfm-readonly"


def test_create_link_token_returns_500_on_client_error(client, monkeypatch):
    import api.plaid_api as plaid_module

    def fake_link_token_create(_request):
        raise RuntimeError("Plaid unavailable")

    monkeypatch.setattr(plaid_module.client, "link_token_create", fake_link_token_create)

    response = client.post("/create_link_token")

    assert response.status_code == 500
    assert response.get_json()["error"] == "Plaid unavailable"


def test_exchange_public_token_requires_public_token(client):
    response = client.post("/exchange_public_token", json={})

    assert response.status_code == 400
    assert response.get_json()["error"] == "Missing public_token"


def test_exchange_public_token_returns_warnings_for_partial_failures(client, monkeypatch):
    import api.plaid_api as plaid_module

    captured = {}

    def fake_exchange(_request):
        return SimpleNamespace(access_token="access-123", item_id="item-123")

    def fake_insert_items(item_id, access_token):
        captured["inserted"] = (item_id, access_token)

    def fake_update_item_institution(item_id, institution_name=None, institution_id=None):
        captured["institution"] = (item_id, institution_name, institution_id)

    monkeypatch.setattr(plaid_module.client, "item_public_token_exchange", fake_exchange)
    monkeypatch.setattr(plaid_module.db_manager, "insert_items", fake_insert_items)
    monkeypatch.setattr(plaid_module.db_manager, "update_item_institution", fake_update_item_institution)
    monkeypatch.setattr(plaid_module, "store_accounts", lambda _client, token, item_id=None: captured.update(accounts=(token, item_id)))
    monkeypatch.setattr(plaid_module, "store_transactions", lambda _client, _token: (_ for _ in ()).throw(RuntimeError("txn down")))
    monkeypatch.setattr(plaid_module, "store_investment_holdings", lambda _client, _token: (_ for _ in ()).throw(RuntimeError("holdings down")))

    response = client.post(
        "/exchange_public_token",
        json={
            "public_token": "public-123",
            "institution_name": "Test Bank",
            "institution_id": "ins_123",
        },
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["status"] == "linked"
    assert payload["item_id"] == "item-123"
    assert payload["warnings"] == ["transactions: txn down", "holdings: holdings down"]
    assert captured["inserted"] == ("item-123", "access-123")
    assert captured["institution"] == ("item-123", "Test Bank", "ins_123")
    assert captured["accounts"] == ("access-123", "item-123")


def test_import_holdings_requires_linked_items(client, monkeypatch):
    import api.plaid_api as plaid_module

    monkeypatch.setattr(plaid_module.db_manager, "get_items", lambda: [])

    response = client.post("/plaid/import_holdings")

    assert response.status_code == 400
    assert response.get_json()["error"] == "No linked Plaid items found."


def test_import_transactions_collects_warnings(client, monkeypatch):
    import api.plaid_api as plaid_module

    monkeypatch.setattr(
        plaid_module.db_manager,
        "get_items",
        lambda: [
            {"item_id": "item-1", "access_token": "token-1"},
            {"item_id": "item-2", "access_token": "token-2"},
        ],
    )

    def fake_store_transactions(_client, access_token):
        if access_token == "token-2":
            raise RuntimeError("transactions unavailable")

    monkeypatch.setattr(plaid_module, "store_transactions", fake_store_transactions)

    response = client.post("/plaid/import_transactions")

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["items_processed"] == 1
    assert payload["warnings"] == ["transactions unavailable"]
