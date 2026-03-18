# FinanceTracker

Personal finance tracking app with dashboards, API integrations, and local storage.

## Run the app

The app runs on **macOS, Windows, and Linux**. Use the script for your OS:

| OS      | Command     |
|---------|-------------|
| **Mac / Linux** | `./start.sh` |
| **Windows**     | `start.bat`  |

From the project root, the script creates a `venv` if needed, installs dependencies from `requirements.txt`, then starts:

- **Flask + Dash** at http://127.0.0.1:5000 (main site, Plaid link, stocks, etc.)
- **Streamlit** apps on 8501 (backtest) and 8502 (SEC filings), if `STREAMLIT_AUTO_START` is enabled in `.env`.

**Mac/Linux:** first time run `chmod +x start.sh`. Optional: copy `.env.example` to `.env` and add your API keys.

**Install packages (venv):**

- **Mac/Linux:** `./pip.sh install <package>` or `./pip.sh install -r requirements.txt`
- **Windows:** `venv\Scripts\python.exe -m pip install <package>` (or activate venv and use `pip`)

### Secrets: Infisical (CLI) or .env

Secrets are loaded from the **environment** only (`os.getenv`). No Infisical SDK in the app.

- **With Infisical:** use the CLI to inject secrets at run time. **Mac/Linux:** `infisical run -- ./start.sh` or `make run-infisical`. **Windows:** `infisical run -- venv\Scripts\python.exe main.py`. One-time setup: `infisical login`, then `infisical init` in the repo root. See **[docs/INFISICAL.md](docs/INFISICAL.md)**.
- **Without Infisical:** copy `.env.example` to `.env`, fill in values, and run `./start.sh` (Mac/Linux) or `start.bat` (Windows). `.env` is optional when using Infisical.

## Project layout

