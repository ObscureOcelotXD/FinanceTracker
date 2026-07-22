"""Smoke tests for Flask routes: index, quant, filings, news, quant/risk_summary."""
import pandas as pd
import pytest


@pytest.fixture
def temp_db(tmp_path):
    """Point db_manager at a temp DB and init it before server is imported."""
    from services import db_manager
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
    assert b"Covered Calls" in r.data
    assert b"Import CSV" in r.data
    assert b"hideManualEntryToggle" in r.data
    assert b"hidePlaidToggle" in r.data
    assert b"hideMutualFundsToggle" in r.data
    assert b"hideEtfsToggle" in r.data


def test_admin_hide_manual_entry_default_and_toggle(client):
    r = client.get("/admin/hide_manual_entry")
    assert r.status_code == 200
    assert r.get_json()["hide_manual_entry"] is True

    r2 = client.post("/admin/hide_manual_entry", json={"hide_manual_entry": False})
    assert r2.status_code == 200
    assert r2.get_json()["hide_manual_entry"] is False

    r3 = client.get("/admin/hide_manual_entry")
    assert r3.get_json()["hide_manual_entry"] is False

    r4 = client.post("/admin/hide_manual_entry", json={"hide_manual_entry": True})
    assert r4.get_json()["hide_manual_entry"] is True


def test_admin_hide_plaid_default_and_toggle(client):
    r = client.get("/admin/hide_plaid")
    assert r.status_code == 200
    assert r.get_json()["hide_plaid"] is True

    r2 = client.post("/admin/hide_plaid", json={"hide_plaid": False})
    assert r2.status_code == 200
    assert r2.get_json()["hide_plaid"] is False

    r3 = client.get("/admin/hide_plaid")
    assert r3.get_json()["hide_plaid"] is False


def test_admin_hide_mutual_funds_and_etfs_toggles(client):
    r = client.get("/admin/hide_mutual_funds")
    assert r.status_code == 200
    assert r.get_json()["hide_mutual_funds"] is False

    r2 = client.post("/admin/hide_mutual_funds", json={"hide_mutual_funds": True})
    assert r2.status_code == 200
    assert r2.get_json()["hide_mutual_funds"] is True

    r3 = client.get("/admin/hide_etfs")
    assert r3.status_code == 200
    assert r3.get_json()["hide_etfs"] is False

    r4 = client.post("/admin/hide_etfs", json={"hide_etfs": True})
    assert r4.status_code == 200
    assert r4.get_json()["hide_etfs"] is True

    r5 = client.get("/admin/security_types")
    assert r5.status_code == 200
    body = r5.get_json()
    assert "counts" in body
    assert "types" in body


def test_export_holdings_and_calls_csv(client, temp_db):
    from services import db_manager

    db_manager.replace_all_stocks(
        [{"brokerage": "Manual", "account": "Manage Stocks", "ticker": "MSFT", "shares": 10, "cost_basis": 100}]
    )
    db_manager.replace_all_covered_calls(
        [
            {
                "ticker": "MSFT",
                "strike": 400,
                "expiration_date": "2026-08-15",
                "contracts": 1,
                "premium_received": 20,
            }
        ]
    )
    h = client.get("/api/export/holdings.csv")
    assert h.status_code == 200
    assert b"MSFT" in h.data
    assert "attachment" in h.headers.get("Content-Disposition", "")

    c = client.get("/api/export/covered_calls.csv")
    assert c.status_code == 200
    assert b"MSFT" in c.data

    p = client.get("/api/export/portfolio.csv")
    assert p.status_code == 200
    assert b"type" in p.data
    assert b"stock" in p.data
    assert b"call" in p.data
    assert b"MSFT" in p.data
    assert "portfolio.csv" in p.headers.get("Content-Disposition", "")

    z = client.get("/api/export/portfolio.zip")
    assert z.status_code == 200
    assert z.data[:2] == b"PK"


def test_api_home_insights_returns_json(client):
    r = client.get("/api/home_insights")
    assert r.status_code == 200
    data = r.get_json()
    assert "enabled" in data
    assert isinstance(data.get("sources"), list)


def test_api_sec_filing_job_status_returns_json(client):
    r = client.get("/api/sec_filing_job_status")
    assert r.status_code == 200
    data = r.get_json()
    assert "status" in data
    assert data["status"] in ("idle", "running", "done", "error")
    assert "finished_age_seconds" in data
    assert "toast_eligible" in data
    assert isinstance(data["toast_eligible"], bool)


def test_api_quant_job_status_returns_json(client):
    r = client.get("/api/quant_job_status")
    assert r.status_code == 200
    data = r.get_json()
    assert "status" in data
    assert data["status"] in ("idle", "running", "done", "error")
    assert "toast_eligible" in data


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


def test_plaid_management_page_returns_200(client):
    from services import db_manager

    db_manager.set_hide_plaid(False)
    r = client.get("/plaid")
    assert r.status_code == 200
    assert b"Plaid Management" in r.data
    assert b"plaid-management.js" in r.data


def test_plaid_management_redirects_when_hidden(client):
    from services import db_manager

    db_manager.set_hide_plaid(True)
    r = client.get("/plaid")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/")


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

    def _wipe(force=False, wipe_etf_sources=False):
        captured["force"] = force
        captured["wipe_etf_sources"] = wipe_etf_sources

    monkeypatch.setattr(server.db_manager, "wipe_all_data", _wipe)

    r = client.post("/admin/wipe_all", json={"wipe_etf_sources": True})

    assert r.status_code == 200
    assert r.get_json() == {"status": "ok", "wipe_etf_sources": True}
    assert captured["force"] is True
    assert captured["wipe_etf_sources"] is True


def test_admin_backfill_prices_returns_ok(client, monkeypatch):
    def _fake_backfill(lookback_days=None, force=False):
        assert force is True
        assert lookback_days == 30
        return {
            "upserted": 12,
            "skipped": False,
            "reason": None,
            "lookback_days": 30,
            "distinct_dates": 20,
            "tickers": 3,
        }

    monkeypatch.setattr(
        "api.finnhub_api.backfill_held_price_history",
        _fake_backfill,
    )
    r = client.post("/admin/backfill_prices", json={"days": 30})
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "ok"
    assert data["upserted"] == 12
    assert data["tickers"] == 3


def test_admin_wipe_all_keeps_etf_by_default(client, monkeypatch):
    import server

    captured = {}

    def _wipe(force=False, wipe_etf_sources=False):
        captured["wipe_etf_sources"] = wipe_etf_sources

    monkeypatch.setattr(server.db_manager, "wipe_all_data", _wipe)

    r = client.post("/admin/wipe_all", json={})
    assert r.status_code == 200
    assert r.get_json()["wipe_etf_sources"] is False
    assert captured["wipe_etf_sources"] is False


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

    from services import db_manager

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

    from services import db_manager

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
