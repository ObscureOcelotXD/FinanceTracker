import api.btc_wallet_api as btc_wallet_api


def test_scan_uses_scripthash_methods(monkeypatch):
    calls = []

    def fake_request(method, params):
        calls.append((method, params))
        if method == "blockchain.scripthash.get_history":
            if params[0] == "hash-0-0":
                return [{"height": 1, "tx_hash": "abc"}]
            return []
        raise RuntimeError("Unexpected method")

    class DummyClient:
        def request(self, method, params=None):
            return fake_request(method, params)

    monkeypatch.setattr(btc_wallet_api, "_derive_address", lambda xpub, chain, index, t: f"addr-{chain}-{index}")
    monkeypatch.setattr(btc_wallet_api, "_derive_scripthash", lambda xpub, chain, index, t: f"hash-{chain}-{index}")

    used_addresses, used_scripthashes, scanned = btc_wallet_api._scan_addresses(
        DummyClient(), "xpub", gap_limit=2, address_type="p2wpkh"
    )

    assert ("blockchain.scripthash.get_history", ["hash-0-0"]) in calls
    assert used_addresses == ["addr-0-0"]
    assert used_scripthashes == ["hash-0-0"]
    assert scanned >= 1
