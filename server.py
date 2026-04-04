from flask import (
    Flask,
    render_template,
    jsonify,
    request,
    make_response,
    redirect,
    url_for,
    got_request_exception,
    has_request_context,
)
import os
import logging
import traceback
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

import api.alpha_api as av
import db_manager
from api.quant_risk import compute_risk_summary

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_LOG = logging.getLogger(__name__)


def _env_truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes")


def _client_error_log_enabled() -> bool:
    if _env_truthy("ENABLE_ERROR_LOG"):
        return True
    return _env_truthy("ENABLE_CLIENT_ERROR_LOG")


def _server_error_log_enabled() -> bool:
    if _env_truthy("ENABLE_ERROR_LOG"):
        return True
    return _env_truthy("ENABLE_SERVER_ERROR_LOG")


def _register_server_exception_logging(app: Flask) -> None:
    @got_request_exception.connect_via(app)
    def _log_unhandled(sender, exception, **extra):
        if not _server_error_log_enabled():
            return
        try:
            from werkzeug.exceptions import HTTPException
            if isinstance(exception, HTTPException):
                code = exception.code
                if code is None or code < 500:
                    return
        except Exception:
            pass
        try:
            if has_request_context():
                ep = request.endpoint or "unknown"
                path = request.path or ""
            else:
                ep = "no_request"
                path = ""
            source = f"{ep}:{path}"[:120]
            msg = f"{type(exception).__name__}: {exception}"[:2000]
            detail = traceback.format_exc()[:4000]
            db_manager.insert_app_error("server", source, msg, detail)
        except Exception as exc:
            _LOG.warning("server error log failed: %s", exc)


def _public_app_context():
    app_name = (os.getenv("PUBLIC_APP_NAME") or "FinanceTracker").strip()
    support_email = (
        os.getenv("PUBLIC_SUPPORT_EMAIL")
        or os.getenv("SEC_EDGAR_EMAIL")
        or ""
    ).strip()
    app_url = (os.getenv("PUBLIC_APP_URL") or "http://127.0.0.1:5000").strip()
    owner_name = (
        os.getenv("PUBLIC_OWNER_NAME")
        or os.getenv("SEC_EDGAR_COMPANY")
        or app_name
    ).strip()
    return {
        "app_name": app_name,
        "support_email": support_email,
        "app_url": app_url.rstrip("/"),
        "owner_name": owner_name,
        "support_mailto": f"mailto:{support_email}" if support_email else None,
    }


