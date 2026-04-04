"""
Free POC: aggregate public RSS feeds into a daily digest (no API keys, no LLM).

Run manually or on a schedule:
    python scripts/run_daily_news_digest.py

Outputs under data/news_digest/: latest.json, latest.md. Each run also **upserts** rows into
``news_digest_articles`` (SQLite) keyed by normalized URL so you can keep history and query via
``GET /api/news_articles`` (pagination and filters for the UI next). Rows include
``first_seen_at_utc`` (when we first stored the article), optional ``summary`` (NULL until a future
summarization pipeline — see TODO in ``db_manager``). Pruning: set ``NEWS_DIGEST_RETENTION_DAYS``
(default **90**, ``0`` disables) to drop rows whose ``first_seen_at_utc`` is older than that many days.

**Ticker tagging** matches **ticker symbols** (``$LMT``, ``(LMT)``, bare ``LMT`` in uppercase text,
etc.) against your **current** holdings from the DB: **Manage Stocks** and **Plaid-linked**
positions (see ``portfolio_ticker_universe``). Matching text is built from the RSS/Atom **title**,
**description/summary**, **content** blocks when present, URL path words, and — when the feed omits a
body (notably **Yahoo Finance** ``rssindex``, which often has **no** ``description`` in the XML) —
an optional **HTTP fetch** of the article URL to read ``og:description`` / meta description (see
``NEWS_DIGEST_FETCH_ARTICLE_SNIPPET``). Stored ``summary`` holds that combined text for re-tagging.
Each digest run re-enriches items from the feeds; after persisting, stored rows for **today and
yesterday** in ``NEWS_DIGEST_TZ`` are **re-tagged** from the DB so holdings added after a story first
appeared still get badges on Refresh.

Scheduling (when the Flask app runs): set NEWS_DIGEST_TZ (default America/New_York),
NEWS_DIGEST_HOUR (default 6), NEWS_DIGEST_WINDOW_MINUTES (default 5). Automatic runs
are skipped if latest.json is already from "today" in that timezone. Disable
background threads with NEWS_DIGEST_DISABLE_SCHEDULER=1 (e.g. tests).
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import feedparser
import requests

_LOG = logging.getLogger(__name__)
_digest_run_lock = threading.Lock()

DEFAULT_UA = "FinanceTrackerNewsDigest/0.1 (personal POC)"

# Public RSS feeds only — no keys. Replace if a feed stops working.
DEFAULT_FEEDS: list[tuple[str, str]] = [
    ("BBC Business", "http://feeds.bbci.co.uk/news/business/rss.xml"),
    ("CNBC Top Stories", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("MarketWatch Top Stories", "https://feeds.marketwatch.com/marketwatch/topstories/"),
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "data" / "news_digest"

def portfolio_ticker_universe() -> tuple[dict[str, str], dict[str, int]]:
    """
    Build ticker → source label for matching, plus counts for digest metadata.

    Returns:
        universe: uppercased symbol → tooltip label (Manage Stocks / Plaid / both).
        stats: manual_distinct, plaid_distinct, unique_for_matching.
    """
    try:
        import db_manager

        manual = set(db_manager.get_held_stock_tickers())
        plaid = set(db_manager.get_plaid_holdings_tickers())
    except Exception as exc:
        _LOG.warning("portfolio tickers unavailable for news digest: %s", exc)
        return {}, {"manual_distinct": 0, "plaid_distinct": 0, "unique_for_matching": 0}

    universe: dict[str, str] = {}
    for t in sorted(manual | plaid):
        in_m = t in manual
        in_p = t in plaid
        if in_m and in_p:
            universe[t] = "Manage Stocks & Plaid"
        elif in_m:
            universe[t] = "Manage Stocks"
        else:
            universe[t] = "Plaid-linked"

    stats = {
        "manual_distinct": len(manual),
        "plaid_distinct": len(plaid),
        "unique_for_matching": len(universe),
    }
    return universe, stats


def _strip_html(s: str) -> str:
    if not s:
        return ""
    t = re.sub(r"<[^>]+>", " ", s)
    t = html.unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def _rss_entry_combined_plain_text(entry: Any) -> str:
    """
    Merge all RSS/Atom text fields so ticker symbols in the body (not only the headline) match.
    Many feeds put tickers in ``content`` or ``summary_detail`` while ``description`` is shorter.
    """
    parts: list[str] = []
    for key in ("summary", "description", "subtitle"):
        v = entry.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(_strip_html(v))
    sd = entry.get("summary_detail")
    if isinstance(sd, dict) and sd.get("value"):
        parts.append(_strip_html(str(sd["value"])))
    dd = entry.get("description_detail")
    if isinstance(dd, dict) and dd.get("value"):
        parts.append(_strip_html(str(dd["value"])))
    for block in entry.get("content") or []:
        if isinstance(block, dict) and block.get("value"):
            parts.append(_strip_html(str(block["value"])))
    blob = "\n".join(parts)
    return re.sub(r"\s+", " ", blob.strip())


def _article_snippet_fetch_enabled() -> bool:
    return (os.getenv("NEWS_DIGEST_FETCH_ARTICLE_SNIPPET") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def _max_article_snippet_fetches_per_digest() -> int:
    raw = (os.getenv("NEWS_DIGEST_MAX_ARTICLE_SNIPPET_FETCHES") or "50").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 50
    return max(0, n)


def _snippet_fetch_priority_urls_from_db(items: list[dict[str, Any]]) -> set[str]:
    """Canonical URLs in ``items`` that already exist in the DB with NULL/empty ``summary``."""
    import db_manager

    canon: list[str] = []
    for it in items:
        if (it.get("summary_text") or "").strip():
            continue
        if not (it.get("link") or "").strip():
            continue
        canon.append(db_manager.canonical_news_article_url(it))
    if not canon:
        return set()
    return db_manager.news_digest_urls_with_null_summary(canon)


def _fill_article_snippets_for_items(
    items: list[dict[str, Any]],
    max_fetches: int,
    *,
    priority_urls: set[str] | None = None,
) -> None:
    """
    After the digest list is final, fetch HTML meta descriptions for items with no RSS body.
    This runs on the capped ``unique`` list — not on every row of every raw feed — so budget is
    not spent on stories that never make it into the digest (fixes Yahoo items deep in the feed).
    Rows that already exist in SQLite with NULL/empty ``summary`` are fetched first when
    ``priority_urls`` is set (backfill before spending budget on first-time stories).
    """
    if max_fetches <= 0 or not _article_snippet_fetch_enabled():
        return
    import db_manager

    need: list[dict[str, Any]] = []
    for it in items:
        st = (it.get("summary_text") or "").strip()
        link = (it.get("link") or "").strip()
        if st or not link:
            continue
        need.append(it)
    if not need:
        return

    if priority_urls:
        pri_u = set(priority_urls)
        priority_items = [it for it in need if db_manager.canonical_news_article_url(it) in pri_u]
        pri_keys = {db_manager.canonical_news_article_url(it) for it in priority_items}
        rest_items = [it for it in need if db_manager.canonical_news_article_url(it) not in pri_keys]
        ordered = priority_items + rest_items
    else:
        ordered = need

    remaining = max_fetches
    for it in ordered:
        if remaining <= 0:
            break
        link = (it.get("link") or "").strip()
        fetched = _fetch_article_snippet_from_url(link)
        if fetched:
            it["summary_text"] = fetched
            remaining -= 1


def _fetch_article_snippet_from_url(url: str) -> str:
    """
    When RSS has no body, load the article HTML and take ``og:description`` / meta description.
    Yahoo Finance's top news RSS often omits ``<description>`` in the feed XML.
    """
    u = (url or "").strip()
    if not u.startswith(("http://", "https://")):
        return ""
    if not _article_snippet_fetch_enabled():
        return ""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return ""
    try:
        r = requests.get(
            u,
            headers={
                "User-Agent": _user_agent(),
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            },
            timeout=18,
        )
        r.raise_for_status()
        raw = r.text[:800_000]
        soup = BeautifulSoup(raw, "lxml")
        for attrs in (
            {"property": "og:description"},
            {"name": "twitter:description"},
            {"name": "description"},
        ):
            tag = soup.find("meta", attrs=attrs)
            if tag and tag.get("content"):
                t = str(tag["content"]).strip()
                if len(t) > 12:
                    return re.sub(r"\s+", " ", t)[:12000]
    except Exception as exc:
        _LOG.debug("article snippet fetch failed for %s: %s", u, exc)
    return ""


_TICKER_TOKEN_RE = re.compile(r"\b([A-Z0-9]{1,5}(?:\.[A-Z])?)\b")


def _url_path_as_search_text(link: str) -> str:
    """Turn URL path segments (e.g. Yahoo slugs ``...-boeing-lockheed-...``) into space-separated words."""
    if not (link or "").strip():
        return ""
    try:
        path = (urlparse(link.strip()).path or "").strip("/")
        if not path:
            return ""
        return re.sub(r"[-_/]+", " ", path)
    except Exception:
        return ""


def matching_text_for_ticker_enrichment(title: str, summary: str, link: str = "") -> str:
    """
    Text used for ticker matching: title, combined RSS body (``summary_text``), and URL path words.
    """
    parts = [
        (title or "").strip(),
        (summary or "").strip(),
        _url_path_as_search_text(link or ""),
    ]
    blob = "\n".join(p for p in parts if p)
    return re.sub(r"\s+", " ", blob.strip())


def match_tickers_from_universe(
    text: str,
    universe: dict[str, str],
) -> tuple[list[str], dict[str, str]]:
    """
    Find mentions of symbols that exist in ``universe`` (from DB holdings: ``portfolio_ticker_universe``).
    Uses ``$SYM``, ``NYSE: SYM``, ``(SYM)``, and bare tokens (length ≥2 in universe, plus class shares like BRK.A).
    Single-letter tickers only via ``$`` / exchange / parentheses.
    """
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text or not universe:
        return [], {}
    found: set[str] = set()

    for m in re.finditer(r"\$([A-Z0-9]{1,5}(?:\.[A-Z])?)\b", text, flags=re.IGNORECASE):
        sym = m.group(1).upper()
        if sym in universe:
            found.add(sym)

    for m in re.finditer(
        r"(?:NYSE|NASDAQ|AMEX|OTC|BATS)\s*:\s*([A-Z0-9]{1,5}(?:\.[A-Z])?)\b",
        text,
        flags=re.IGNORECASE,
    ):
        sym = m.group(1).upper()
        if sym in universe:
            found.add(sym)

    for m in re.finditer(r"\(([A-Z0-9]{1,5}(?:\.[A-Z])?)\)", text):
        sym = m.group(1).upper()
        if sym in universe:
            found.add(sym)

    u = text.upper()
    for m in _TICKER_TOKEN_RE.finditer(u):
        sym = m.group(1)
        if sym not in universe:
            continue
        # Single-letter tickers (F, C, …) only via $ / exchange / parens above.
        if len(sym) == 1:
            continue
        found.add(sym)

    ordered = sorted(found)
    companies = {s: universe[s] for s in ordered}
    return ordered, companies


def _infer_categories(text: str) -> list[str]:
    """
    Lightweight keyword buckets (no ML). Multiple categories allowed; default is ``general``.
    Designed so a future paid API / LLM layer can replace or augment this field.
    """
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return ["general"]
    tl = f" {text.lower()} "
    cats: set[str] = set()

    def has(p: str) -> bool:
        return p in tl

    # Multi-word and specific phrases first
    if any(
        has(p)
        for p in (
            " interest rate ",
            " federal reserve ",
            " treasury ",
            " bond yield ",
            " yield curve ",
            " fomc ",
            " rate cut ",
            " rate hike ",
            " rate cuts ",
            " rate hikes ",
        )
    ) or has(" powell "):
        cats.add("rates")
    if any(
        has(p)
        for p in (
            " earnings ",
            " quarterly ",
            " eps ",
            " revenue ",
            " guidance ",
            " profit ",
            " beats ",
            " misses ",
        )
    ) or re.search(r"\bq[1-4]\b", tl):
        cats.add("earnings")
    if any(
        has(p)
        for p in (
            " inflation ",
            " recession ",
            " gdp ",
            " unemployment ",
            " jobs report ",
            " consumer price ",
            " cpi ",
        )
    ):
        cats.add("economy")
    if any(
        has(p)
        for p in (
            " bitcoin ",
            " ethereum ",
            " crypto ",
            " blockchain ",
            " dogecoin ",
            " btc ",
        )
    ):
        cats.add("crypto")
    if any(
        has(p)
        for p in (
            " oil ",
            " crude ",
            " opec ",
            " natural gas ",
            " energy sector ",
            " barrel ",
        )
    ):
        cats.add("energy")
    if any(
        has(p)
        for p in (
            " s&p ",
            " nasdaq ",
            " dow ",
            " stock market ",
            " wall street ",
            " shares ",
            " stocks ",
            " rally ",
            " sell-off ",
            " selloff ",
            " trading ",
        )
    ):
        cats.add("markets")
    if any(
        has(p)
        for p in (
            " technology ",
            " software ",
            " semiconductor ",
            " chip ",
            " artificial intelligence ",
            " big tech ",
            " apple ",
            " microsoft ",
            " google ",
            " amazon ",
            " meta ",
            " nvidia ",
        )
    ):
        cats.add("tech")
    if any(
        has(p)
        for p in (
            " health care ",
            " healthcare ",
            " pharma ",
            " biotech ",
            " drug ",
            " hospital ",
        )
    ):
        cats.add("healthcare")
    if any(
        has(p)
        for p in (
            " jpmorgan ",
            " goldman ",
            " citigroup ",
            " morgan stanley ",
            " wells fargo ",
        )
    ) or re.search(r"\bbank(ing)?\b", tl):
        cats.add("banking")
    if any(has(p) for p in (" mortgage ", " housing ", " home sales ", " real estate ")):
        cats.add("housing")
    if any(has(p) for p in (" retail ", " consumer spending ", " walmart ", " target ")):
        cats.add("consumer")
    if any(
        has(p)
        for p in (
            " sanctions ",
            " tariff ",
            " trade war ",
            " china ",
            " russia ",
            " ukraine ",
            " middle east ",
        )
    ):
        cats.add("geopolitics")
    if any(
        has(p)
        for p in (
            " lawsuit ",
            " antitrust ",
            " regulators ",
            " regulation ",
            " sec charges ",
            " sec probe ",
            " sec investigation ",
        )
    ) or re.search(r"\bsec\b", tl):
        cats.add("regulation")

    if not cats:
        cats.add("general")
    return sorted(cats)


def enrich_news_item(item: dict[str, Any], universe: dict[str, str] | None = None) -> None:
    """Mutate item with ``categories``, ``tickers``, and ``ticker_companies`` from title + summary + link slug."""
    title = (item.get("title") or "").strip()
    summary = (item.get("summary_text") or "").strip()
    link = (item.get("link") or "").strip()
    blob = matching_text_for_ticker_enrichment(title, summary, link)
    item["categories"] = _infer_categories(blob)
    if universe is None:
        universe, _ = portfolio_ticker_universe()
    tickers, companies = match_tickers_from_universe(blob, universe)
    item["tickers"] = tickers
    item["ticker_companies"] = companies


def _user_agent() -> str:
    try:
        from dotenv import load_dotenv
        import os

        load_dotenv()
        return (os.getenv("FINANCE_NEWS_USER_AGENT") or DEFAULT_UA).strip() or DEFAULT_UA
    except Exception:
        return DEFAULT_UA


def _fetch_and_parse_feed(source_name: str, url: str) -> tuple[list[dict[str, Any]], str | None]:
    """Return (items, error_message_or_none). RSS body only; HTML snippet fetch happens in ``collect_digest``."""
    headers = {
        "User-Agent": _user_agent(),
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }
    try:
        r = requests.get(url, headers=headers, timeout=25)
        r.raise_for_status()
    except requests.RequestException as exc:
        return [], f"{source_name}: {exc}"

    parsed = feedparser.parse(r.content)
    items: list[dict[str, Any]] = []
    for entry in getattr(parsed, "entries", []) or []:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        pub = (
            entry.get("published")
            or entry.get("updated")
            or entry.get("pubDate")
            or ""
        )
        if isinstance(pub, str):
            pub = pub.strip()
        else:
            pub = str(pub) if pub else ""
        if not title and not link:
            continue
        summary_text = _rss_entry_combined_plain_text(entry)
        items.append(
            {
                "title": title,
                "link": link,
                "published_raw": pub,
                "summary_text": summary_text,
                "source_feed": source_name,
                "feed_url": url,
            }
        )
    if not items and getattr(parsed, "bozo", False):
        return [], f"{source_name}: feed parse warning ({getattr(parsed, 'bozo_exception', '')})"
    return items, None


def _dedupe_key(item: dict[str, Any]) -> str:
    link = (item.get("link") or "").strip()
    title = (item.get("title") or "").strip()
    if link:
        return hashlib.sha256(link.encode("utf-8")).hexdigest()[:16]
    return hashlib.sha256(title.encode("utf-8")).hexdigest()[:16]


def collect_digest(
    feeds: list[tuple[str, str]] | None = None,
    max_items: int = 50,
) -> dict[str, Any]:
    """
    Fetch all feeds, merge, dedupe by link/title hash, cap at max_items.
    """
    feeds = feeds or DEFAULT_FEEDS
    batches: list[list[dict[str, Any]]] = []
    errors: list[str] = []

    for source_name, url in feeds:
        batch, err = _fetch_and_parse_feed(source_name, url)
        if err:
            errors.append(err)
        batches.append(batch)

    # Round-robin so the max_items cap is not filled by only the first feed.
    all_items: list[dict[str, Any]] = []
    if batches:
        max_len = max(len(b) for b in batches)
        for i in range(max_len):
            for b in batches:
                if i < len(b):
                    all_items.append(b[i])

    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for it in all_items:
        k = _dedupe_key(it)
        if k in seen:
            continue
        seen.add(k)
        unique.append(it)
        if len(unique) >= max_items:
            break

    _fill_article_snippets_for_items(
        unique,
        _max_article_snippet_fetches_per_digest(),
        priority_urls=_snippet_fetch_priority_urls_from_db(unique),
    )

    universe, ticker_stats = portfolio_ticker_universe()
    for it in unique:
        enrich_news_item(it, universe)

    generated_at = datetime.now(timezone.utc).isoformat()
    return {
        "generated_at_utc": generated_at,
        "feed_count": len(feeds),
        "item_count": len(unique),
        "errors": errors,
        "items": unique,
        "enrichment": "keywords_v1",
        "ticker_match_source": "portfolio",
        "held_tickers_count": ticker_stats["unique_for_matching"],
        "portfolio_ticker_stats": ticker_stats,
    }


def render_markdown(digest: dict[str, Any]) -> str:
    lines = [
        "# Daily news digest (POC)",
        "",
        f"Generated (UTC): `{digest.get('generated_at_utc', '')}`",
        f"Items: **{digest.get('item_count', 0)}**",
        "",
    ]
    errs = digest.get("errors") or []
    if errs:
        lines.extend(["## Feed notes", ""])
        for e in errs:
            lines.append(f"- {e}")
        lines.append("")
    lines.extend(["## Headlines", ""])
    for i, it in enumerate(digest.get("items") or [], start=1):
        title = it.get("title") or "(no title)"
        link = it.get("link") or ""
        src = it.get("source_feed") or ""
        cats = it.get("categories") or []
        syms = it.get("tickers") or []
        tc = it.get("ticker_companies") or {}
        meta_parts: list[str] = []
        if cats:
            meta_parts.append("categories: " + ", ".join(cats))
        if syms:
            tick_bits = []
            for s in syms:
                name = tc.get(s) if isinstance(tc, dict) else None
                tick_bits.append(f"{s} ({name})" if name else s)
            meta_parts.append("tickers: " + ", ".join(tick_bits))
        suffix = ""
        if meta_parts:
            suffix = " — " + "; ".join(meta_parts)
        if link:
            lines.append(f"{i}. [{title}]({link}) — *{src}*{suffix}")
        else:
            lines.append(f"{i}. {title} — *{src}*{suffix}")
    lines.append("")
    lines.append("---")
    lines.append("*Automated RSS aggregation only; not investment advice.*")
    lines.append("")
    return "\n".join(lines)


def retag_stored_articles_for_local_date(local_date: str) -> int:
    """
    Re-run portfolio ticker matching on all DB rows whose ``first_seen_at_utc`` falls on
    ``local_date`` (``YYYY-MM-DD`` in ``NEWS_DIGEST_TZ``). Updates ``tickers_json`` /
    ``ticker_companies_json`` when mentions match the **current** holdings universe.
    """
    import db_manager

    universe, _ = portfolio_ticker_universe()
    rows = db_manager.list_news_digest_articles_for_local_date(local_date)
    if not rows:
        return 0
    processed = 0
    for row in rows:
        title = (row.get("title") or "").strip()
        summary = (row.get("summary") or "").strip()
        link = (row.get("link") or row.get("url") or "").strip()
        blob = matching_text_for_ticker_enrichment(title, summary, link)
        tickers, companies = match_tickers_from_universe(blob, universe)
        url = row.get("url") or ""
        if not url:
            continue
        db_manager.update_news_digest_article_tickers(url, tickers, companies)
        processed += 1
    return processed


def _retag_recent_local_days_after_digest() -> None:
    """After a digest write, refresh ticker badges for today and yesterday (local digest clock)."""
    tz = _schedule_tz()
    today = datetime.now(tz).date()
    for delta in (0, 1):
        d = (today - timedelta(days=delta)).isoformat()
        try:
            count = retag_stored_articles_for_local_date(d)
            if count:
                _LOG.info("news_digest: retagged portfolio tickers for %s (%d article(s))", d, count)
        except Exception as exc:
            _LOG.warning("news_digest: retag tickers for %s failed: %s", d, exc)


def _backfill_null_summaries_after_digest(budget: int | None = None) -> int:
    """
    Fetch HTML snippets for recent DB articles that still have no summary.
    This covers articles that fell out of the current digest's ``max_items`` cap.
    Returns the number of summaries filled.
    """
    if not _article_snippet_fetch_enabled():
        return 0
    import db_manager

    max_fetches = budget if budget is not None else _max_article_snippet_fetches_per_digest()
    rows = db_manager.recent_news_digest_articles_with_null_summary(days=2)
    if not rows:
        return 0
    filled = 0
    for row in rows:
        if filled >= max_fetches:
            break
        url = (row.get("url") or "").strip()
        if not url:
            continue
        snippet = _fetch_article_snippet_from_url(url)
        if snippet:
            db_manager.update_news_digest_article_summary(url, snippet)
            filled += 1
    if filled:
        _LOG.info("news_digest: backfilled %d null summary/summaries from HTML snippets", filled)
    return filled


def write_outputs(digest: dict[str, Any], out_dir: Path | None = None) -> tuple[Path, Path]:
    out_dir = out_dir or OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "latest.json"
    md_path = out_dir / "latest.md"
    json_path.write_text(json.dumps(digest, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(digest), encoding="utf-8")
    try:
        import db_manager

        n = db_manager.upsert_news_digest_articles_from_digest(digest)
        _LOG.info("news_digest_articles: upserted %d row(s)", n)
        _backfill_null_summaries_after_digest()
        _retag_recent_local_days_after_digest()
        pruned = db_manager.prune_news_digest_articles()
        if pruned:
            _LOG.info("news_digest_articles: pruned %d row(s) (retention)", pruned)
    except Exception as exc:
        _LOG.warning("news_digest_articles upsert skipped: %s", exc)
    return json_path, md_path


def run_daily_digest() -> tuple[Path, Path]:
    digest = collect_digest()
    return write_outputs(digest)


def run_daily_digest_locked() -> tuple[Path, Path]:
    """Serialize digest generation (scheduler + manual refresh)."""
    with _digest_run_lock:
        return run_daily_digest()


def _schedule_tz() -> ZoneInfo:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass
    name = (os.getenv("NEWS_DIGEST_TZ") or "America/New_York").strip()
    try:
        return ZoneInfo(name)
    except Exception:
        _LOG.warning("Invalid NEWS_DIGEST_TZ=%r; using UTC", name)
        return ZoneInfo("UTC")


def _schedule_hour_minute() -> tuple[int, int]:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass
    raw = (os.getenv("NEWS_DIGEST_HOUR") or "6").strip()
    try:
        h = int(raw.split(":", 1)[0])
    except ValueError:
        h = 6
    h = max(0, min(23, h))
    return h, 0


def _schedule_window_minutes() -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass
    try:
        w = int((os.getenv("NEWS_DIGEST_WINDOW_MINUTES") or "5").strip())
    except ValueError:
        w = 5
    return max(1, min(59, w))


def _parse_generated_at_utc(s: str) -> datetime | None:
    if not s or not isinstance(s, str):
        return None
    t = s.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def load_latest_digest() -> dict[str, Any] | None:
    path = OUTPUT_DIR / "latest.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def digest_fresh_for_today() -> bool:
    """True if latest.json exists and was generated on today's calendar date in NEWS_DIGEST_TZ."""
    data = load_latest_digest()
    if not data:
        return False
    dt = _parse_generated_at_utc(str(data.get("generated_at_utc") or ""))
    if dt is None:
        return False
    tz = _schedule_tz()
    local_date = dt.astimezone(tz).date()
    today = datetime.now(tz).date()
    return local_date == today


def in_scheduled_run_window() -> bool:
    """True during the configured local clock window starting at NEWS_DIGEST_HOUR:00."""
    tz = _schedule_tz()
    now = datetime.now(tz)
    hour, minute = _schedule_hour_minute()
    window = _schedule_window_minutes()
    if now.hour != hour:
        return False
    return now.minute < window


def maybe_run_on_startup() -> bool:
    """If today's digest is missing, run once (catch-up when the app was down at schedule time)."""
    if digest_fresh_for_today():
        return False
    try:
        run_daily_digest_locked()
        _LOG.info("news digest: ran on startup (catch-up)")
        return True
    except Exception as exc:
        _LOG.warning("news digest startup run failed: %s", exc)
        return False


def maybe_run_at_scheduled_time() -> bool:
    """Run at most once per local day while the app is up, during the morning window."""
    if not in_scheduled_run_window():
        return False
    if digest_fresh_for_today():
        return False
    try:
        run_daily_digest_locked()
        _LOG.info("news digest: ran at scheduled window")
        return True
    except Exception as exc:
        _LOG.warning("news digest scheduled run failed: %s", exc)
        return False
