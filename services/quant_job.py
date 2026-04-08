"""Quant backtest job status (Streamlit + Flask), mirroring sec_filing_job."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from services import db_manager

_LOCK = threading.RLock()


def _default_status_path() -> Path:
    raw = os.getenv("QUANT_JOB_STATUS_PATH")
    if raw:
        return Path(raw).expanduser()
    return Path.cwd() / "data" / "quant_backtest_job_status.json"


STATUS_PATH = _default_status_path()
TOAST_MAX_AGE_SECONDS = int(os.getenv("QUANT_TOAST_MAX_AGE_SECONDS") or os.getenv("SEC_FILING_TOAST_MAX_AGE_SECONDS") or "120")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_finished_at_utc(raw: Any) -> Optional[datetime]:
    if not raw or not isinstance(raw, str):
        return None
    try:
        s = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _finished_age_seconds(data: Dict[str, Any]) -> Optional[float]:
    if data.get("status") not in ("done", "error"):
        return None
    dt = _parse_finished_at_utc(data.get("finished_at"))
    if dt is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())


def _enrich_status(data: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(data)
    age = _finished_age_seconds(out)
    out["finished_age_seconds"] = age
    out["toast_eligible"] = (
        out.get("status") in ("done", "error")
        and age is not None
        and age <= TOAST_MAX_AGE_SECONDS
    )
    return out


def _atomic_write(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_status() -> Dict[str, Any]:
    with _LOCK:
        if not STATUS_PATH.exists():
            return _enrich_status(_idle_payload())
        try:
            raw = STATUS_PATH.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict):
                return _enrich_status(_idle_payload())
            return _enrich_status(data)
        except (OSError, json.JSONDecodeError):
            return _enrich_status(_idle_payload())


def _idle_payload() -> Dict[str, Any]:
    return {
        "job_id": None,
        "status": "idle",
        "message": "",
        "error": None,
        "tickers": [],
        "updated_at": _utc_now_iso(),
        "finished_at": None,
    }


def write_running(job_id: str, tickers: List[str]) -> None:
    payload = {
        "job_id": job_id,
        "status": "running",
        "message": "Running backtest…",
        "error": None,
        "tickers": list(tickers),
        "updated_at": _utc_now_iso(),
        "finished_at": None,
    }
    with _LOCK:
        _atomic_write(STATUS_PATH, payload)


def write_done(job_id: str, message: str, tickers: List[str]) -> None:
    now = _utc_now_iso()
    payload = {
        "job_id": job_id,
        "status": "done",
        "message": message,
        "error": None,
        "tickers": list(tickers),
        "updated_at": now,
        "finished_at": now,
    }
    with _LOCK:
        _atomic_write(STATUS_PATH, payload)


def write_error(job_id: str, err: str, tickers: List[str]) -> None:
    now = _utc_now_iso()
    payload = {
        "job_id": job_id,
        "status": "error",
        "message": "Quant backtest failed.",
        "error": err,
        "tickers": list(tickers),
        "updated_at": now,
        "finished_at": now,
    }
    with _LOCK:
        _atomic_write(STATUS_PATH, payload)


def _tickers_from_params(params: Dict[str, Any]) -> List[str]:
    port = params.get("portfolio")
    if isinstance(port, dict):
        return sorted(str(k).upper() for k in port.keys())
    if isinstance(port, list):
        return sorted(str(x).upper() for x in port if x)
    return []


def execute_quant_backtest_job(job_id: str, params: Dict[str, Any]) -> None:
    """Run backtest, save Plotly JSON figures, persist row, set status done."""
    from quant.quant_backtest import normalize_portfolio_input, run_backtest

    port = params.get("portfolio")
    port_map = normalize_portfolio_input(port)  # type: ignore[arg-type]
    tickers = sorted(port_map.keys())

    stats, figs = run_backtest(
        portfolio=port_map,
        start=params["start"],
        end=params["end"],
        strategy_name=params["strategy_name"],
        fast_window=int(params.get("fast_window") or 50),
        slow_window=int(params.get("slow_window") or 200),
        rebalance_monthly=bool(params.get("rebalance_monthly")),
    )
    buy_stats, _ = run_backtest(
        portfolio=port_map,
        start=params["start"],
        end=params["end"],
        strategy_name="buy_hold",
        rebalance_monthly=bool(params.get("rebalance_monthly")),
    )

    root = Path.cwd() / "data" / "quant_figures" / job_id
    root.mkdir(parents=True, exist_ok=True)
    for name, fig in figs.items():
        (root / f"{name}.json").write_text(fig.to_json(), encoding="utf-8")

    db_manager.insert_quant_backtest_run(
        job_id,
        params,
        stats,
        buy_stats,
    )
    msg = f"Backtest complete ({params.get('strategy_name', 'strategy')}) for {', '.join(tickers)}."
    write_done(job_id, msg, tickers)


def start_quant_job_if_idle(
    params: Dict[str, Any],
    runner: Callable[[str, Dict[str, Any]], None],
) -> bool:
    with _LOCK:
        if STATUS_PATH.exists():
            try:
                cur = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
                if isinstance(cur, dict) and cur.get("status") == "running":
                    return False
            except (OSError, json.JSONDecodeError):
                pass
        job_id = str(uuid.uuid4())
        write_running(job_id, _tickers_from_params(params))

    def _target() -> None:
        try:
            runner(job_id, params)
        except Exception as exc:
            write_error(job_id, str(exc), _tickers_from_params(params))

    threading.Thread(target=_target, name="quant_backtest_job", daemon=True).start()
    return True
