"""Smoke tests for Flask routes: index, quant, filings, quant/risk_summary."""
import pandas as pd
import pytest


@pytest.fixture
def temp_db(tmp_path):
    """Point db_manager at a temp DB and init it before server is imported."""
    import db_manager
    db_manager.DATABASE = str(tmp_path / "test_finance_data.db")
    db_manager.init_db()
    return db_manager.DATABASE


@pytest.fixture
def client(temp_db):
    """Flask test client using create_flask_app(). Depends on temp_db so DB is ready before server import."""
    from server import create_flask_app
    app = create_flask_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_index_returns_200(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"Privacy Mode" in r.data
    assert b'privacyModeSelect' in r.data


def test_quant_returns_200(client):
    r = client.get("/quant")
    assert r.status_code == 200


def test_filings_returns_200(client):
    r = client.get("/filings")
    assert r.status_code == 200


def test_privacy_returns_200(client):
    r = client.get("/privacy")
    assert r.status_code == 200


def test_terms_returns_200(client):
    r = client.get("/terms")
    assert r.status_code == 200


def test_support_returns_200(client):
    r = client.get("/support")
    assert r.status_code == 200


def test_favicon_returns_204(client):
    r = client.get("/favicon.ico")
    assert r.status_code == 204
    assert r.data == b""


def test_oauth_callback_redirects_home(client):
    r = client.get("/oauth/callback")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/")


def test_webhook_returns_received_status(client):
    r = client.post("/webhook", json={"event": "SYNC_UPDATES_AVAILABLE"})
    assert r.status_code == 200
    assert r.get_json() == {"status": "received"}


def test_admin_wipe_all_returns_ok(client, monkeypatch):
    import server

    captured = {}
    monkeypatch.setattr(server.db_manager, "wipe_all_data", lambda force=False: captured.setdefault("force", force))

    r = client.post("/admin/wipe_all")

    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}
    assert captured["force"] is True


def test_admin_get_etf_sources_returns_sorted_items(client, monkeypatch):
    import server

    monkeypatch.setattr(
        server.db_manager,
        "get_etf_sources",
        lambda: pd.DataFrame(
            [
                {"symbol": "VOO", "source_type": "provider_csv", "url": "https://b.example", "updated_at": "2026-01-02"},
                {"symbol": "AAPL", "source_type": "yahoo_top_holdings", "url": "https://a.example", "updated_at": "2026-01-01"},
            ]
        ),
    )

    r = client.get("/admin/etf_sources")

    assert r.status_code == 200
    assert [item["symbol"] for item in r.get_json()["items"]] == ["AAPL", "VOO"]


def test_admin_upsert_etf_source_requires_symbol(client):
    r = client.post("/admin/etf_sources", json={})
    assert r.status_code == 400
    assert r.get_json()["error"] == "Missing symbol"


def test_admin_upsert_etf_source_returns_resolved_source(client, monkeypatch):
    from api import etf_breakdown

    monkeypatch.setattr(
        etf_breakdown,
        "resolve_source",
        lambda symbol, url=None, source_type=None, allow_auto_lookup=True: {
            "symbol": symbol,
            "url": url,
            "source_type": source_type or "provider_csv",
        },
    )

    r = client.post(
        "/admin/etf_sources",
        json={"symbol": "VOO", "url": "https://example.com/voo.csv", "source_type": "provider_csv"},
    )

    payload = r.get_json()
    assert r.status_code == 200
    assert payload["status"] == "ok"
    assert payload["source"]["symbol"] == "VOO"
    assert payload["source"]["source_type"] == "provider_csv"


def test_quant_risk_summary_returns_200_and_json(client):
    r = client.get("/quant/risk_summary")
    assert r.status_code == 200
    data = r.get_json()
    assert data is not None
    assert "volatility_pct" in data
    assert "max_drawdown_pct" in data
    assert "beta" in data
    assert "last_updated" in data
    assert "fresh" in data
