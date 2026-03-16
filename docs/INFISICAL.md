# Infisical (CLI-only secrets)

FinanceTracker can load secrets from [Infisical](https://infisical.com) using **only the Infisical CLI**. The app does not import any Infisical SDK; it reads from the environment as usual (`os.getenv`, etc.). When you run the app under `infisical run -- <command>`, the CLI fetches secrets for the linked project/environment and injects them into the process. No `.env` file is required.

## What you need

- An Infisical Cloud account (sign up at [infisical.com](https://infisical.com)).
- The [Infisical CLI](https://infisical.com/docs/cli/overview) installed (`brew install infisical` or see their docs).
- The repo linked to a project: `infisical login` then `infisical init` in the project root (creates `.infisical.json`; safe to commit).

## Setup (one-time)

1. **Sign up and create a project**  
   At [app.infisical.com](https://app.infisical.com), create a project and at least one environment (e.g. `dev`).

2. **Add secrets in the dashboard**  
   In your project → environment, add the following **secret names** with the values you use locally. Names must match exactly (same as in `.env.example`):

   **Plaid**
   - `PLAID_CLIENT_ID`
   - `PLAID_SECRET`
   - `PLAID_ENV` (e.g. `sandbox` or `production`)
   - `PLAID_REDIRECT_URI` (e.g. `http://127.0.0.1:5000/oauth/callback`)
   - Optional: `PLAID_SANDBOX_SECRET`, `PLAID_SANDBOX_CLIENT_ID`, `PLAID_WEBHOOK`, `PLAID_PRODUCTS`, `PLAID_COUNTRY_CODES`

   **BTC wallet (optional)**
   - `BTC_WALLET_XPUB`, `BTC_WALLET_ADDRESS_TYPE`, `BTC_WALLET_GAP_LIMIT`
   - `BTC_ELECTRUM_HOST`, `BTC_ELECTRUM_PORT`, `BTC_ELECTRUM_SSL`, `BTC_WALLET_CACHE_TTL`

   **Streamlit**
   - `STREAMLIT_AUTO_START` (e.g. `true`)

   **SEC filings / AI**
   - `GEMINI_API_KEY`, `GEMINI_MODEL`
   - Optional: `GROQ_API_KEY`, `GROQ_MODEL`, `HF_API_KEY`, `HF_MODEL`
   - `SEC_EDGAR_COMPANY`, `SEC_EDGAR_EMAIL`, `SEC_EDGAR_USER_AGENT`
   - `SEC_FILINGS_RETENTION_DAYS`

   **Other APIs (if used)**
   - `ALPHA_VANTAGE_API_KEY` or `ALPHAVANTAGE_API_KEY`
   - `FINNHUB_API_KEY`
   - `POLYGON_API_KEY`
   - Umbrel: `UMBREL_LIGHTNING_MACAROON`, `UMBREL_RPC_PASS`, and other `UMBREL_*` as needed. You can keep these in `.env` only (do not add to Infisical) if you prefer; `load_dotenv()` will still load them when you run under `infisical run`.

3. **Install and link the CLI**
   ```bash
   brew install infisical
   infisical login
   cd /path/to/FinanceTracker
   infisical init
   ```
   `infisical init` creates `.infisical.json` in the repo root (project/environment IDs; safe to commit).

## Running the app with Infisical

Secrets are injected only when you run commands under the CLI. Use one of:

```bash
# Convenience (recommended)
make run-infisical

# Or explicitly
infisical run -- ./start.sh

# Specific environment (e.g. prod)
infisical run --env=prod -- ./start.sh
```

The child process (Python, start.sh, etc.) receives all Infisical secrets as environment variables. The app still calls `load_dotenv()`; if you don’t have a `.env` file or a variable is already set by Infisical, the injected value is used.

## Running without Infisical

You can still use a `.env` file and run the app normally:

```bash
./start.sh
# or
make run
```

Copy `.env.example` to `.env`, fill in values, and run. No Infisical CLI required.

## Docker Compose

This project does not ship Docker Compose. If you add it later:

- Use environment variable substitution in the compose file (e.g. `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}`) with **no** default values for secrets (`${VAR}` not `${VAR:-default}`).
- Run Compose from a process that has the env injected: `infisical run -- docker compose up`.

## Summary

| Goal                         | Command / action                          |
|-----------------------------|-------------------------------------------|
| Run with Infisical (no .env)| `make run-infisical` or `infisical run -- ./start.sh` |
| Run with .env only          | `./start.sh` or `make run`                |
| One-off command with secrets| `infisical run -- pytest` or `infisical run -- ./pip.sh install ...` |
| Link repo to Infisical      | `infisical login` then `infisical init`   |

Secret names the app expects are listed above and in `.env.example`.
