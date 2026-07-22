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
    Response,
)
import os
import logging
import traceback
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from services import db_manager
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
    security_email = (os.getenv("PUBLIC_SECURITY_EMAIL") or "").strip()
    app_url = (os.getenv("PUBLIC_APP_URL") or "http://127.0.0.1:5050").strip()
    owner_name = (
        os.getenv("PUBLIC_OWNER_NAME")
        or os.getenv("SEC_EDGAR_COMPANY")
        or app_name
    ).strip()
    return {
        "app_name": app_name,
        "support_email": support_email,
        "security_email": security_email,
        "app_url": app_url.rstrip("/"),
        "owner_name": owner_name,
        "support_mailto": f"mailto:{support_email}" if support_email else None,
        "security_mailto": f"mailto:{security_email}" if security_email else None,
    }


def create_flask_app():
    # Configure logging
    logging.basicConfig(level=logging.DEBUG)

    app = Flask(__name__, template_folder=os.path.join(_BASE_DIR, "templates"), static_folder=os.path.join(_BASE_DIR, "static"))
    
    # Disable template caching
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.jinja_env.auto_reload = True

    try:
        from api.portfolio_import import ensure_template_files

        ensure_template_files()
    except Exception:
        logging.exception("Could not write portfolio CSV templates")

    if _env_truthy("TRUST_PROXY_HEADERS"):
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(  # type: ignore[method-assign]
            app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1
        )

    _register_server_exception_logging(app)

    @app.before_request
    def _redirect_http_to_https_when_required():
        if not _env_truthy("PUBLIC_REQUIRE_HTTPS"):
            return None
        if request.scheme == "https":
            return None
        host = (request.host or "").split(":")[0].lower()
        if host in ("127.0.0.1", "localhost"):
            return None
        if request.url.startswith("http://"):
            return redirect(request.url.replace("http://", "https://", 1), code=308)
        return None

    @app.route('/')
    def index():
        resp = make_response(render_template('index.html', public_app=_public_app_context()))
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.route("/plaid")
    def plaid_management():
        if db_manager.get_hide_plaid():
            return redirect(url_for("index"))
        resp = make_response(render_template("plaid.html", public_app=_public_app_context()))
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
        data = request.get_json(silent=True) or {}
        raw = data.get("wipe_etf_sources", False)
        wipe_etf = raw is True or str(raw).strip().lower() in {"1", "true", "yes", "on"}
        try:
            db_manager.wipe_all_data(force=True, wipe_etf_sources=wipe_etf)
            return jsonify({"status": "ok", "wipe_etf_sources": wipe_etf})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route('/admin/backfill_prices', methods=['POST'])
    def admin_backfill_prices():
        """Force Yahoo daily-close backfill for held tickers (quant history)."""
        data = request.get_json(silent=True) or {}
        days = data.get("days")
        lookback = None
        if days is not None and str(days).strip() != "":
            try:
                lookback = int(days)
            except (TypeError, ValueError):
                return jsonify({"error": "days must be an integer"}), 400
            if lookback < 1 or lookback > 3650:
                return jsonify({"error": "days must be between 1 and 3650"}), 400
        try:
            from api import finnhub_api as fh

            result = fh.backfill_held_price_history(lookback_days=lookback, force=True)
            return jsonify({"status": "ok", **result})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route('/admin/hide_manual_entry', methods=['GET'])
    def admin_get_hide_manual_entry():
        try:
            return jsonify({"hide_manual_entry": db_manager.get_hide_manual_entry()})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route('/admin/hide_manual_entry', methods=['POST'])
    def admin_set_hide_manual_entry():
        data = request.get_json(silent=True) or {}
        if "hide_manual_entry" not in data:
            return jsonify({"error": "Missing hide_manual_entry"}), 400
        raw = data.get("hide_manual_entry")
        hidden = raw is True or str(raw).strip().lower() in {"1", "true", "yes", "on"}
        try:
            db_manager.set_hide_manual_entry(hidden)
            return jsonify({"status": "ok", "hide_manual_entry": db_manager.get_hide_manual_entry()})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route('/admin/hide_plaid', methods=['GET'])
    def admin_get_hide_plaid():
        try:
            return jsonify({"hide_plaid": db_manager.get_hide_plaid()})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route('/admin/hide_plaid', methods=['POST'])
    def admin_set_hide_plaid():
        data = request.get_json(silent=True) or {}
        if "hide_plaid" not in data:
            return jsonify({"error": "Missing hide_plaid"}), 400
        raw = data.get("hide_plaid")
        hidden = raw is True or str(raw).strip().lower() in {"1", "true", "yes", "on"}
        try:
            db_manager.set_hide_plaid(hidden)
            return jsonify({"status": "ok", "hide_plaid": db_manager.get_hide_plaid()})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route('/admin/hide_mutual_funds', methods=['GET'])
    def admin_get_hide_mutual_funds():
        try:
            return jsonify({"hide_mutual_funds": db_manager.get_hide_mutual_funds()})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route('/admin/hide_mutual_funds', methods=['POST'])
    def admin_set_hide_mutual_funds():
        data = request.get_json(silent=True) or {}
        if "hide_mutual_funds" not in data:
            return jsonify({"error": "Missing hide_mutual_funds"}), 400
        raw = data.get("hide_mutual_funds")
        hidden = raw is True or str(raw).strip().lower() in {"1", "true", "yes", "on"}
        try:
            db_manager.set_hide_mutual_funds(hidden)
            return jsonify({"status": "ok", "hide_mutual_funds": db_manager.get_hide_mutual_funds()})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route('/admin/hide_etfs', methods=['GET'])
    def admin_get_hide_etfs():
        try:
            return jsonify({"hide_etfs": db_manager.get_hide_etfs()})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route('/admin/hide_etfs', methods=['POST'])
    def admin_set_hide_etfs():
        data = request.get_json(silent=True) or {}
        if "hide_etfs" not in data:
            return jsonify({"error": "Missing hide_etfs"}), 400
        raw = data.get("hide_etfs")
        hidden = raw is True or str(raw).strip().lower() in {"1", "true", "yes", "on"}
        try:
            db_manager.set_hide_etfs(hidden)
            return jsonify({"status": "ok", "hide_etfs": db_manager.get_hide_etfs()})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route('/admin/security_types', methods=['GET'])
    def admin_get_security_types():
        try:
            from api import security_type as st

            return jsonify(st.security_type_summary())
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route('/api/export/holdings.csv', methods=['GET'])
    def export_holdings_csv():
        try:
            from api import portfolio_import as pi

            body = pi.export_holdings_csv()
            return Response(
                body,
                mimetype="text/csv",
                headers={"Content-Disposition": "attachment; filename=holdings.csv"},
            )
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route('/api/export/covered_calls.csv', methods=['GET'])
    def export_covered_calls_csv():
        try:
            from api import portfolio_import as pi

            body = pi.export_covered_calls_csv()
            return Response(
                body,
                mimetype="text/csv",
                headers={"Content-Disposition": "attachment; filename=covered_calls.csv"},
            )
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route('/api/export/portfolio.csv', methods=['GET'])
    def export_portfolio_csv():
        try:
            from api import portfolio_import as pi

            body = pi.export_portfolio_csv()
            return Response(
                body,
                mimetype="text/csv",
                headers={"Content-Disposition": "attachment; filename=portfolio.csv"},
            )
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route('/api/export/portfolio.zip', methods=['GET'])
    def export_portfolio_zip():
        try:
            from api import portfolio_import as pi

            body = pi.export_portfolio_zip_bytes()
            return Response(
                body,
                mimetype="application/zip",
                headers={"Content-Disposition": "attachment; filename=portfolio_export.zip"},
            )
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

    from api.plaid_api import plaid_bp
    app.register_blueprint(plaid_bp)

    from api.umbrel_api import umbrel_api
    app.register_blueprint(umbrel_api)

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

    @app.route("/api/sec_filing_job_status", methods=["GET"])
    def api_sec_filing_job_status():
        from services import sec_filing_job

        return jsonify(sec_filing_job.read_status())

    @app.route("/api/quant_job_status", methods=["GET"])
    def api_quant_job_status():
        from services import quant_job

        return jsonify(quant_job.read_status())

    @app.route("/api/home_insights", methods=["GET"])
    def api_home_insights_get():
        from api.home_insights import get_home_insights_payload

        return jsonify(get_home_insights_payload())

    @app.route("/api/home_insights/refresh", methods=["POST"])
    def api_home_insights_refresh():
        try:
            from api.home_insights import generate_and_store_home_insights, get_home_insights_payload

            generate_and_store_home_insights()
            return jsonify(get_home_insights_payload())
        except Exception as exc:
            _LOG.warning("home_insights refresh failed: %s", exc)
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
                from api.news_ai import enrich_items_with_merged_tickers

                items = enrich_items_with_merged_tickers(items)
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
            from api.news_ai import enrich_items_with_merged_tickers

            items = enrich_items_with_merged_tickers(items)
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
    import socket

    def _bindable(host: str, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                return False
        return True

    preferred = (os.getenv("FLASK_PORT") or os.getenv("PORT") or "").strip()
    candidates = []
    if preferred.isdigit():
        candidates.append(int(preferred))
    candidates.extend([5000, 5050, 8000, 8080, 3000, 5001, 5002])
    host = "0.0.0.0"
    chosen = None
    for port in candidates:
        if _bindable(host, port):
            chosen = port
            break
    if chosen is None:
        raise SystemExit("No free Flask port found; set FLASK_PORT.")
    print(f"FinanceTracker debug server: http://127.0.0.1:{chosen}/")
    create_flask_app().run(host=host, port=chosen, debug=True)
