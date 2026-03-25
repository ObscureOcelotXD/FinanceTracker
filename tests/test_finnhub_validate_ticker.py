import api.finnhub_api as finnhub_api


def test_validate_empty_ticker():
    ok, msg = finnhub_api.validate_equity_symbol("")
    assert ok is False
    assert "empty" in (msg or "").lower()


def test_validate_skipped_without_api_key(monkeypatch):
    monkeypatch.setattr(finnhub_api, "_get_finnhub_api_key", lambda: None)
    ok, msg = finnhub_api.validate_equity_symbol("FAKEZZ")
    assert ok is True
    assert msg is None


def test_validate_accepts_known_profile(monkeypatch):
    monkeypatch.setattr(finnhub_api, "_get_finnhub_api_key", lambda: "test-key")
    monkeypatch.setattr(
        finnhub_api,
        "fetch_company_profile",
        lambda sym: {"ticker": sym, "name": "Example Corp"},
    )
    ok, msg = finnhub_api.validate_equity_symbol("AAPL")
    assert ok is True
    assert msg is None


def test_validate_rejects_empty_profile(monkeypatch):
    monkeypatch.setattr(finnhub_api, "_get_finnhub_api_key", lambda: "test-key")
    monkeypatch.setattr(finnhub_api, "fetch_company_profile", lambda sym: {})
    ok, msg = finnhub_api.validate_equity_symbol("NOTREAL")
    assert ok is False
    assert msg and "NOTREAL" in msg
