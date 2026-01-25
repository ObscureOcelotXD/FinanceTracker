from flask import Flask, render_template, jsonify, request, make_response
import os
import logging
import math
import datetime as dt
import pandas as pd
import requests
import api.alpha_api as av
# import finnhub_api as finn
from dotenv import load_dotenv
import db_manager

# Load environment variables
load_dotenv()

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(_BASE_DIR, "templates"), static_folder=os.path.join(_BASE_DIR, "static"))
app.config["DEBUG"] = True


@app.route('/')
def index():
    resp = make_response(render_template('index.html'))  # Serve the HTML page
    resp.headers["Cache-Control"] = "no-store"
    return resp


def create_flask_app():
    # Configure logging
    logging.basicConfig(level=logging.DEBUG)

    app = Flask(__name__, template_folder=os.path.join(_BASE_DIR, "templates"), static_folder=os.path.join(_BASE_DIR, "static"))
    
    # Disable template caching
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.jinja_env.auto_reload = True

    @app.route('/')
    def index():
        resp = make_response(render_template('index.html'))
        resp.headers["Cache-Control"] = "no-store"
        return resp

    


    @app.route('/webhook', methods=['POST'])
    def webhook():
        data = request.get_json()
        print("Received webhook:", data)
        return jsonify({"status": "received"}), 200

    @app.route('/admin/wipe_all', methods=['POST'])
    def admin_wipe_all():
        try:
            db_manager.wipe_all_data(force=True)
            return jsonify({"status": "ok"})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    def _fetch_yahoo_history(symbol, start_date, end_date):
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        params = {
            "period1": int(start_date.timestamp()),
            "period2": int(end_date.timestamp()),
            "interval": "1d",
            "events": "div,splits",
            "includePrePost": "false",
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36",
            "Accept": "application/json,text/plain,*/*",
        }
        resp = requests.get(url, params=params, headers=headers, timeout=20)
        data = resp.json()
        try:
            result = data["chart"]["result"][0]
            timestamps = result.get("timestamp", [])
            closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        except (KeyError, IndexError, TypeError):
            return None, data
        return list(zip(timestamps, closes)), None

    def _ensure_benchmark_history(symbol, start_date, end_date):
        series = db_manager.get_benchmark_price_series(symbol)
        if not series.empty:
            last_date = series["date"].max()
            if last_date >= end_date - dt.timedelta(days=2):
                return series
        candles, error = _fetch_yahoo_history(symbol, start_date, end_date)
        if error:
            return series
        for ts, close in candles:
            if close is None:
                continue
            date_str = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).date().isoformat()
            db_manager.upsert_benchmark_price(symbol, date_str, float(close), source="Yahoo")
        return db_manager.get_benchmark_price_series(symbol)

    @app.route('/quant/risk_summary', methods=['GET'])
    def quant_risk_summary():
        try:
            df = db_manager.get_portfolio_value_history()
            if df.empty or len(df) < 2:
                return jsonify({"volatility_pct": None, "max_drawdown_pct": None, "beta": None, "last_updated": None, "fresh": False})
            df = df.sort_values("date").copy()
            df["returns"] = df["portfolio_value"].pct_change()
            returns = df["returns"].dropna()
            volatility = None
            if not returns.empty:
                volatility = returns.std() * math.sqrt(252) * 100
            running_max = df["portfolio_value"].cummax()
            drawdown = df["portfolio_value"] / running_max - 1
            max_drawdown = drawdown.min() * 100 if not drawdown.empty else None
            beta = None
            start_date = df["date"].min()
            end_date = df["date"].max() + dt.timedelta(days=1)
            last_updated = df["date"].max().date()
            today = dt.datetime.utcnow().date()
            weekday = today.weekday()
            if weekday == 0:
                last_business_day = today - dt.timedelta(days=3)
            elif weekday == 6:
                last_business_day = today - dt.timedelta(days=2)
            elif weekday == 5:
                last_business_day = today - dt.timedelta(days=1)
            else:
                last_business_day = today
            fresh = last_updated >= last_business_day
            spy = _ensure_benchmark_history("SPY", start_date, end_date)
            if not spy.empty:
                spy = spy.sort_values("date").copy()
                spy["returns"] = spy["closing_price"].pct_change()
                merged = pd.merge(
                    df[["date", "returns"]],
                    spy[["date", "returns"]].rename(columns={"returns": "spy_returns"}),
                    on="date",
                    how="inner",
                ).dropna()
                if len(merged) >= 3 and merged["spy_returns"].var() != 0:
                    beta = merged["returns"].cov(merged["spy_returns"]) / merged["spy_returns"].var()
            return jsonify({
                "volatility_pct": round(volatility, 2) if volatility is not None else None,
                "max_drawdown_pct": round(max_drawdown, 2) if max_drawdown is not None else None,
                "beta": round(beta, 2) if beta is not None else None,
                "last_updated": last_updated.isoformat(),
                "fresh": fresh,
            })
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500
    

    app.register_blueprint(av.alpha_api)

    from api.finnhub_api import finnhub_api
    app.register_blueprint(finnhub_api)

    from api.plaid_api import plaid_bp
    app.register_blueprint(plaid_bp)

    from api.coingecko_api import coingecko_api
    app.register_blueprint(coingecko_api)

    from api.umbrel_api import umbrel_api
    app.register_blueprint(umbrel_api)

    # from api.nownodes_api import nownodes_api
    # app.register_blueprint(nownodes_api)

    from api.umbrel_lightning_api import umbrel_lightning_api
    app.register_blueprint(umbrel_lightning_api)
    
    from api.btc_wallet_api import btc_wallet_api
    app.register_blueprint(btc_wallet_api)

    # from api.binance_api import binance_api
    # app.register_blueprint(binance_api)
    return app

if __name__ == '__main__':
    #app = create_flask_app() # uncomment to run app fron this file.
    # av.update_stock_prices()
    app.run(host="0.0.0.0", port=5000, debug=True)