def create_flask_app():
    # Configure logging
    logging.basicConfig(level=logging.DEBUG)

    app = Flask(__name__, template_folder=os.path.join(_BASE_DIR, "templates"), static_folder=os.path.join(_BASE_DIR, "static"))
    
    # Disable template caching
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.jinja_env.auto_reload = True

    _register_server_exception_logging(app)

    @app.route('/')
    def index():
        resp = make_response(render_template('index.html', public_app=_public_app_context()))
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.route('/quant')
    def quant():
        resp = make_response(render_template('quant.html', public_app=_public_app_context()))
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.route('/filings')
    def filings():
        resp = make_response(render_template('filings.html', public_app=_public_app_context()))
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.route("/news")
    def news():
        resp = make_response(render_template("news.html", public_app=_public_app_context()))
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.route('/privacy')
    def privacy():
        resp = make_response(render_template('privacy.html', public_app=_public_app_context()))
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.route('/terms')
    def terms():
        resp = make_response(render_template('terms.html', public_app=_public_app_context()))
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.route('/support')
    def support():
        resp = make_response(render_template('support.html', public_app=_public_app_context()))
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

    # Optional: browser calls POST /api/client_error with {source, message, detail?} when client error logging is enabled.
    @app.route("/api/client_error", methods=["POST"])
    def client_error():
        if not _client_error_log_enabled():
            return jsonify({"status": "disabled"}), 200
        payload = request.get_json(silent=True) or {}
        source = str(payload.get("source") or "app")[:120]
        message = str(payload.get("message") or "")[:2000]
        detail = payload.get("detail")
        if detail is not None:
            detail = str(detail)[:4000]
        try:
            db_manager.insert_client_error(source, message, detail)
        except Exception as exc:
            _LOG.warning("client_error log failed: %s", exc)
            return jsonify({"status": "error"}), 500
        return jsonify({"status": "ok"}), 200

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

    @app.route("/api/news_digest", methods=["GET"])
    def api_news_digest_get():
        from api.news_digest import load_latest_digest

        data = load_latest_digest()
        if data is None:
            return jsonify(
                {
                    "empty": True,
                    "generated_at_utc": None,
                    "items": [],
                    "item_count": 0,
                    "errors": [],
                    "enrichment": "keywords_v1",
                    "ticker_match_source": "portfolio",
                    "held_tickers_count": 0,
                    "portfolio_ticker_stats": {
                        "manual_distinct": 0,
                        "plaid_distinct": 0,
                        "unique_for_matching": 0,
                    },
                    "ticker_companies": {},
                }
            )
        return jsonify(data)

    @app.route("/api/news_digest/refresh", methods=["POST"])
    def api_news_digest_refresh():
        try:
            from api.news_digest import load_latest_digest, run_daily_digest_locked

            run_daily_digest_locked()
            data = load_latest_digest()
            if data is None:
                return jsonify({"error": "Digest not written"}), 500
            return jsonify(data)
        except Exception as exc:
            _LOG.warning("news digest refresh failed: %s", exc)
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/news_articles", methods=["GET"])
    def api_news_articles_list():
        """Stored news rows. With ``page`` query: offset pagination. Without ``page``: one local calendar day per response."""
        try:
            if "page" in request.args:
                try:
                    page = int(request.args.get("page") or 1)
                except (TypeError, ValueError):
                    page = 1
                try:
                    per_page = int(request.args.get("per_page") or 20)
                except (TypeError, ValueError):
                    per_page = 20
                category = (request.args.get("category") or "").strip() or None
                ticker = (request.args.get("ticker") or "").strip() or None
                sort = (request.args.get("sort") or "created").strip() or "created"
                items, total, per_effective = db_manager.list_news_digest_articles(
                    page=page,
                    per_page=per_page,
                    category=category,
                    ticker=ticker,
                    sort=sort,
                )
                pages = (total + per_effective - 1) // per_effective if total else 0
                return jsonify(
                    {
                        "items": items,
                        "total": total,
                        "page": max(1, page),
                        "per_page": per_effective,
                        "pages": pages,
                    }
                )

            from api.news_digest import load_latest_digest

            raw_date = (request.args.get("date") or "").strip()
            if raw_date:
                try:
                    datetime.strptime(raw_date, "%Y-%m-%d")
                except ValueError:
                    return jsonify({"error": "invalid date; use YYYY-MM-DD"}), 400

            meta = db_manager.list_news_digest_local_dates_desc()
            sorted_desc = [x["date"] for x in meta]
            sorted_asc = sorted(sorted_desc)
            if raw_date:
                current = raw_date
            elif sorted_desc:
                current = sorted_desc[0]
            else:
                current = db_manager.today_local_iso_digest_tz()

            items = db_manager.list_news_digest_articles_for_local_date(current)
            older_date, newer_date = db_manager.news_digest_local_date_neighbors(sorted_asc, current)
            latest = load_latest_digest()
            gen = (latest or {}).get("generated_at_utc")
            tz = db_manager.news_digest_schedule_tz()
            tz_key = getattr(tz, "key", None) or str(tz)
            return jsonify(
                {
                    "items": items,
                    "date": current,
                    "older_date": older_date,
                    "newer_date": newer_date,
                    "schedule_tz": tz_key,
                    "digest_generated_at_utc": gen,
                }
            )
        except Exception as exc:
            _LOG.warning("news_articles list failed: %s", exc)
            return jsonify({"error": str(exc)}), 500

    _start_news_digest_background()
    return app


def _start_news_digest_background() -> None:
    """6am local digest + startup catch-up; disable with NEWS_DIGEST_DISABLE_SCHEDULER=1."""
    if _env_truthy("NEWS_DIGEST_DISABLE_SCHEDULER"):
        return
    import threading
    import time

    def startup():
        try:
            from api import news_digest

            news_digest.maybe_run_on_startup()
        except Exception as exc:
            _LOG.warning("news digest startup: %s", exc)

    def loop():
        while True:
            time.sleep(60)
            try:
                from api import news_digest

                news_digest.maybe_run_at_scheduled_time()
            except Exception as exc:
                _LOG.warning("news digest scheduler: %s", exc)

    threading.Thread(target=startup, daemon=True, name="news-digest-startup").start()
    threading.Thread(target=loop, daemon=True, name="news-digest-scheduler").start()


if __name__ == "__main__":
    create_flask_app().run(host="0.0.0.0", port=5000, debug=True)
