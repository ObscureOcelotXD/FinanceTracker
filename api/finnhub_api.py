# finnhub_api.py
from flask import Blueprint, jsonify, request
import os
import requests

finnhub_api = Blueprint('finnhub_api', __name__)

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")  # Make sure this is set in your environment

def get_stock_quote(symbol):
    url = "https://finnhub.io/api/v1/quote"
    params = {"symbol": symbol, "token": FINNHUB_API_KEY}
    response = requests.get(url, params=params)
    print("Request URL:", response.request.url)
    data = response.json()
    print("Finnhub response:", data)
    return data

@finnhub_api.route('/finnhub', methods=['GET'])
def finnhub_quote():
    symbol = "SPY"  # You can later make this dynamic
    data = get_stock_quote(symbol)

    # Finnhub returns a JSON like: { "c": 261.74, "h": 263.31, "l": 260.68, "o": 261.07, "pc": 259.45, "t": 1582641000 }
    if "c" in data:
        return jsonify({"symbol": symbol, "price": data["c"]})
    else:
        return jsonify({"error": "Data not found"}), 500


def get_stock_quote(symbol):
    """Call Finnhub's stock quote endpoint."""
    url = "https://finnhub.io/api/v1/quote"
    params = {
        "symbol": symbol,
        "token": FINNHUB_API_KEY
    }
    response = requests.get(url, params=params)
    data = response.json()
    return data

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

@finnhub_api.route('/stock', methods=['POST'])
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