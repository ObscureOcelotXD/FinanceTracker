"""
Groq: synthesize cross-insights from recent news (DB) + SEC filing summaries (DB) for the home page.
One batched JSON call; results cached in ``home_insights_cache``.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

import requests

_LOG = logging.getLogger(__name__)

_DEFAULT_MODEL = "llama-3.1-8b-instant"
_MAX_NEWS = 18
_MAX_SEC = 8
_MAX_NEWS_SUMMARY = 320
_MAX_SEC_SUMMARY = 500
_MAX_PROMPT_CHARS = 10000


def _enabled() -> bool:
    return (os.getenv("HOME_INSIGHTS_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _model() -> str:
    return (os.getenv("HOME_INSIGHTS_GROQ_MODEL") or os.getenv("NEWS_AI_GROQ_MODEL") or _DEFAULT_MODEL).strip()


def _truncate(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[: n - 1].rstrip() + "…"


def _parse_json(raw: str) -> dict[str, Any] | None:
    t = (raw or "").strip()
    if not t:
        return None
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    try:
        o = json.loads(t)
    except json.JSONDecodeError:
        return None
    return o if isinstance(o, dict) else None


def _call_groq(system: str, user: str) -> tuple[str | None, str]:
    api_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not api_key:
        return None, "no_key"
    model = _model()
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": 700,
        "response_format": {"type": "json_object"},
    }
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=90,
        )
        if resp.status_code == 400:
            payload.pop("response_format", None)
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=90,
            )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        return ((content or "").strip() or None), model
    except Exception as exc:
        _LOG.warning("home_insights groq failed: %s", exc)
        return None, model


_SYSTEM = (
    "You connect recent market news headlines with SEC filing summaries the user has generated. "
    "Produce actionable, concise insights for a retail investor. "
    "Output ONLY valid JSON with keys: "
    "insights (string, use short bullet lines with leading '- ' or numbers), "
    "sources (array of objects, each with: kind 'news' or 'sec', title string, "
    "optional url string for news, optional detail string for SEC e.g. ticker and form). "
    "List only sources you actually used in your reasoning (subset of the provided inputs). "
    "If inputs are empty or unrelated, set insights to a brief note and sources to []. "
    "No investment advice; educational framing only."
)


def _build_context() -> tuple[str, list[dict[str, Any]]]:
    """Returns (user_prompt, catalog) where catalog maps index labels to metadata for UI."""
    import db_manager
    from api.news_digest import portfolio_ticker_universe

    universe, _ = portfolio_ticker_universe()
    hold_line = ", ".join(sorted(universe.keys())[:40]) if universe else "(no holdings in app)"

    rows, _, _ = db_manager.list_news_digest_articles(page=1, per_page=_MAX_NEWS, sort="created")
    sec_rows = db_manager.get_sec_summaries(limit=_MAX_SEC)

    catalog: list[dict[str, Any]] = []
    lines: list[str] = [f"User portfolio tickers (for context only): {hold_line}", ""]

    lines.append("=== NEWS ARTICLES ===")
    for i, it in enumerate(rows):
        title = _truncate(it.get("title") or "", 200)
        url = (it.get("url") or it.get("link") or "").strip()
        summ = _truncate(it.get("summary") or "", _MAX_NEWS_SUMMARY)
        src = (it.get("source_feed") or "").strip()
        label = f"N{i+1}"
        catalog.append({"kind": "news", "label": label, "title": title, "url": url, "source_feed": src})
        lines.append(f"[{label}] {title}")
        if src:
            lines.append(f"  outlet: {src}")
        if summ:
            lines.append(f"  summary: {summ}")
        if url:
            lines.append(f"  url: {url}")
        lines.append("")

    lines.append("=== SEC FILING SUMMARIES (cached AI summaries) ===")
    for j, rec in enumerate(sec_rows):
        ticker = (rec.get("ticker") or "").strip()
        ftype = (rec.get("filing_type") or "").strip()
        fdate = (rec.get("filing_date") or "").strip()
        stext = _truncate(rec.get("summary_text") or "", _MAX_SEC_SUMMARY)
        label = f"S{j+1}"
        catalog.append(
            {
                "kind": "sec",
                "label": label,
                "title": f"{ticker} {ftype}".strip(),
                "detail": fdate,
                "doc_hash": rec.get("doc_hash"),
            }
        )
        lines.append(f"[{label}] {ticker} {ftype} (filed/reported ~ {fdate})")
        if stext:
            lines.append(f"  summary_excerpt: {stext}")
        lines.append("")

    body = "\n".join(lines).strip()
    if len(body) > _MAX_PROMPT_CHARS:
        body = body[: _MAX_PROMPT_CHARS - 1] + "…"
    return body, catalog


def _normalize_sources(raw: Any, catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep model output honest: merge with catalog by label when possible."""
    if not isinstance(raw, list):
        return []
    by_label = {c["label"]: c for c in catalog if c.get("label")}
    out: list[dict[str, Any]] = []
    for item in raw[:24]:
        if not isinstance(item, dict):
            continue
        kind = (item.get("kind") or "").strip().lower()
        if kind not in ("news", "sec"):
            continue
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip() or None
        detail = (item.get("detail") or "").strip() or None
        lab = (item.get("label") or "").strip()
        if lab and lab in by_label:
            base = by_label[lab]
            title = title or base.get("title") or ""
            if kind == "news":
                url = url or base.get("url") or None
            if kind == "sec" and not detail:
                detail = base.get("detail")
        entry: dict[str, Any] = {"kind": kind, "title": title}
        if url:
            entry["url"] = url
        if detail:
            entry["detail"] = detail
        if title or url or detail:
            out.append(entry)
    return out


