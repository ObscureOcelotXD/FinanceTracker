# Portfolio sync (Umbrel Files over Tailscale)

Push/Pull on **Import CSV**:

1. **Upload** your CSV into FinanceTracker (updates the local DB).  
2. **Push to Umbrel** exports that DB to Umbrel’s `portfolio.csv`.  

Push does **not** send your Numbers file straight to Umbrel — upload first, then Push.

## Where to see the file on Umbrel

After a successful Push, open either:

1. **Umbrel home screen → Files** (built-in), or  
2. **File Browser** app  

Then go to:

**Home → Documents → Portfolio → `portfolio.csv`**

Full API path: `/Home/Documents/Portfolio/portfolio.csv`

Refresh the folder if it was already open.

## Why not File Browser’s `:7421` API?

File Browser is behind Umbrel’s app-proxy. Dashboard login cookies often get **401** on that port. The built-in Files API accepts the same dashboard password via a Bearer token and writes into the same Documents tree you browse in the UI.

## Setup

```bash
UMBREL_TAILSCALE_IP=100.x.x.x          # same host as BTC
UMBREL_PASSWORD=your_umbrel_password   # Umbrel home-screen password

# Defaults:
# PORTFOLIO_UMBREL_PATH=/Home/Documents/Portfolio
# PORTFOLIO_SYNC_FILENAME=portfolio.csv

# If Umbrel 2FA is on:
# UMBREL_TOTP=123456

# Optional: if the Tailscale IP alone doesn't open the dashboard in a browser,
# set the exact URL you use (LAN, MagicDNS, or HTTPS):
# UMBREL_DASHBOARD_URL=http://umbrel.local
# UMBREL_DASHBOARD_URL=https://umbrel.your-tailnet.ts.net
```

Restart FinanceTracker → Import CSV → Push.

**Connectivity:** Pull/Push talks to the Umbrel **dashboard on port 80** (`/trpc/user.login`), not Bitcoin RPC (`:8332`). If you see a connect timeout, Tailscale is usually disconnected or `UMBREL_TAILSCALE_IP` is stale — open the same host in a browser / `curl -m 5 http://<host>/` first.

Legacy `PORTFOLIO_FB_PATH=/Documents/...` is auto-mapped to `/Home/Documents/...`.

## Security

Keep Umbrel on Tailscale/LAN. Store `UMBREL_PASSWORD` in Infisical/`.env`, not in git.
