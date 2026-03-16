"""Smoke tests for Flask routes: index, quant, filings, quant/risk_summary."""
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


def test_quant_returns_200(client):
    r = client.get("/quant")
    assert r.status_code == 200


def test_filings_returns_200(client):
    r = client.get("/filings")
    assert r.status_code == 200


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
