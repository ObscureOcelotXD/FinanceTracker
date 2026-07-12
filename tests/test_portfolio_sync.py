"""Tests for Umbrel Files / path portfolio sync."""
from unittest.mock import MagicMock

import pytest

from api import portfolio_sync as ps
from services import db_manager


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_manager.DATABASE = str(tmp_path / "test_finance_data.db")
    db_manager.init_db()
    sync_root = tmp_path / "Documents" / "Portfolio"
    monkeypatch.setenv("PORTFOLIO_SYNC_DIR", str(sync_root))
    monkeypatch.delenv("PORTFOLIO_SYNC_FILENAME", raising=False)
    monkeypatch.delenv("UMBREL_TAILSCALE_IP", raising=False)
    monkeypatch.delenv("UMBREL_HOST", raising=False)
    monkeypatch.delenv("UMBREL_PASSWORD", raising=False)
    monkeypatch.delenv("PORTFOLIO_FB_HOST", raising=False)
    return sync_root


@pytest.fixture
def umbrel_env(monkeypatch):
    monkeypatch.delenv("PORTFOLIO_SYNC_DIR", raising=False)
    monkeypatch.setenv("UMBREL_TAILSCALE_IP", "umbrel.test.ts.net")
    monkeypatch.setenv("UMBREL_PASSWORD", "umbrel-dash-secret")
    monkeypatch.delenv("PORTFOLIO_UMBREL_PATH", raising=False)
    monkeypatch.delenv("PORTFOLIO_FB_PATH", raising=False)
    monkeypatch.delenv("PORTFOLIO_SYNC_FILENAME", raising=False)


def _session_cm(session):
    class _CM:
        def __enter__(self):
            return session

        def __exit__(self, *args):
            return False

    return _CM()


def test_status_unconfigured(monkeypatch):
    monkeypatch.delenv("PORTFOLIO_SYNC_DIR", raising=False)
    monkeypatch.delenv("UMBREL_TAILSCALE_IP", raising=False)
    monkeypatch.delenv("UMBREL_HOST", raising=False)
    monkeypatch.delenv("PORTFOLIO_FB_HOST", raising=False)
    monkeypatch.delenv("UMBREL_PASSWORD", raising=False)
    assert ps.status()["configured"] is False


def test_maps_legacy_documents_path(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_FB_PATH", "/Documents/Portfolio")
    assert ps.remote_dir() == "/Home/Documents/Portfolio"
    assert ps.remote_file() == "/Home/Documents/Portfolio/portfolio.csv"


def test_status_warns_without_password(monkeypatch):
    monkeypatch.delenv("PORTFOLIO_SYNC_DIR", raising=False)
    monkeypatch.setenv("UMBREL_TAILSCALE_IP", "100.1.2.3")
    monkeypatch.delenv("UMBREL_PASSWORD", raising=False)
    st = ps.status()
    assert "UMBREL_PASSWORD" in st["message"]


def test_push_path_mode(temp_db, monkeypatch):
    from api import portfolio_import as pi

    monkeypatch.setattr(pi, "_refresh_prices_after_holdings_change", lambda: None)
    db_manager.replace_all_stocks(
        [{"brokerage": "Schwab", "account": "IRA", "ticker": "AAPL", "shares": 10, "cost_basis": 100}]
    )
    result = ps.push_portfolio_csv()
    assert result["mode"] == "path"
    assert (temp_db / "portfolio.csv").is_file()


def test_pull_path_mode(temp_db, monkeypatch):
    from api import portfolio_import as pi

    monkeypatch.setattr(pi, "_refresh_prices_after_holdings_change", lambda: None)
    temp_db.mkdir(parents=True, exist_ok=True)
    (temp_db / "portfolio.csv").write_text(
        "type,brokerage,account,ticker,shares,cost_basis/premium,strike,expiration_date,contracts,open_date,status,notes\n"
        "stock,Fidelity,Taxable,MSFT,5,1000,,,,,,\n",
        encoding="utf-8",
    )
    result = ps.pull_portfolio_csv()
    assert result.get("ok") is True
    assert db_manager.get_stocks().iloc[0]["ticker"] == "MSFT"


def test_push_umbrel_files(umbrel_env, tmp_path, monkeypatch):
    from api import portfolio_import as pi

    db_manager.DATABASE = str(tmp_path / "u.db")
    db_manager.init_db()
    monkeypatch.setattr(pi, "_refresh_prices_after_holdings_change", lambda: None)
    db_manager.replace_all_stocks(
        [{"brokerage": "Schwab", "account": "IRA", "ticker": "AAPL", "shares": 2, "cost_basis": 50}]
    )
    csv_body = pi.export_portfolio_csv()

    session = MagicMock()
    login = MagicMock(
        status_code=200,
        text='{"result":{"data":"jwt-token"}}',
        headers={"Content-Type": "application/json"},
    )
    login.json.return_value = {"result": {"data": "jwt-token"}}
    list_ok = MagicMock(
        status_code=200,
        text='{"result":{"data":{"files":[]}}}',
        headers={"Content-Type": "application/json"},
    )
    list_ok.json.return_value = {"result": {"data": {"files": []}}}
    upload_ok = MagicMock(status_code=200, text="ok", headers={"Content-Type": "text/plain"})
    download_ok = MagicMock(
        status_code=200,
        content=csv_body.encode(),
        text=csv_body,
        headers={"Content-Type": "text/csv"},
    )

    def _post(url, *args, **kwargs):
        if "user.login" in url:
            return login
        if "createDirectory" in url:
            return MagicMock(
                status_code=200,
                text='{"result":{"data":true}}',
                headers={"Content-Type": "application/json"},
                **{"json.return_value": {"result": {"data": True}}},
            )
        return upload_ok

    def _get(url, *args, **kwargs):
        if "/api/files/download" in url:
            return download_ok
        return list_ok

    session.post.side_effect = _post
    session.get.side_effect = _get
    monkeypatch.setattr(ps.requests, "Session", lambda: _session_cm(session))

    result = ps.push_portfolio_csv()
    assert result["ok"] is True
    assert result["mode"] == "umbrel_files"
    assert "/Home/Documents/Portfolio/portfolio.csv" in result["file"]
