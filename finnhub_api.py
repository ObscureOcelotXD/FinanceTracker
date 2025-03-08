# finnhub_api.py
from flask import Blueprint, jsonify
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
