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

    @app.route('/quant')
    def quant():
        resp = make_response(render_template('quant.html'))
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.route('/filings')
    def filings():
        resp = make_response(render_template('filings.html'))
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

    @app.route('/admin/etf_sources', methods=['GET'])
    def admin_get_etf_sources():
        try:
            df = db_manager.get_etf_sources()
            records = df.sort_values("symbol").to_dict(orient="records") if not df.empty else []
            return jsonify({"items": records})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route('/admin/etf_sources', methods=['POST'])
    def admin_upsert_etf_source():
        data = request.get_json(force=True) or {}
        symbol = (data.get("symbol") or "").strip().upper()
        url = (data.get("url") or "").strip() or None
        source_type = (data.get("source_type") or "").strip() or None
        if not symbol:
            return jsonify({"error": "Missing symbol"}), 400
        try:
            from api import etf_breakdown
            result = etf_breakdown.resolve_source(
                symbol,
                url=url,
                source_type=source_type,
                allow_auto_lookup=True,
            )
            return jsonify({"status": "ok", "source": result})
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
                return jsonify({
                    "volatility_pct": None,
                    "max_drawdown_pct": None,
                    "beta": None,
                    "last_updated": None,
                    "fresh": False,
                    "top_sector": None,
                    "top_sector_pct": None,
                    "hhi": None,
                    "diversification_ratio": None,
                })
            df = df.sort_values("date").copy()
            df["returns"] = df["portfolio_value"].pct_change()
            returns = df["returns"].dropna()
            volatility = None
            volatility_raw = None
            if not returns.empty:
                volatility_raw = returns.std() * math.sqrt(252)
                volatility = volatility_raw * 100
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
            top_sector = None
            top_sector_pct = None
            hhi = None
            diversification_ratio = None
            value_df = db_manager.get_value_stocks()
            if not value_df.empty:
                value_df = value_df.copy()
                total_value = value_df["position_value"].sum()
                if total_value > 0:
                    value_df["weight"] = value_df["position_value"] / total_value
                    try:
                        from api import finnhub_api
                        from api import etf_breakdown
                        tickers = value_df["ticker"].tolist()
                        sector_map = finnhub_api.get_sector_allocation_map(tickers)
                        sector_weights = {}
                        for _, row in value_df.iterrows():
                            ticker = row["ticker"]
                            weight = float(row["weight"])
                            if etf_breakdown.is_tracked_etf(ticker):
                                breakdown = etf_breakdown.get_sector_breakdown(ticker, refresh_days=7)
                                if breakdown:
                                    for sector, portion in breakdown.items():
                                        sector_weights[sector] = sector_weights.get(sector, 0.0) + weight * float(portion)
                                    continue
                            sector = sector_map.get(ticker) or "Unknown"
                            sector_weights[sector] = sector_weights.get(sector, 0.0) + weight
                        if sector_weights:
                            total_sector_weight = sum(sector_weights.values())
                            if total_sector_weight > 0:
                                normalized = {k: v / total_sector_weight for k, v in sector_weights.items()}
                                top_sector = max(normalized, key=normalized.get)
                                top_sector_pct = float(normalized[top_sector] * 100)
                                hhi = float(sum(value ** 2 for value in normalized.values()))
                    except Exception:
                        pass
                    price_df = db_manager.get_stock_prices_df()
                    if not price_df.empty:
                        price_df = price_df.copy()
                        price_df["date"] = pd.to_datetime(price_df["date"])
                        price_df["closing_price"] = pd.to_numeric(price_df["closing_price"], errors="coerce")
                        price_df = price_df.sort_values(["ticker", "date"])
                        price_df["returns"] = price_df.groupby("ticker")["closing_price"].pct_change()
                        vol_by_ticker = price_df.groupby("ticker")["returns"].std() * math.sqrt(252)
                        vol_by_ticker = vol_by_ticker.dropna()
                        if not vol_by_ticker.empty and "weight" in value_df.columns:
                            weights = value_df.set_index("ticker")["weight"]
                            aligned = vol_by_ticker.to_frame("vol").join(weights.to_frame("weight"), how="inner")
                            if not aligned.empty:
                                weighted_avg_vol = float((aligned["vol"] * aligned["weight"]).sum())
                                if weighted_avg_vol > 0 and volatility_raw:
                                    diversification_ratio = float(volatility_raw / weighted_avg_vol)
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
                "top_sector": top_sector,
                "top_sector_pct": round(top_sector_pct, 2) if top_sector_pct is not None else None,
                "hhi": round(hhi, 4) if hhi is not None else None,
                "diversification_ratio": round(diversification_ratio, 2) if diversification_ratio is not None else None,
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
