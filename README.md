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

## ETF Sector Sources

To decompose ETF/index funds into sector weights, use the Admin "ETF Source
Registry" on the home page. The app auto-detects provider URLs (Schwab first,
then Yahoo) and lets you override the URL/type manually. Sector weights cache
weekly and fall back to Polygon if no provider data is available.

## Umbrel Lightning TLS

If you see `InsecureRequestWarning` from the Lightning endpoint, it means HTTPS
cert verification is disabled (common with self-signed certs on local nodes).
You can keep it disabled for local-only use, or supply a CA bundle and enable
verification later:

- `UMBREL_LIGHTNING_CA_BUNDLE` = path to your CA cert file
- `UMBREL_LIGHTNING_VERIFY_SSL` = `true`

## SEC Filings Summaries (Flow)

When you click **Fetch & Summarize** in the SEC Filings page, the app:

- Reads inputs (tickers, types, date, cache options)
- Initializes the database and prunes old filings
- Downloads the newest filing (if not already cached locally)
- Extracts plain text from the filing
- Splits the text into chunks
- Summarizes with Groq (primary), then Gemini (fallback)
- Saves the summary and metadata in `sec_filing_summaries`
