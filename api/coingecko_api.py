# api/coingecko_api.py
from flask import Blueprint, jsonify, request
import requests

coingecko_api = Blueprint('coingecko_api', __name__)

# Mapping from common ticker symbols to CoinGecko IDs
# COIN_MAPPING = {
#     "BTC": "bitcoin",
#     "ETH": "ethereum",
#     "LTC": "litecoin",
#     # add more mappings as needed...
# }

def get_coin_price(coin_id, vs_currency="usd"):
    """Call CoinGecko's simple price endpoint to get current price."""
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": coin_id,
        "vs_currencies": vs_currency
    }
    response = requests.get(url, params=params)
    data = response.json()
    return data

@coingecko_api.route('/coingecko', methods=['POST'])
def coingecko_quote():
    data = request.get_json(force=True)
    ticker = data.get("ticker")
    if not ticker:
        return jsonify({"error": "No ticker provided"}), 400

    # Map the provided ticker to a CoinGecko coin id
    coin_id = ticker #COIN_MAPPING.get(ticker.upper())
    if not coin_id:
        return jsonify({"error": f"Ticker '{ticker}' not recognized."}), 400

    price_data = get_coin_price(coin_id)
    # Expected response is like: {"bitcoin": {"usd": 26000.12}}
    if coin_id in price_data and "usd" in price_data[coin_id]:
        price = price_data[coin_id]["usd"]
        return jsonify({"ticker": ticker.upper(), "price": price})
    else:
        return jsonify({"error": "Data not found or API error", "data": price_data}), 500


@coingecko_api.route('/coingeckoBtc', methods=['POST'])
def coingecko_BTC_quote():
    """Return the current price of Bitcoin (BTC) from CoinGecko."""
    coin_id = "bitcoin"  # CoinGecko's id for Bitcoin
    price_data = get_coin_price(coin_id)
    if coin_id in price_data and "usd" in price_data[coin_id]:
        price = price_data[coin_id]["usd"]
        return jsonify({"ticker": "BTC", "price": price})
    else:
        return jsonify({"error": "Data not found or API error", "data": price_data}), 500