def generate_and_store_home_insights() -> bool:
    """
    Pull latest news + SEC summaries, call Groq, persist cache. Returns True on success.
    """
    import db_manager

    if not _enabled():
        return False
    if not (os.getenv("GROQ_API_KEY") or "").strip():
        db_manager.upsert_home_insights(
            None,
            [],
            "none",
            error_text="Set GROQ_API_KEY to generate insights.",
        )
        return False

    body, catalog = _build_context()

    user = (
        "Using ONLY the inputs below, write cross-cutting insights.\n\n" + body
    )
    raw, model = _call_groq(_SYSTEM, user)
    if not raw:
        db_manager.upsert_home_insights(
            None,
            [],
            model,
            error_text="Groq request failed or returned empty. Try again later.",
        )
        return False

    data = _parse_json(raw)
    if not data:
        db_manager.upsert_home_insights(
            None,
            [],
            model,
            error_text="Could not parse AI response.",
        )
        return False

    insights = data.get("insights")
    insight_text = insights.strip() if isinstance(insights, str) else ""
    sources = _normalize_sources(data.get("sources"), catalog)
    if not insight_text:
        insight_text = "No cross-insights generated from current inputs."

    db_manager.upsert_home_insights(
        insight_text,
        sources,
        model,
        error_text=None,
    )
    return True


def get_home_insights_payload() -> dict[str, Any]:
    """API shape for GET /api/home_insights."""
    import db_manager

    if not _enabled():
        return {
            "enabled": False,
            "insight": None,
            "sources": [],
            "generated_at_utc": None,
            "model": None,
            "error": "Home insights disabled (HOME_INSIGHTS_ENABLED=0).",
        }

    row = db_manager.get_home_insights()
    if not row:
        return {
            "enabled": True,
            "insight": None,
            "sources": [],
            "generated_at_utc": None,
            "model": None,
            "error": None,
            "empty": True,
        }
    insight = row.get("insight_text")
    err = row.get("error_text")
    return {
        "enabled": True,
        "insight": insight,
        "sources": row.get("sources") or [],
        "generated_at_utc": row.get("generated_at_utc"),
        "model": row.get("model"),
        "error": err,
        "empty": not (insight or "").strip() and not (err or "").strip(),
    }
