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

# Defaults tuned for richer context; override via env (see _limits()).
_DEFAULT_MAX_NEWS = 36
_DEFAULT_MAX_SEC = 14
_DEFAULT_MAX_NEWS_SUMMARY = 480
_DEFAULT_MAX_SEC_SUMMARY = 720
_DEFAULT_MAX_PROMPT_CHARS = 18000
_DEFAULT_GROQ_MAX_TOKENS = 1100
_DEFAULT_PORTFOLIO_TICKERS_MAX = 20
_DEFAULT_PER_TICKER_NEWS = 4
_DEFAULT_MAX_SOURCE_LABELS = 40


def _env_int(name: str, default: int, min_v: int = 1, max_v: int | None = None) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        v = int(raw)
    except ValueError:
        return default
    v = max(min_v, v)
    if max_v is not None:
        v = min(max_v, v)
    return v


def _limits() -> dict[str, int]:
    """Effective caps for news/SEC/prompt (env HOME_INSIGHTS_* overrides)."""
    return {
        "max_news": _env_int("HOME_INSIGHTS_MAX_NEWS", _DEFAULT_MAX_NEWS, 1, 100),
        "max_sec": _env_int("HOME_INSIGHTS_MAX_SEC", _DEFAULT_MAX_SEC, 1, 80),
        "max_news_summary": _env_int(
            "HOME_INSIGHTS_MAX_NEWS_SUMMARY", _DEFAULT_MAX_NEWS_SUMMARY, 120, 4000
        ),
        "max_sec_summary": _env_int(
            "HOME_INSIGHTS_MAX_SEC_SUMMARY", _DEFAULT_MAX_SEC_SUMMARY, 200, 8000
        ),
        "max_prompt_chars": _env_int(
            "HOME_INSIGHTS_MAX_PROMPT_CHARS", _DEFAULT_MAX_PROMPT_CHARS, 2000, 100000
        ),
        "groq_max_tokens": _env_int(
            "HOME_INSIGHTS_GROQ_MAX_TOKENS", _DEFAULT_GROQ_MAX_TOKENS, 256, 8192
        ),
        "portfolio_tickers_max": _env_int(
            "HOME_INSIGHTS_PORTFOLIO_TICKERS_MAX", _DEFAULT_PORTFOLIO_TICKERS_MAX, 0, 60
        ),
        "per_ticker_news": _env_int(
            "HOME_INSIGHTS_PER_TICKER_NEWS", _DEFAULT_PER_TICKER_NEWS, 1, 25
        ),
        "max_source_labels": _env_int(
            "HOME_INSIGHTS_MAX_SOURCE_LABELS", _DEFAULT_MAX_SOURCE_LABELS, 8, 80
        ),
    }


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
    lim = _limits()
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": lim["groq_max_tokens"],
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
    "You connect recent market news with SEC filing summaries the user has generated. "
    "News items may include matched tickers, categories, and optional AI relevance "
    "(which holdings the story mentions or materially concerns). "
    "Prioritize connections that relate to the user's stated portfolio tickers when relevant. "
    "Produce actionable, concise insights for a retail investor. "
    "Output ONLY valid JSON with keys: "
    "insights (string, use short bullet lines with leading '- ' or numbers), "
    "sources (array of objects, each with: kind 'news' or 'sec', title string, "
    "optional url string for news, optional detail string for SEC e.g. ticker and form). "
    "Use label fields (N1, S1, …) in sources when citing a specific provided item. "
    "List only sources you actually used in your reasoning (subset of the provided inputs). "
    "If inputs are empty or unrelated, set insights to a brief note and sources to []. "
    "No investment advice; educational framing only."
)


def _format_ai_relevance_line(ai: Any) -> Optional[str]:
    if not isinstance(ai, dict):
        return None
    parts: list[str] = []
    m = ai.get("mentioned")
    r = ai.get("relevant")
    if isinstance(m, list) and m:
        parts.append(
            "ai_mentioned: " + ", ".join(str(x).upper() for x in m[:14] if x)
        )
    if isinstance(r, list) and r:
        parts.append(
            "ai_relevant: " + ", ".join(str(x).upper() for x in r[:14] if x)
        )
    note = ai.get("note")
    if isinstance(note, str) and note.strip():
        parts.append("ai_note: " + _truncate(note.strip(), 240))
    return " | ".join(parts) if parts else None


