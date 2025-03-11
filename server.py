from flask import Flask, render_template, jsonify, request
from flask import Flask, render_template
import logging
import api.alpha_api as av
# import finnhub_api as finn
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config["DEBUG"] = True


@app.route('/')
def index():
    return render_template('index.html')  # Serve the HTML page


def create_flask_app():
    # Configure logging
    logging.basicConfig(level=logging.DEBUG)

    app = Flask(__name__)

    @app.route('/')
    def index():
        return render_template('index.html')

    


    @app.route('/webhook', methods=['POST'])
    def webhook():
        data = request.get_json()
        print("Received webhook:", data)
        return jsonify({"status": "received"}), 200
    

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
    
    # from api.binance_api import binance_api
    # app.register_blueprint(binance_api)

    return app

if __name__ == '__main__':
    #app = create_flask_app() # uncomment to run app fron this file.
    app.run(host="0.0.0.0", port=5000, debug=True)
