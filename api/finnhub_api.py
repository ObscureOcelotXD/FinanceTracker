# finnhub_api.py
from flask import Blueprint, jsonify, request
import os
import requests
import concurrent.futures
import datetime
from dotenv import load_dotenv
try:
    # When running from the project root.
    from db_manager import get_all_tickers, upsert_stock_price
except ModuleNotFoundError:
    # When the package is imported as a module (e.g., api.finnhub_api).
    from ..db_manager import get_all_tickers, upsert_stock_price

finnhub_api = Blueprint("finnhub_api", __name__)

# Load .env so the key is available when this module is imported.
load_dotenv()

def _get_finnhub_api_key():
    key = os.getenv("FINNHUB_API_KEY")
    if key:
        return key.strip()
    return None

FINNHUB_QUOTE_URL = "https://finnhub.io/api/v1/quote"

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

def update_stock_prices():
    tickers = get_all_tickers()  # e.g., returns a list like ["AAPL", "MSFT", "GOOG", ...]
    today = datetime.date.today().isoformat()

    # Fetch prices concurrently using Finnhub
    batch_prices = fetch_stock_prices_batch(tickers)
    
    for ticker in tickers:
        price = batch_prices.get(ticker)
        if price is not None:
            upsert_stock_price(ticker, today, price)
            print(f"Inserted price for {ticker}: {price}")
        else:
            print(f"Price for {ticker} not available.")