def _gather_news_rows_for_insights() -> list[dict[str, Any]]:
    """
    Prefer articles tagged to portfolio tickers (one query per symbol), then fill with
    recent general articles. De-duplicates by URL.
    """
    import db_manager
    from api.news_digest import portfolio_ticker_universe

    lim = _limits()
    max_news = lim["max_news"]
    universe, _ = portfolio_ticker_universe()
    cap = lim["portfolio_tickers_max"]
    tickers = sorted(universe.keys())[:cap] if (universe and cap > 0) else []

    seen: set[str] = set()
    out: list[dict[str, Any]] = []

    def _add(r: dict[str, Any]) -> None:
        u = (r.get("url") or r.get("link") or "").strip()
        if not u or u in seen:
            return
        seen.add(u)
        out.append(r)

    if tickers:
        for sym in tickers:
            if len(out) >= max_news:
                break
            rows, _, _ = db_manager.list_news_digest_articles(
                page=1,
                per_page=lim["per_ticker_news"],
                ticker=sym,
                sort="created",
            )
            for r in rows:
                if len(out) >= max_news:
                    break
                _add(r)

    need = max_news - len(out)
    if need > 0:
        rows, _, _ = db_manager.list_news_digest_articles(
            page=1,
            per_page=need,
            sort="created",
        )
        for r in rows:
            if len(out) >= max_news:
                break
            _add(r)

    return out[:max_news]


def _build_context() -> tuple[str, list[dict[str, Any]]]:
    """Returns (user_prompt, catalog) where catalog maps index labels to metadata for UI."""
    import db_manager
    from api.news_digest import portfolio_ticker_universe

    lim = _limits()
    universe, _ = portfolio_ticker_universe()
    hold_line = ", ".join(sorted(universe.keys())[:50]) if universe else "(no holdings in app)"

    rows = _gather_news_rows_for_insights()
    sec_rows = db_manager.get_sec_summaries(limit=lim["max_sec"])

    catalog: list[dict[str, Any]] = []
    lines: list[str] = [
        f"User portfolio tickers (for context only): {hold_line}",
        "",
        "News selection: articles below preferentially include stories matched to those tickers "
        "(when holdings exist), then recent general digest articles; each block lists tags and "
        "optional AI relevance when available.",
        "",
    ]

    lines.append("=== NEWS ARTICLES ===")
    for i, it in enumerate(rows):
        title = _truncate(it.get("title") or "", 220)
        url = (it.get("url") or it.get("link") or "").strip()
        summ = _truncate(it.get("summary") or "", lim["max_news_summary"])
        src = (it.get("source_feed") or "").strip()
        tickers = it.get("tickers") or []
        if isinstance(tickers, list):
            tick_s = ", ".join(str(t).upper() for t in tickers[:16] if t)
        else:
            tick_s = ""
        cats = it.get("categories") or []
        if isinstance(cats, list):
            cat_s = ", ".join(str(c) for c in cats[:12] if c)
        else:
            cat_s = ""
        fs = (it.get("first_seen_at_utc") or "").strip()
        label = f"N{i+1}"
        catalog.append(
            {
                "kind": "news",
                "label": label,
                "title": title,
                "url": url,
                "source_feed": src,
                "tickers": tickers if isinstance(tickers, list) else [],
                "categories": cats if isinstance(cats, list) else [],
            }
        )
        lines.append(f"[{label}] {title}")
        if src:
            lines.append(f"  outlet: {src}")
        if tick_s:
            lines.append(f"  tickers_matched: {tick_s}")
        if cat_s:
            lines.append(f"  categories: {cat_s}")
        rel_line = _format_ai_relevance_line(it.get("ai_relevance"))
        if rel_line:
            lines.append(f"  {rel_line}")
        if fs:
            lines.append(f"  first_seen_utc: {fs}")
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
        stext = _truncate(rec.get("summary_text") or "", lim["max_sec_summary"])
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
    mch = lim["max_prompt_chars"]
    if len(body) > mch:
        body = body[: mch - 1] + "…"
    return body, catalog


def _normalize_sources(raw: Any, catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep model output honest: merge with catalog by label when possible."""
    if not isinstance(raw, list):
        return []
    by_label = {c["label"]: c for c in catalog if c.get("label")}
    cap = _limits()["max_source_labels"]
    out: list[dict[str, Any]] = []
    for item in raw[:cap]:
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
