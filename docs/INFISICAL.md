# Infisical (CLI-only secrets)

FinanceTracker loads secrets from the **environment** only (`os.getenv`). Use the [Infisical CLI](https://infisical.com/docs/cli/overview) to inject them at run time — no Infisical SDK in the app.

## Setup (one-time)

1. Create a project at [app.infisical.com](https://app.infisical.com).
2. Add secrets (names must match `.env.example`):

   **Plaid**
   - `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENV`, `PLAID_REDIRECT_URI`
   - Optional: `PLAID_WEBHOOK`, `PLAID_PRODUCTS`, `PLAID_COUNTRY_CODES`, sandbox keys

   **Market data**
   - `FINNHUB_API_KEY` (stock prices / sectors)
   - `POLYGON_API_KEY` (sector / ETF fallback)

   **AI (Groq)**
   - `GROQ_API_KEY`, optional `GROQ_MODEL` (SEC filings, news AI, home insights)

   **SEC EDGAR**
   - `SEC_EDGAR_COMPANY`, `SEC_EDGAR_EMAIL`, `SEC_EDGAR_USER_AGENT`
   - `SEC_FILINGS_RETENTION_DAYS`

   **Umbrel / BTC (optional)**
   - `UMBREL_TAILSCALE_IP`, `UMBREL_PASSWORD` (portfolio Files sync)
   - `UMBREL_RPC_*`, `UMBREL_LIGHTNING_*`
   - `BTC_WALLET_XPUB`, `BTC_ELECTRUM_HOST`, `BTC_ELECTRUM_PORT`, `BTC_ELECTRUM_SSL`, …

   **App**
   - `STREAMLIT_AUTO_START` (e.g. `true`)

   You can keep Umbrel passwords in `.env` only if you prefer; `load_dotenv()` still applies under `infisical run`.

3. Link the repo:
   ```bash
   brew install infisical   # or see Infisical docs
   infisical login
   cd /path/to/FinanceTracker
   infisical init
   ```

## Run

```bash
make run-infisical
# or
infisical run -- ./start.sh
# Windows:
infisical run -- venv\Scripts\python.exe main.py
```

Without Infisical: copy `.env.example` → `.env` and run `./start.sh` / `start.bat`.

## Summary

| Goal | Action |
|---|---|
| Run with Infisical | `make run-infisical` or `infisical run -- ./start.sh` |
| Run with `.env` only | `./start.sh` / `start.bat` |
| One-off with secrets | `infisical run -- pytest` |
| Link repo | `infisical login` then `infisical init` |
