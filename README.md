# FinanceTracker

Personal finance tracking app with dashboards, API integrations, and local storage.

## Tests

Run all tests:

```bash
python -m pytest
```

Included tests:

- `tests/test_btc_wallet_api.py::test_scan_uses_scripthash_methods`  
  Mocks the Electrum client and verifies `_scan_addresses` uses
  `blockchain.scripthash.get_history`.
- `tests/test_db_manager.py::test_realized_gain_insert_and_compute`  
  Inserts a realized gain and validates calculated gain and percentage.
- `tests/test_db_manager.py::test_plaid_holdings_upsert_and_query`  
  Seeds Plaid item/account/price data and verifies holdings aggregation.
- `tests/test_db_manager.py::test_wipe_all_data_clears_tables`  
  Inserts data, wipes all tables, and confirms tables are empty.
- `tests/test_finnhub_sector_cache.py::test_polygon_preferred_over_finnhub`  
  Confirms Polygon industry data is preferred over Finnhub.
- `tests/test_finnhub_sector_cache.py::test_force_refresh_ignores_cached`  
  Confirms force refresh ignores cached sector values.
