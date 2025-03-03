from flask import Blueprint, jsonify
import os
import requests

alpha_api = Blueprint('alpha_api', __name__)

ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")

def get_sp500_value():
    # Example: Use Alpha Vantage GLOBAL_QUOTE endpoint for S&P 500
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": "SPY",  # Check documentation for the correct symbol
        "apikey": ALPHA_VANTAGE_API_KEY
    }
    response = requests.get(url, params=params)
    data = response.json()
    print("Alpha Vantage response:", data) 
    try:
        # Adjust the key names based on Alpha Vantage response structure
        sp500_value = data["Global Quote"]["05. price"]
    except KeyError:
        sp500_value = None
    return sp500_value

@alpha_api.route('/sp500', methods=['GET'])
def sp500():
    value = get_sp500_value()
    if value is None:
        return jsonify({"error": "Could not fetch S&P 500 data"}), 500
    return jsonify({"sp500": value})




def get_btc_value():
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "DIGITAL_CURRENCY_DAILY",
        "symbol": "BTC",
        "market": "USD",
        "apikey": ALPHA_VANTAGE_API_KEY
    }
    response = requests.get(url, params=params)
    data = response.json()
    print("Alpha Vantage BTC response:", data)  # Debug: view the full response
    
    # The daily crypto data is returned under the key "Time Series (Digital Currency Daily)"
    try:
        time_series = data["Time Series (Digital Currency Daily)"]
        # The keys are date strings. We sort them and pick the most recent.
        latest_date = sorted(time_series.keys())[-1]
        # Typically, the closing value in USD is under the key "4a. close (USD)"
        btc_value = time_series[latest_date]["4. close"]
        return btc_value
    except KeyError as e:
        print("Error parsing BTC data:", e)
        return None
    

@alpha_api.route('/btc', methods=['GET'])
def btc():
    value = get_btc_value()
    if value is None:
        return jsonify({"error": "Could not fetch BTC data"}), 500
    return jsonify({"btc": value})