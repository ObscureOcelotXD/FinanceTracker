from runServer import flask_app
import db_manager

if __name__ == '__main__':
    try:
        # Initialize Dash before the Flask server handles any requests.
        import dashApp as dashApp
        import dash_callbacks

        db_manager.init_db()
        db_manager.delete_orphan_stock_prices()

        # Update stock prices needs to run here so db has time to initialize.
        import api.finnhub_api as finnhub
        finnhub.update_stock_prices()
        db_manager.delete_orphan_stock_prices()

        print("🚀 Starting Flask (with Dash) on http://127.0.0.1:5000")
        flask_app.run(host="127.0.0.1", port=5000, use_reloader=False)
    except KeyboardInterrupt:
        print("Shutting down the application...")

