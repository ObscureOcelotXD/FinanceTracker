from flask import Flask, render_template, jsonify, request, make_response, redirect, url_for
import os
import logging

from dotenv import load_dotenv
load_dotenv()

import api.alpha_api as av
import db_manager
from api.quant_risk import compute_risk_summary

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


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

    @app.route('/favicon.ico')
    def favicon():
        return "", 204

    @app.route('/webhook', methods=['POST'])
    def webhook():
        data = request.get_json()
        print("Received webhook:", data)
        return jsonify({"status": "received"}), 200

    # Plaid OAuth redirect: after user authenticates at bank, Plaid redirects here.
    # Send them back to the app; Link will complete when the frontend has it open.
    @app.route('/oauth/callback')
    def plaid_oauth_callback():
        # Optional: pass through query params if Plaid adds link_session_id etc. for resume
        return redirect(url_for('index'))

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

    @app.route('/quant/risk_summary', methods=['GET'])
    def quant_risk_summary():
        try:
            return jsonify(compute_risk_summary())
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

    try:
        from api.btc_wallet_api import btc_wallet_api
        app.register_blueprint(btc_wallet_api)
        btc_wallet_enabled = True
    except ImportError:
        btc_wallet_enabled = False

    if not btc_wallet_enabled:
        @app.route("/btc/wallet_summary", methods=["GET"])
        def btc_wallet_summary_disabled():
            return jsonify({"enabled": False, "error": "BTC wallet not configured (bip_utils not installed)"})

    # from api.binance_api import binance_api
    # app.register_blueprint(binance_api)
    return app


if __name__ == "__main__":
    create_flask_app().run(host="0.0.0.0", port=5000, debug=True)
