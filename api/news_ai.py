"""
POC: Groq cloud API classifies news articles vs. the user's current holdings
(mention + thematic relevance). Tuned for low cost: small model, tiny caps, opt-in.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import requests

_LOG = logging.getLogger(__name__)

# Default: fast/cheap on Groq (override with NEWS_AI_GROQ_MODEL).
_DEFAULT_NEWS_AI_MODEL = "llama-3.1-8b-instant"


def _env_truthy(name: str, default: str = "0") -> bool:
    v = (os.getenv(name) or default).strip().lower()
    return v in ("1", "true", "yes", "on")


def _news_ai_enabled() -> bool:
    return _env_truthy("NEWS_AI_ENABLED", "0")


def _max_articles_per_run() -> int:
    try:
        return max(0, min(50, int(os.getenv("NEWS_AI_MAX_ARTICLES_PER_RUN") or "3")))
    except ValueError:
        return 3


def _max_input_chars() -> int:
    try:
        return max(500, min(12000, int(os.getenv("NEWS_AI_MAX_INPUT_CHARS") or "2400")))
    except ValueError:
        return 2400


def _groq_model() -> str:
    return (os.getenv("NEWS_AI_GROQ_MODEL") or _DEFAULT_NEWS_AI_MODEL).strip()


def _truncate(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[: n - 1].rstrip() + "…"


def _holdings_lines(universe: dict[str, str], max_lines: int = 60) -> str:
    lines: list[str] = []
    for sym in sorted(universe.keys())[:max_lines]:
        label = universe.get(sym) or ""
        lines.append(f"- {sym}: {label}")
    if len(universe) > max_lines:
        lines.append(f"(+{len(universe) - max_lines} more symbols omitted for brevity)")
    return "\n".join(lines)


def _call_groq_json(system: str, user: str) -> str | None:
    api_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not api_key:
        return None
    model = _groq_model()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.1,
        "max_tokens": 220,
        "response_format": {"type": "json_object"},
    }
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=45,
        )
        if resp.status_code == 400:
            payload.pop("response_format", None)
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=45,
            )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        return (content or "").strip() or None
    except Exception as exc:
        _LOG.debug("news_ai groq request failed: %s", exc)
        return None


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    t = (raw or "").strip()
    if not t:
        return None
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    try:
        obj = json.loads(t)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _normalize_relevance(
    data: dict[str, Any],
    universe: dict[str, str],
) -> dict[str, Any]:
    allowed = {k.upper() for k in universe.keys()}
    mentioned: list[str] = []
    relevant: list[str] = []
    for key, out in (("mentioned", mentioned), ("relevant", relevant)):
        v = data.get(key)
        if not isinstance(v, list):
            continue
        for x in v:
            if not isinstance(x, str):
                continue
            u = x.strip().upper()
            if u in allowed and u not in out:
                out.append(u)
    note = data.get("note")
    note_s = note.strip()[:500] if isinstance(note, str) else ""
    return {"mentioned": mentioned, "relevant": relevant, "note": note_s}


_SYSTEM = (
    "You classify a single news article against the user's stock holdings. "
    "Output ONLY valid JSON with keys: mentioned (array of ticker symbols explicitly present "
    "or clearly indicated), relevant (array of symbols where the story materially concerns "
    "that holding even if the ticker does not appear), note (one short sentence, may be empty). "
    "Use only symbols from the holdings list. If nothing applies, use empty arrays."
)


def _user_prompt(holdings_block: str, title: str, summary: str) -> str:
    return (
        "Holdings (symbol: source label):\n"
        f"{holdings_block}\n\n"
        "Article:\n"
        f"Title: {title}\n"
        f"Summary/body: {summary}\n"
    )


def run_news_ai_relevance_batch() -> int:
    """
    Process up to NEWS_AI_MAX_ARTICLES_PER_RUN recent articles missing AI fields.
    Returns count successfully stored.
    """
    if not _news_ai_enabled():
        return 0
    if not (os.getenv("GROQ_API_KEY") or "").strip():
        _LOG.debug("news_ai: skipped (no GROQ_API_KEY)")
        return 0

    from api.news_digest import portfolio_ticker_universe
    import db_manager

    universe, stats = portfolio_ticker_universe()
    if not universe or stats.get("unique_for_matching", 0) == 0:
        return 0

    cap = _max_articles_per_run()
    if cap == 0:
        return 0

    try:
        lookback = int(os.getenv("NEWS_AI_LOOKBACK_DAYS") or "2")
    except ValueError:
        lookback = 2
    lookback = max(1, min(30, lookback))
    pending = db_manager.list_news_digest_articles_pending_ai(
        days=lookback,
        limit=cap,
    )
    if not pending:
        return 0

    holdings_block = _holdings_lines(universe)
    max_chars = _max_input_chars()
    done = 0
    now = datetime.now(timezone.utc).isoformat()

    for row in pending:
        url = (row.get("url") or "").strip()
        title = _truncate(row.get("title") or "", 220)
        summary = _truncate(row.get("summary") or "", max_chars)
        if not url:
            continue
        user = _user_prompt(holdings_block, title, summary)

        raw = _call_groq_json(_SYSTEM, user)
        if not raw:
            continue
        parsed = _parse_json_object(raw)
        if not parsed:
            continue
        rel = _normalize_relevance(parsed, universe)
        if db_manager.update_news_digest_article_ai_relevance(url, rel, now):
            done += 1

    return done


def enrich_items_with_merged_tickers(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Merge rule-based tickers with AI ``mentioned`` + ``relevant`` for API responses.
    Company labels for AI-only symbols come from the portfolio universe when available.
    """
    if not items:
        return items
    try:
        from api.news_digest import portfolio_ticker_universe

        universe, _ = portfolio_ticker_universe()
    except Exception:
        universe = {}

    for it in items:
        rule = [str(x).upper() for x in (it.get("tickers") or []) if x]
        tc = dict(it.get("ticker_companies") or {})
        ai = it.get("ai_relevance")
        extra: set[str] = set()
        if isinstance(ai, dict):
            for k in ("mentioned", "relevant"):
                for x in ai.get(k) or []:
                    if isinstance(x, str) and x.strip():
                        extra.add(x.strip().upper())
        merged = sorted(set(rule) | extra)
        for s in merged:
            if s not in tc and s in universe:
                tc[s] = universe[s]
        it["tickers"] = merged
        it["ticker_companies"] = tc
    return items
