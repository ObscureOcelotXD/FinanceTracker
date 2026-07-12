# FinanceTracker

Personal stocks-focused finance tracker with Dash dashboards, Plaid linking, Umbrel node status, and local SQLite storage.

## Run the app

| OS | Command |
|---|---|
| **Mac / Linux** | `./start.sh` |
| **Windows** | `start.bat` |

From the project root, the script creates a `venv` if needed, installs `requirements.txt`, then starts:

- **Flask + Dash** at http://127.0.0.1:5000
- **Streamlit** on 8501 (quant backtest) and 8502 (SEC filings), if `STREAMLIT_AUTO_START` is enabled

**Mac/Linux:** first time run `chmod +x start.sh`. Copy `.env.example` → `.env` and add API keys (or use Infisical).

### Secrets: Infisical or `.env`

Secrets come from the **environment** only (`os.getenv`).

- **Infisical:** `infisical run -- ./start.sh` (Mac/Linux) or `infisical run -- venv\Scripts\python.exe main.py` (Windows). See [docs/INFISICAL.md](docs/INFISICAL.md).
- **Local `.env`:** copy `.env.example` → `.env` and fill in values.

## What you get

- **Stocks dashboard** – holdings, privacy mode, hide mutual funds / ETFs
- **Manage / Import / Covered Calls / Realized Gains** – Dash pages under `/dashboard/`
- **Plaid** – read-only bank & brokerage linking
- **Umbrel Corner** – Bitcoin node, Lightning, cold-storage wallet (Electrum)
- **Portfolio sync** – push/pull `portfolio.csv` to Umbrel Files over Tailscale
- **News digest + Groq insights** – optional AI relevance / home insights
- **Quant backtest + SEC filings** – Streamlit tools (Groq for summaries)

## Project layout

- **`main.py`** – Entry: DB init, Streamlit, Dash, Finnhub price refresh, Flask on 5000
- **`server.py`** / **`runServer.py`** – Flask app factory and gunicorn entry
- **`dashApp.py`** + **`dashPages/`** – Dash UI (stocks, manage, covered calls, import, realized)
- **`api/`** – Plaid, Finnhub, Polygon, Umbrel, BTC wallet, portfolio import/sync, quant risk, news
- **`services/`** – SQLite (`db_manager`), SEC filings Streamlit app
- **`quant/`** – Backtest helpers for Streamlit
- **`docs/`** – Infisical, portfolio sync, Plaid production kit + GitHub Pages legal site
- **`templates/`**, **`static/`** – Home page and assets
- **`scripts/`** – e.g. daily news digest runner
- **`tests/`** – Pytest suite

## Tests

```bash
# Mac/Linux
./test.sh

# Windows
venv\Scripts\python.exe -m pytest tests\ -v
```

## Optional: BTC wallet (Sparrow / Electrum)

Needs `bip_utils` → **coincurve**. Prefer Python 3.12/3.13, or on 3.14 install build tools and:

```bash
./pip.sh install bip_utils -c constraints-btc.txt
```

Without it, the rest of the app still runs; cold storage shows as not configured.

## Umbrel Lightning TLS

If you see `InsecureRequestWarning` from Lightning HTTPS:

- `UMBREL_LIGHTNING_CA_BUNDLE` = path to CA cert
- `UMBREL_LIGHTNING_VERIFY_SSL` = `true`

## Plaid (production)

Read-only personal finance: balances, transactions, investments — no payments or transfers. Prefer products **`transactions`** and **`investments`**.

See:

- [docs/PLAID_PRODUCTION_REQUEST.md](docs/PLAID_PRODUCTION_REQUEST.md)
- [docs/PLAID_PRODUCTION_CHECKLIST.md](docs/PLAID_PRODUCTION_CHECKLIST.md)
- Public pages under **`docs/`** for GitHub Pages (`/privacy`, `/terms`, `/support` also served by the app)

Configure `PLAID_*` in `.env`, add redirect URI `…/oauth/callback` in the Plaid dashboard, and set Data Transparency Messaging use cases if Link requires them.

## Portfolio sync (Umbrel Files)

Push/Pull from **Import CSV** writes `Home → Documents → Portfolio → portfolio.csv`. Needs `UMBREL_TAILSCALE_IP` + `UMBREL_PASSWORD`. Details: [docs/PORTFOLIO_SYNC.md](docs/PORTFOLIO_SYNC.md).

## SEC filings (Groq)

Fetch & Summarize uses **`GROQ_API_KEY`** to chunk and summarize filings into `sec_filing_summaries`.
