"""Shared SEC filing fetch/summarize job status for Streamlit + Flask."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_LOCK = threading.RLock()

# Repo root when running `streamlit run services/filings.py` is cwd; align with db_manager data dir.
def _default_status_path() -> Path:
    raw = os.getenv("SEC_FILING_JOB_STATUS_PATH")
    if raw:
        return Path(raw).expanduser()
    return Path.cwd() / "data" / "sec_filing_job_status.json"


STATUS_PATH = _default_status_path()

# Dashboard / Streamlit toast only if job finished within this many seconds (real-time completion).
TOAST_MAX_AGE_SECONDS = int(os.getenv("SEC_FILING_TOAST_MAX_AGE_SECONDS") or "120")


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
    data = json.dumps(payload, indent=2)
    tmp.write_text(data, encoding="utf-8")
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
        "log_lines": [],
        "error": None,
        "tickers": [],
        "updated_at": _utc_now_iso(),
        "finished_at": None,
    }


def write_running(job_id: str, tickers: List[str]) -> None:
    payload = {
        "job_id": job_id,
        "status": "running",
        "message": "Running…",
        "log_lines": [],
        "error": None,
        "tickers": list(tickers),
        "updated_at": _utc_now_iso(),
        "finished_at": None,
    }
    with _LOCK:
        _atomic_write(STATUS_PATH, payload)


def write_done(
    job_id: str,
    message: str,
    log_lines: List[str],
    tickers: List[str],
) -> None:
    now = _utc_now_iso()
    payload = {
        "job_id": job_id,
        "status": "done",
        "message": message,
        "log_lines": list(log_lines),
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
        "message": "SEC filing job failed.",
        "log_lines": [],
        "error": err,
        "tickers": list(tickers),
        "updated_at": now,
        "finished_at": now,
    }
    with _LOCK:
        _atomic_write(STATUS_PATH, payload)


def start_job_if_idle(
    tickers: List[str],
    filing_types: List[str],
    after_iso: str,
    force_refresh: bool,
    runner: Callable[[str, List[str], List[str], str, bool], None],
) -> bool:
    """
    If no job is running, set status to running and spawn ``runner`` in a daemon thread.
    ``runner`` receives (job_id, tickers, filing_types, after_iso, force_refresh).
    """
    with _LOCK:
        if STATUS_PATH.exists():
            try:
                cur = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
                if isinstance(cur, dict) and cur.get("status") == "running":
                    return False
            except (OSError, json.JSONDecodeError):
                pass
        job_id = str(uuid.uuid4())
        write_running(job_id, tickers)

    def _target() -> None:
        try:
            runner(job_id, tickers, filing_types, after_iso, force_refresh)
        except Exception as exc:
            write_error(job_id, str(exc), tickers)

    t = threading.Thread(target=_target, name="sec_filing_job", daemon=True)
    t.start()
    return True
