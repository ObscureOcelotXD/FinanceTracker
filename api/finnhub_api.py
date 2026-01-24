# finnhub_api.py
from flask import Blueprint, jsonify, request
import os
import requests
import concurrent.futures
import datetime
from dotenv import load_dotenv
try:
    from . import polygon_api
except Exception:
    import polygon_api
try:
    # When running from the project root.
    from db_manager import (
        get_all_tickers,
        upsert_stock_price,
        get_last_update,
        set_last_update,
        get_sector_map,
        get_sector_records,
        upsert_stock_sector,
    )
except ModuleNotFoundError:
    # When the package is imported as a module (e.g., api.finnhub_api).
    from ..db_manager import (
        get_all_tickers,
        upsert_stock_price,
        get_last_update,
        set_last_update,
        get_sector_map,
        get_sector_records,
        upsert_stock_sector,
    )

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

def get_stock_quote(symbol):
    url = FINNHUB_QUOTE_URL
    params = {"symbol": symbol, "token": _get_finnhub_api_key()}
    response = requests.get(url, params=params)
    print("Request URL:", response.request.url)
    data = response.json()
    print("Finnhub response:", data)
    return data

@finnhub_api.route("/finnhub", methods=["GET"])
def finnhub_quote():
    symbol = "SPY"  # You can later make this dynamic
    data = get_stock_quote(symbol)

    # Finnhub returns a JSON like: { "c": 261.74, "h": 263.31, "l": 260.68, "o": 261.07, "pc": 259.45, "t": 1582641000 }
    if "c" in data:
        return jsonify({"symbol": symbol, "price": data["c"]})
    else:
        return jsonify({"error": "Data not found"}), 500

# def get_crypto_quote(symbol):
#     """Call Finnhub's crypto quote endpoint.
#        Expect a full symbol in the format 'BINANCE:ETHUSDT'. 
#        We can build this from a simple user input like 'ETH'. """
#     url = "https://finnhub.io/api/v1/crypto/quote"
#     params = {
#         "symbol": symbol,
#         "token": FINNHUB_API_KEY
#     }
#     response = requests.get(url, params=params)
#     data = response.json()
#     return data

@finnhub_api.route("/stock", methods=["POST"])
def stock_quote():
    data = request.get_json(force=True)
    ticker = data.get("ticker")
    if not ticker:
        return jsonify({"error": "No ticker provided"}), 400

    quote = get_stock_quote(ticker)
    # Finnhub returns a JSON with key "c" as the current price for stocks
    if "c" in quote and quote["c"]:
        return jsonify({"ticker": ticker.upper(), "price": quote["c"]})
    else:
        return jsonify({"error": "Data not found or API error"}), 500



# @finnhub_api.route('/finnCrypto', methods=['POST'])
# def crypto_quote():
#     data = request.get_json(force=True)
#     ticker = data.get("ticker")
#     if not ticker:
#         return jsonify({"error": "No ticker provided"}), 400

#     # For crypto, we assume that if the user enters a simple symbol like "ETH",
#     # we will default to the BINANCE exchange and use the trading pair ending in USDT.
#     symbol = f"BINANCE:{ticker.upper()}USDT"
#     quote = get_crypto_quote(symbol)
#     # Finnhub returns a JSON with key "c" as the current price for crypto quotes as well
#     if "c" in quote and quote["c"]:
#         return jsonify({"ticker": symbol, "price": quote["c"]})
#     else:
#         return jsonify({"error": "Data not found or API error"}), 500



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

def get_sector_allocation_map(tickers, refresh_days: int = 7, force_refresh: bool = False):
    cached_records = get_sector_records(tickers)
    cached = {t: rec.get("sector") for t, rec in cached_records.items()}
    stale_cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=refresh_days)
    missing = []
    if force_refresh:
        print(f"[Sector] Force refresh enabled for {len(tickers)} tickers.")
    for t in tickers:
        t_upper = t.upper()
        if t_upper in SECTOR_OVERRIDES:
            sector = SECTOR_OVERRIDES[t_upper]
            upsert_stock_sector(t_upper, sector, datetime.datetime.utcnow().isoformat())
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
                upsert_stock_sector(ticker_upper, sector, datetime.datetime.utcnow().isoformat())
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
            upsert_stock_sector(ticker_upper, sector, datetime.datetime.utcnow().isoformat())
            cached[ticker] = sector
        except Exception as exc:
            print(f"[Finnhub] Sector fetch failed for {ticker}: {exc}")
            cached[ticker] = "Unknown"
    return cached

def update_stock_prices(forceUpdate: bool = False):
    tickers = get_all_tickers()  # e.g., returns a list like ["AAPL", "MSFT", "GOOG", ...]
    today = datetime.date.today().isoformat()

    last_run = get_last_update()
    if last_run == today and not forceUpdate:
        print("[Finnhub] Update already performed today. Skipping update.")
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