# finnhub_api.py
from flask import Blueprint
import os
import requests
import concurrent.futures
import datetime
from dotenv import load_dotenv
try:
    from . import polygon_api
except Exception:
    import polygon_api
from services.db_manager import (
    get_all_tickers,
    get_tickers_missing_prices,
    upsert_stock_price,
    get_last_update,
    set_last_update,
    get_sector_map,
    get_sector_records,
    upsert_stock_sector,
    get_stock_prices_df,
    get_app_setting,
    set_app_setting,
)

# Kept as a Blueprint name for historical imports; no HTTP routes remain.
finnhub_api = Blueprint("finnhub_api", __name__)

# Load .env so the key is available when this module is imported.
load_dotenv()

def _get_finnhub_api_key():
    key = os.getenv("FINNHUB_API_KEY")
    if key:
        return key.strip()
    return None

FINNHUB_QUOTE_URL = "https://finnhub.io/api/v1/quote"
FINNHUB_PROFILE_URL = "https://finnhub.io/api/v1/stock/profile2"

SECTOR_OVERRIDES = {
    "VTI": "Broad Market",
    "VTSAX": "Broad Market",
    "ITOT": "Broad Market",
    "SCHB": "Broad Market",
    "SWTSX": "Broad Market",
    "FSKAX": "Broad Market",
    "FZROX": "Broad Market",
    "VOO": "S&P 500",
    "IVV": "S&P 500",
    "SPY": "S&P 500",
    "FXAIX": "S&P 500",
    "VFIAX": "S&P 500",
    "SWPPX": "S&P 500",
    "VTSMX": "Total Stock Market",
    "VT": "Total World",
    "VXUS": "Total International",
    "FTIHX": "Total International",
    "VTIAX": "Total International",
    "IXUS": "Total International",
}


GENERIC_SECTORS = {
    "technology",
    "unknown",
    "",
    None,
}


def _is_generic_sector(value):
    if value is None:
        return True
    return str(value).strip().lower() in GENERIC_SECTORS


def fetch_finnhub_quote(ticker):
    """
    Calls Finnhub's /quote endpoint for a single ticker and returns a tuple (ticker, current_price).
    The Finnhub quote returns a JSON object with key "c" for the current price.
    """
    params = {
        "symbol": ticker,
        "token": _get_finnhub_api_key(),
    }
    response = requests.get(FINNHUB_QUOTE_URL, params=params)
    data = response.json()
    try:
        current_price = data.get("c")
        if current_price is None:
            raise ValueError("Missing 'c' value")
        return ticker, float(current_price)
    except (KeyError, ValueError) as e:
        print(f"Error fetching price for {ticker}: {e} - Response: {data}")
        return ticker, None

def fetch_stock_prices_batch(tickers):
    """
    Fetches Finnhub quotes for a list of tickers concurrently.
    Returns a dictionary mapping ticker -> current_price.
    """
    batch_prices = {}
    # Using a thread pool to perform requests concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # Submit a task for each ticker.
        future_to_ticker = {executor.submit(fetch_finnhub_quote, ticker): ticker for ticker in tickers}
        for future in concurrent.futures.as_completed(future_to_ticker):
            ticker, price = future.result()
            batch_prices[ticker] = price
    return batch_prices

def fetch_company_profile(ticker):
    params = {
        "symbol": ticker.upper(),
        "token": _get_finnhub_api_key(),
    }
    response = requests.get(FINNHUB_PROFILE_URL, params=params, timeout=15)
    if response.status_code != 200:
        print(f"[Finnhub] {ticker} HTTP {response.status_code}: {response.text[:200]}")
        return {}
    data = response.json()
    print(f"[Finnhub] {ticker} profile fetched.")
    return data


