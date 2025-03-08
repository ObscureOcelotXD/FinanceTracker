# binance_api.py
from flask import Blueprint, jsonify, request
import requests

binance_api = Blueprint('binance_api', __name__)

def get_binance_price(symbol="BTCUSDT"):
    """Fetch the current price for the given symbol from Binance API."""
    url = "https://api.binance.com/api/v3/ticker/price"
    params = {"symbol": symbol}
    response = requests.get(url, params=params)
    # You may want to add error checking here
    data = response.json()
    return data

@binance_api.route('/binanceBtc', methods=['GET'])
def binance_quote():
    """
    Endpoint to get the current price of a cryptocurrency.
    Accepts an optional query parameter 'symbol'. Defaults to BTCUSDT.
    Example: /binance?symbol=BTCUSDT
    """
    symbol = request.args.get("symbol", "BTCUSDT").upper()
    data = get_binance_price(symbol)
    if "price" in data:
        return jsonify({"symbol": symbol, "price": data["price"]})
    else:
        return jsonify({"error": "Data not found or API error", "data": data}), 500
