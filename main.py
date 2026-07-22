from runServer import flask_app
from services import db_manager
import atexit
import os
import socket
import subprocess
import sys
import webbrowser
from pathlib import Path


def _env_truthy(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def _parse_port(raw: str | None) -> int | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        port = int(text)
    except ValueError:
        return None
    if 1 <= port <= 65535:
        return port
    return None


def _port_bindable(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _looks_like_airtunes(host: str, port: int) -> bool:
    """macOS AirPlay Receiver answers :5000 with HTTP 403 / Server: AirTunes."""
    try:
        with socket.create_connection((host, port), timeout=0.35) as sock:
            sock.settimeout(0.35)
            sock.sendall(b"HEAD / HTTP/1.0\r\nHost: localhost\r\n\r\n")
            data = sock.recv(512).decode("latin-1", errors="ignore")
    except OSError:
        return False
    lowered = data.lower()
    return "airtunes" in lowered or (
        "403" in data[:40] and "server:" in lowered and "air" in lowered
    )


def _candidate_ports() -> list[int]:
    preferred = _parse_port(os.getenv("FLASK_PORT") or os.getenv("PORT"))
    defaults = [5000, 5050, 8000, 8080, 3000, 5001, 5002, 5051, 8888, 7000]
    if preferred is not None:
        # Honor an explicit port first, then fall back so startup still works.
        rest = [p for p in defaults if p != preferred]
        return [preferred, *rest]
    return defaults


def pick_flask_port(host: str = "127.0.0.1") -> int:
    tried: list[int] = []
    for port in _candidate_ports():
        if port in tried:
            continue
        tried.append(port)
        if not _port_bindable(host, port):
            print(f"  · port {port} busy — trying next…")
            continue
        # Bindable does not guarantee HTTP is ours (rare shared-listen cases).
        if _looks_like_airtunes(host, port):
            print(f"  · port {port} looks like macOS AirPlay (AirTunes) — skipping…")
            continue
        return port
    raise RuntimeError(
        "Could not bind Flask to any candidate port "
        f"({', '.join(str(p) for p in tried)}). Set FLASK_PORT to a free port."
    )


if __name__ == "__main__":
    try:
        def start_streamlit_app(script_name: str, port: str):
            auto_start = os.getenv("STREAMLIT_AUTO_START", "true").strip().lower() in {
                "1",
                "true",
                "yes",
                "y",
                "on",
            }
            if not auto_start:
                print("ℹ️ Streamlit auto-start disabled.")
                return None
            root = Path(__file__).resolve().parent
            script_path = root / script_name
            if not script_path.exists():
                print(f"⚠️ {script_name} not found. Skipping Streamlit.")
                return None
            cmd = [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(script_path),
                "--server.port",
                port,
                "--server.headless",
                "true",
            ]
            try:
                proc = subprocess.Popen(cmd, cwd=str(root))
            except Exception as exc:
                print(f"⚠️ Failed to start Streamlit: {exc}")
                return None
            print(f"🚀 Starting Streamlit on http://127.0.0.1:{port}")
            return proc

        backtest_proc = start_streamlit_app("streamlit_backtest.py", "8501")
        filings_proc = start_streamlit_app("services/filings.py", "8502")
        if backtest_proc:
            atexit.register(lambda: backtest_proc.terminate())
        if filings_proc:
            atexit.register(lambda: filings_proc.terminate())

        # Initialize DB first; Dash pages query it when they are imported.
        db_manager.init_db()
        db_manager.delete_orphan_stock_prices()

        # Initialize Dash before the Flask server handles any requests.
        import dashApp as dashApp  # noqa: F401

        # Update stock prices needs to run here so db has time to initialize.
        import api.finnhub_api as finnhub

        finnhub.update_stock_prices()
        db_manager.delete_orphan_stock_prices()

        host = "127.0.0.1"
        print("Selecting Flask port…")
        port = pick_flask_port(host)
        home_url = f"http://{host}:{port}/"
        print("")
        print("=" * 56)
        print("  FinanceTracker is ready")
        print(f"  Home page: {home_url}")
        print("=" * 56)
        print("")
        if _env_truthy("FLASK_OPEN_BROWSER", default=True):
            try:
                webbrowser.open(home_url)
            except Exception:
                pass
        flask_app.run(host=host, port=port, use_reloader=False)
    except KeyboardInterrupt:
        print("Shutting down the application...")
