# Portfolio sync (Umbrel Files over Tailscale)

Push/Pull on **Import CSV** uploads or downloads `portfolio.csv` through Umbrel’s **built-in Files API** (dashboard on port 80), using your Umbrel password.

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
```

Restart FinanceTracker → Import CSV → Push.

Legacy `PORTFOLIO_FB_PATH=/Documents/...` is auto-mapped to `/Home/Documents/...`.

## Security

Keep Umbrel on Tailscale/LAN. Store `UMBREL_PASSWORD` in Infisical/`.env`, not in git.
