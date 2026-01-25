import datetime

import api.finnhub_api as finnhub_api


def test_polygon_preferred_over_finnhub(monkeypatch):
    now = datetime.datetime.utcnow()
    cached_records = {}
    captured = {}

    def fake_get_sector_records(tickers):
        return cached_records

    def fake_upsert_stock_sector(ticker, sector, updated_at):
        captured["ticker"] = ticker
        captured["sector"] = sector
        captured["updated_at"] = updated_at

    monkeypatch.setattr(finnhub_api, "get_sector_records", fake_get_sector_records)
    monkeypatch.setattr(finnhub_api, "upsert_stock_sector", fake_upsert_stock_sector)
    monkeypatch.setattr(
        finnhub_api.polygon_api,
        "get_polygon_industry",
        lambda ticker: "Data Processing",
    )
    monkeypatch.setattr(
        finnhub_api,
        "fetch_company_profile",
        lambda ticker: {"finnhubIndustry": "Technology"},
    )

    result = finnhub_api.get_sector_allocation_map(["msft"], refresh_days=7, force_refresh=True)
    assert result["msft"] == "Data Processing"
    assert captured["ticker"] == "MSFT"
    assert captured["sector"] == "Data Processing"
    assert datetime.datetime.fromisoformat(captured["updated_at"]) >= now


def test_force_refresh_ignores_cached(monkeypatch):
    now = datetime.datetime.utcnow()
    cached_records = {
        "AAPL": {"sector": "Consumer Electronics", "updated_at": now.isoformat()},
    }
    calls = {"polygon": 0}

    monkeypatch.setattr(finnhub_api, "get_sector_records", lambda tickers: cached_records)
    monkeypatch.setattr(
        finnhub_api.polygon_api,
        "get_polygon_industry",
        lambda ticker: calls.update(polygon=calls["polygon"] + 1) or "Hardware",
    )
    monkeypatch.setattr(
        finnhub_api,
        "fetch_company_profile",
        lambda ticker: {"finnhubIndustry": "Technology"},
    )
    monkeypatch.setattr(finnhub_api, "upsert_stock_sector", lambda *args, **kwargs: None)

    result = finnhub_api.get_sector_allocation_map(["AAPL"], refresh_days=7, force_refresh=True)
    assert result["AAPL"] == "Hardware"
    assert calls["polygon"] == 1
