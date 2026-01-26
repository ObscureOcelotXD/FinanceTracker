from runServer import flask_app
import db_manager
import atexit
import os
import subprocess
import sys
from pathlib import Path

if __name__ == '__main__':
    try:
        def start_streamlit():
            auto_start = os.getenv("STREAMLIT_AUTO_START", "true").strip().lower() in {"1", "true", "yes", "y", "on"}
            if not auto_start:
                print("ℹ️ Streamlit auto-start disabled.")
                return None
            root = Path(__file__).resolve().parent
            script_path = root / "streamlit_backtest.py"
            if not script_path.exists():
                print("⚠️ streamlit_backtest.py not found. Skipping Streamlit.")
                return None
            cmd = [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(script_path),
                "--server.port",
                "8501",
                "--server.headless",
                "true",
            ]
            try:
                proc = subprocess.Popen(cmd, cwd=str(root))
            except Exception as exc:
                print(f"⚠️ Failed to start Streamlit: {exc}")
                return None
            print("🚀 Starting Streamlit on http://127.0.0.1:8501")
            return proc

        streamlit_proc = start_streamlit()
        if streamlit_proc:
            atexit.register(lambda: streamlit_proc.terminate())

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