def validate_equity_symbol(symbol: str):
    """
    Check whether a ticker looks like a real, active equity Finnhub recognizes.

    Returns (True, None) if valid or if validation is skipped (no API key).
    Returns (False, user_message) if the symbol is not recognized.

    This uses the company profile endpoint (not a full exchange listing). It is
    suitable for rejecting obvious typos and fake symbols without maintaining a
    local registry; rate limits apply per check.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return False, "Ticker cannot be empty."
    key = _get_finnhub_api_key()
    if not key:
        return True, None
    profile = fetch_company_profile(sym)
    if not profile:
        return False, f"{sym} is not a recognized stock ticker."
    if profile.get("ticker") or profile.get("name"):
        return True, None
    return False, f"{sym} is not a recognized stock ticker."

def get_sector_allocation_map(tickers, refresh_days: int = 7, force_refresh: bool = False):
    cached_records = get_sector_records(tickers)
    cached = {t: rec.get("sector") for t, rec in cached_records.items()}
    stale_cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=refresh_days)
    missing = []
    if force_refresh:
        print(f"[Sector] Force refresh enabled for {len(tickers)} tickers.")
    for t in tickers:
        t_upper = t.upper()
        if t_upper in SECTOR_OVERRIDES:
            sector = SECTOR_OVERRIDES[t_upper]
            upsert_stock_sector(t_upper, sector, datetime.datetime.now(datetime.timezone.utc).isoformat())
            cached[t] = sector
            continue
        if force_refresh:
            missing.append(t)
            continue
        rec = cached_records.get(t)
        if not rec or not rec.get("sector"):
            missing.append(t)
            continue
        try:
            updated_at = datetime.datetime.fromisoformat(rec.get("updated_at"))
            if _is_generic_sector(rec.get("sector")):
                if force_refresh or updated_at < stale_cutoff:
                    missing.append(t)
                continue
            if updated_at < stale_cutoff:
                missing.append(t)
        except Exception:
            missing.append(t)
    if not missing:
        print("[Sector] No sector refresh needed.")
    for ticker in missing:
        try:
            ticker_upper = ticker.upper()
            if ticker_upper in SECTOR_OVERRIDES:
                sector = SECTOR_OVERRIDES[ticker_upper]
                upsert_stock_sector(ticker_upper, sector, datetime.datetime.now(datetime.timezone.utc).isoformat())
                cached[ticker] = sector
                continue
            polygon_sector = polygon_api.get_polygon_industry(ticker_upper)
            used_polygon = False
            if polygon_sector and not _is_generic_sector(polygon_sector):
                sector = polygon_sector
                used_polygon = True
                print(f"[Sector] {ticker_upper} -> Polygon: {sector}")
            else:
                data = fetch_company_profile(ticker_upper)
                sector = (
                    data.get("finnhubIndustry")
                    or data.get("industry")
                    or data.get("gicsSubIndustry")
                    or data.get("gics_sub_industry")
                    or data.get("sector")
                    or "Unknown"
                )
                print(f"[Sector] {ticker_upper} -> Finnhub: {sector}")
            upsert_stock_sector(ticker_upper, sector, datetime.datetime.now(datetime.timezone.utc).isoformat())
            cached[ticker] = sector
        except Exception as exc:
            print(f"[Finnhub] Sector fetch failed for {ticker}: {exc}")
            cached[ticker] = "Unknown"
    return cached

def update_stock_prices(forceUpdate: bool = False):
    tickers = get_all_tickers()  # distinct held tickers
    today = datetime.date.today().isoformat()

    last_run = get_last_update()
    missing = get_tickers_missing_prices(tickers)
    if last_run == today and not forceUpdate:
        if not missing:
            print("[Finnhub] Update already performed today. Skipping update.")
            backfill_held_price_history()
            return
        # New holdings imported after today's run still need quotes.
        print(
            f"[Finnhub] Already ran today, but {len(missing)} ticker(s) lack prices — fetching those."
        )
        tickers = missing

    if not tickers:
        print("[Finnhub] No tickers to update.")
        backfill_held_price_history()
        return

    # Fetch prices concurrently using Finnhub
    print(f"[Finnhub] Fetching prices for {len(tickers)} tickers on {today}...")
    batch_prices = fetch_stock_prices_batch(tickers)

    for ticker in tickers:
        price = batch_prices.get(ticker)
        if price is not None:
            upsert_stock_price(ticker, today, price)
            print(f"[Finnhub] Upserted price for {ticker}: {price}")
        else:
            print(f"[Finnhub] Price for {ticker} not available.")
    set_last_update(today)
    backfill_held_price_history()


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_truthy(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def _distinct_price_dates(lookback_days: int) -> int:
    df = get_stock_prices_df()
    if df is None or df.empty:
        return 0
    cutoff = (
        datetime.date.today() - datetime.timedelta(days=max(lookback_days, 1))
    ).isoformat()
    dates = df["date"].astype(str).str[:10]
    return int(dates[dates >= cutoff].nunique())


def backfill_held_price_history(
    lookback_days: int | None = None,
    *,
    force: bool = False,
) -> dict:
    """
    Fill missing daily closes for held tickers so quant metrics have a series.

    Uses Yahoo chart data (same source as SPY beta). Automatic runs happen at most
    once per day unless coverage is still thin. Disable auto with
    ``PRICE_HISTORY_BACKFILL=0``. Pass ``force=True`` (admin button) to run anytime.
    """
    lookback = (
        lookback_days
        if lookback_days is not None
        else _env_int("PRICE_HISTORY_BACKFILL_DAYS", 60)
    )
    if lookback <= 0:
        return {
            "upserted": 0,
            "skipped": True,
            "reason": "lookback_days must be > 0",
            "lookback_days": lookback,
            "distinct_dates": 0,
            "tickers": 0,
        }

    auto_enabled = _env_truthy("PRICE_HISTORY_BACKFILL", default=True)
    if not force and not auto_enabled:
        return {
            "upserted": 0,
            "skipped": True,
            "reason": "PRICE_HISTORY_BACKFILL disabled",
            "lookback_days": lookback,
            "distinct_dates": _distinct_price_dates(lookback),
            "tickers": 0,
        }

    min_dates = _env_int("PRICE_HISTORY_MIN_DATES", 15)
    today = datetime.date.today().isoformat()
    env_force = _env_truthy("PRICE_HISTORY_BACKFILL_FORCE", default=False)
    force = bool(force or env_force)
    last = (get_app_setting("last_price_history_backfill") or "").strip()
    distinct = _distinct_price_dates(lookback)

    if not force:
        if distinct >= min_dates:
            if last != today:
                set_app_setting("last_price_history_backfill", today)
            return {
                "upserted": 0,
                "skipped": True,
                "reason": f"already have {distinct} distinct date(s) (≥{min_dates})",
                "lookback_days": lookback,
                "distinct_dates": distinct,
                "tickers": 0,
            }
        if last == today:
            return {
                "upserted": 0,
                "skipped": True,
                "reason": "already ran today",
                "lookback_days": lookback,
                "distinct_dates": distinct,
                "tickers": 0,
            }

    tickers = [str(t).upper().strip() for t in (get_all_tickers() or []) if str(t).strip()]
    if not tickers:
        set_app_setting("last_price_history_backfill", today)
        return {
            "upserted": 0,
            "skipped": True,
            "reason": "no held tickers",
            "lookback_days": lookback,
            "distinct_dates": distinct,
            "tickers": 0,
        }

    from api.quant_risk import ensure_benchmark_history, fetch_yahoo_history

    end = datetime.datetime.now(datetime.timezone.utc)
    start = end - datetime.timedelta(days=lookback)
    upserted = 0

    try:
        ensure_benchmark_history("SPY", start, end + datetime.timedelta(days=1))
    except Exception as exc:
        print(f"[Prices] SPY history backfill failed: {exc}")

    print(
        f"[Prices] Backfilling up to {lookback}d of daily closes for "
        f"{len(tickers)} ticker(s) (have {distinct} distinct date(s), want ≥{min_dates}"
        f"{', forced' if force else ''})…"
    )
    for ticker in tickers:
        try:
            candles, error = fetch_yahoo_history(ticker, start, end)
            if error or not candles:
                print(f"[Prices] No Yahoo history for {ticker}")
                continue
            for ts, close in candles:
                if close is None:
                    continue
                try:
                    px = float(close)
                except (TypeError, ValueError):
                    continue
                if px <= 0:
                    continue
                date_str = datetime.datetime.fromtimestamp(
                    ts, tz=datetime.timezone.utc
                ).date().isoformat()
                upsert_stock_price(ticker, date_str, px)
                upserted += 1
        except Exception as exc:
            print(f"[Prices] History backfill failed for {ticker}: {exc}")

    set_app_setting("last_price_history_backfill", today)
    distinct_after = _distinct_price_dates(lookback)
    if upserted:
        print(f"[Prices] Backfilled {upserted} historical close row(s).")
    else:
        print("[Prices] History backfill finished with no new rows.")
    return {
        "upserted": upserted,
        "skipped": False,
        "reason": None,
        "lookback_days": lookback,
        "distinct_dates": distinct_after,
        "tickers": len(tickers),
    }
