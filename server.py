from flask import Flask, render_template, jsonify, request, make_response
import os
import logging
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
