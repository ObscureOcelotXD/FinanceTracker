"""Smoke tests for Flask routes: index, quant, filings, news, quant/risk_summary."""
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
def client(temp_db, monkeypatch):
    """Flask test client using create_flask_app(). Depends on temp_db so DB is ready before server import."""
    monkeypatch.setenv("NEWS_DIGEST_DISABLE_SCHEDULER", "1")
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
    assert b"Today's news" in r.data
    assert b"Refresh insights" in r.data
    assert b"View all news" in r.data


def test_api_home_insights_returns_json(client):
    r = client.get("/api/home_insights")
    assert r.status_code == 200
    data = r.get_json()
    assert "enabled" in data
    assert isinstance(data.get("sources"), list)


def test_news_page_returns_200(client):
    r = client.get("/news")
    assert r.status_code == 200
    assert b"All news" in r.data
    assert b"newsDigestTableBody" in r.data
    assert b"Headline" in r.data


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


def test_api_news_digest_get_returns_json(client):
    r = client.get("/api/news_digest")
    assert r.status_code == 200
    data = r.get_json()
    assert "items" in data
    assert isinstance(data["items"], list)


def test_api_news_articles_list_returns_json(client):
    r = client.get("/api/news_articles?page=1&per_page=10")
    assert r.status_code == 200
    data = r.get_json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "per_page" in data
    assert "pages" in data
    assert isinstance(data["items"], list)


def test_api_news_articles_day_mode_returns_json(client):
    r = client.get("/api/news_articles")
    assert r.status_code == 200
    data = r.get_json()
    assert "items" in data
    assert "date" in data
    assert "older_date" in data
    assert "newer_date" in data
    assert "schedule_tz" in data
    assert "digest_generated_at_utc" in data
    assert isinstance(data["items"], list)


def test_api_news_articles_day_mode_invalid_date(client):
    r = client.get("/api/news_articles?date=not-a-date")
    assert r.status_code == 400


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


def test_client_error_endpoint_disabled_by_default(client, monkeypatch):
    # .env may enable logging; this test asserts the endpoint is off when flags are unset.
    monkeypatch.delenv("ENABLE_ERROR_LOG", raising=False)
    monkeypatch.delenv("ENABLE_CLIENT_ERROR_LOG", raising=False)
    monkeypatch.delenv("ENABLE_SERVER_ERROR_LOG", raising=False)
    r = client.post("/api/client_error", json={"source": "t", "message": "m"})
    assert r.status_code == 200
    assert r.get_json() == {"status": "disabled"}


def test_client_error_endpoint_stores_when_enabled(client, monkeypatch, temp_db):
    import sqlite3

    import db_manager

    monkeypatch.setenv("ENABLE_CLIENT_ERROR_LOG", "1")
    r = client.post(
        "/api/client_error",
        json={"source": "ui", "message": "fetch failed", "detail": "timeout"},
    )
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}
    conn = sqlite3.connect(db_manager.DATABASE)
    row = conn.execute(
        "SELECT origin, source, message, detail FROM client_error_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row == ("client", "ui", "fetch failed", "timeout")


def test_server_unhandled_exception_logged_when_enabled(temp_db, monkeypatch):
    import sqlite3

    import db_manager

    monkeypatch.setenv("NEWS_DIGEST_DISABLE_SCHEDULER", "1")
    monkeypatch.setenv("ENABLE_SERVER_ERROR_LOG", "1")
    from server import create_flask_app

    app = create_flask_app()
    app.config["TESTING"] = True
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.route("/__test_crash")
    def _crash():
        raise ValueError("intentional test error")

    with app.test_client() as c:
        r = c.get("/__test_crash")
        assert r.status_code == 500

    conn = sqlite3.connect(db_manager.DATABASE)
    row = conn.execute(
        "SELECT origin, source, message FROM client_error_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    detail = conn.execute(
        "SELECT detail FROM client_error_log ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    conn.close()
    assert row[0] == "server"
    assert "__test_crash" in row[1]
    assert "ValueError" in row[2]
    assert detail and "intentional test error" in detail