- **`main.py`** – Entry point: DB init, optional Streamlit (backtest, filings), Dash, then Flask on 5000.
- **`runServer.py`** – Builds the Flask app via `server.create_flask_app()` (used by `main.py` and for gunicorn).
- **`server.py`** – Flask app factory: routes (/, /quant, /filings, /webhook, /oauth/callback, /admin/*, /quant/risk_summary), blueprint registration. Single app; no duplicate global app.
- **`db_manager.py`** – SQLite schema and CRUD (stocks, accounts, Plaid items, transactions, holdings, SEC summaries, etc.).
- **`dashApp.py`** – Dash app mounted at `/dashboard/`; **`dash_callbacks.py`** – Dash callbacks.
- **`dashPages/`** – Dash pages (stocks, accounts, realized gains, manage).
- **`api/`** – Flask blueprints and helpers: Plaid, Alpha Vantage, Finnhub, CoinGecko, Umbrel, BTC wallet, etc. **`api/quant_risk.py`** – Quant risk summary logic (used by `/quant/risk_summary`).
- **`docs/INFISICAL.md`** – Infisical CLI setup and secret names (no SDK; use `infisical run -- ./start.sh` or `make run-infisical`).
- **`templates/`**, **`static/`** – Jinja HTML and static assets.
- **`handlers/`**, **`ui_main_window.py`**, **`csv_utils.py`** – Desktop (PySide6/Qt) UI; separate from the web app.
- **`scripts/`** – Backfill and one-off scripts.
- **`tests/`** – Pytest tests (db_manager, btc_wallet, finnhub_sector_cache, server routes, quant_risk).

## Tests

Requires pytest in the venv. From project root:

- **Mac/Linux:** `./test.sh` (or `./test.sh -v` for verbose).
- **Windows:** `venv\Scripts\python.exe -m pytest tests\ -v`

Install pytest if needed: **Mac/Linux** `./pip.sh install pytest`; **Windows** `venv\Scripts\python.exe -m pip install pytest`.

Included tests:

- **test_db_manager.py** – Realized gains, Plaid holdings upsert/query, wipe_all.
- **test_btc_wallet_api.py** – Electrum scripthash scan behavior.
- **test_finnhub_sector_cache.py** – Polygon vs Finnhub, force refresh.
- **test_server_routes.py** – Smoke: GET /, /quant, /filings, /quant/risk_summary return 200 and expected JSON shape.
- **test_quant_risk.py** – compute_risk_summary() returns dict with expected keys; empty DB returns nulls.

## Optional: BTC wallet (Sparrow / Electrum) and the coincurve issue

The BTC wallet feature needs `bip_utils`, which depends on **coincurve**. On Python 3.14 (and sometimes 3.13), coincurve often has no prebuilt wheel, so pip tries to **build from source**. That can fail for two reasons:

1. **coincurve 21.x** has a packaging bug (LICENSE/cffi) and fails during metadata build.
2. **Building from source** needs system tools: **pkg-config**, **ninja**, and (for some setups) **CMake**. On macOS: `brew install pkg-config ninja`.

So the app runs **without** the BTC wallet by default (no `bip_utils` in `requirements.txt`). To get the BTC wallet working you can:

**Option A – Use Python 3.12 or 3.13 for the venv**  
Prebuilt wheels for coincurve are more likely. Recreate the venv with that Python:

```bash
rm -rf venv
python3.12 -m venv venv   # or python3.13
./start.sh
./pip.sh install bip_utils
```

**Option B – Stay on Python 3.14 and install build tools**  
Then install coincurve 20.x and bip_utils **with a constraint** so pip doesn’t upgrade to coincurve 21.x:

```bash
brew install pkg-config ninja cmake
./pip.sh install bip_utils -c constraints-btc.txt
```

(`constraints-btc.txt` pins `coincurve>=20,<21`. If you install without it, pip may try coincurve 21 and fail.)

Restart the app after installing; the BTC wallet blueprint will register if `bip_utils` is available.

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

## Plaid (production / personal accounts)

To use **live** bank and brokerage data (after Plaid has approved your app):

This app’s Plaid use case is **read-only personal financial management**:

- View balances, transaction history, investment holdings, cash positions, and related analytics
- No payments, transfers, ACH verification, trading, buying, selling, or movement of funds
- Keep the requested Plaid scope to **`transactions`** and **`investments`** unless the product later adds a real funding workflow

1. **Copy env and set production credentials**
   - Copy `.env.example` to `.env` if you haven’t already.
   - In `.env`, set:
     - `PLAID_CLIENT_ID` and `PLAID_SECRET` to your **production** keys from [Plaid Dashboard](https://dashboard.plaid.com/) (not sandbox).
     - `PLAID_ENV=production`.

2. **Redirect URI (required for OAuth institutions)**
   - In Plaid Dashboard → **Keys** → **Redirect URIs** for the **Production** environment, add:
     - Local: `http://127.0.0.1:5000/oauth/callback`
     - If you deploy later: your app’s base URL + `/oauth/callback` (e.g. `https://yourdomain.com/oauth/callback`).

3. **Run the app and connect**
   - Start the app (e.g. `python main.py`), open the home page, and click **Connect Plaid**.
   - Link will use production; connect your real accounts. After linking, the app pulls read-only account, transaction, and investment holdings data into the local DB for dashboards and analytics.

4. **Optional**
   - Leave `PLAID_WEBHOOK` unset or set it to `http://127.0.0.1:5000/webhook` if you want to receive product/status webhooks (optional for local use).

### Fix: INVALID_LINK_CUSTOMIZATION / Data Transparency Messaging

If Link shows **INVALID_LINK_CUSTOMIZATION** and *"At least one Data Transparency Messaging use case is required"*, Plaid requires you to configure **Data Transparency Messaging (DTM)** in the dashboard (required for US/Canada as of 2024):

1. Go to [Plaid Dashboard → Link → Data Transparency](https://dashboard.plaid.com/link/data-transparency-v5) (or Link Customization).
2. Open the **Data Transparency** section and **select at least one use case** (e.g. "Track and manage your finances", "Invest your money").
3. Click **Publish**. Link will then work; no code change required. If you created a **named** customization and want to use it, set `PLAID_LINK_CUSTOMIZATION_NAME=<name>` in `.env`.

### OAuth vs credential-based connections

- **OAuth:** Many US institutions (including **SoFi, Coinbase**, and other large banks) use OAuth. You must set `PLAID_REDIRECT_URI` and add that URI in Plaid Dashboard → Keys → Redirect URIs. The app’s `/oauth/callback` route sends users back after they sign in at the institution.
- **Without OAuth:** Some smaller banks and credit unions still use username/password (credential-based) in Link; those work without a redirect URI. Which institutions use OAuth is listed in [Plaid Dashboard → Compliance → US OAuth institutions](https://dashboard.plaid.com/settings/compliance/us-oauth-institutions) (or the Plaid docs). You need OAuth configured to connect to SoFi, Coinbase, and most major US banks.

### Plaid production approval kit

If you are preparing a new production request, the repo now includes a narrow, PFM-focused submission package:

- **`docs/PLAID_PRODUCTION_REQUEST.md`** – exact wording for the production request form
- **`docs/PLAID_PRODUCTION_CHECKLIST.md`** – app profile, DTM, screenshots, and security questionnaire prep
- **`/privacy`**, **`/terms`**, **`/support`** – approval-facing pages you can show Plaid reviewers

For this app, keep the Plaid request scoped to **`transactions`** and **`investments`** and describe the product as **read-only** unless you later add a real account/routing-number workflow that needs `auth`.

## SEC Filings Summaries (Flow)

When you click **Fetch & Summarize** in the SEC Filings page, the app:

- Reads inputs (tickers, types, date, cache options)
- Initializes the database and prunes old filings
- Downloads the newest filing (if not already cached locally)
- Extracts plain text from the filing
- Splits the text into chunks
- Summarizes with Groq (primary), then Gemini (fallback)
- Saves the summary and metadata in `sec_filing_summaries`
