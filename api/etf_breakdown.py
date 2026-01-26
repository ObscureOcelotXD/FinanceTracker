import csv
import datetime as dt
import re
from io import StringIO

import pandas as pd
import requests

import db_manager
from api import polygon_api

DEFAULT_ETF_SOURCES = {
    "VTI": {
        "source_type": "schwab_portfolio",
        "url": "https://www.schwab.wallst.com/Prospect/Research/etfs/portfolio.asp?symbol=VTI",
    },
    "VTSAX": {
        "source_type": "schwab_portfolio",
        "url": "https://www.schwab.wallst.com/Prospect/Research/mutualfunds/portfolio.asp?symbol=VTSAX",
    },
    "VOO": {
        "source_type": "schwab_portfolio",
        "url": "https://www.schwab.wallst.com/Prospect/Research/etfs/portfolio.asp?symbol=VOO",
    },
    "SCHD": {
        "source_type": "schwab_portfolio",
        "url": "https://www.schwab.wallst.com/Prospect/Research/etfs/portfolio.asp?symbol=SCHD",
    },
    "FXAIX": {
        "source_type": "schwab_portfolio",
        "url": "https://www.schwab.wallst.com/Prospect/Research/mutualfunds/portfolio.asp?symbol=FXAIX",
    },
    "DFIEX": {
        "source_type": "schwab_portfolio",
        "url": "https://www.schwab.wallst.com/Prospect/Research/mutualfunds/portfolio.asp?symbol=DFIEX",
    },
}


TITLE_CASE_EXCEPTIONS = {
    "and",
    "or",
    "the",
    "of",
    "in",
    "for",
    "to",
    "a",
    "an",
}


def _title_case_label(value):
    if not value:
        return value
    text = str(value).strip()
    if not text:
        return text
    parts = text.replace("/", " / ").split()
    formatted = []
    for idx, part in enumerate(parts):
        lower = part.lower()
        if lower in TITLE_CASE_EXCEPTIONS and idx != 0:
            formatted.append(lower)
            continue
        if part.isupper() and len(part) <= 4:
            formatted.append(part)
            continue
        formatted.append(part.capitalize())
    return " ".join(formatted).replace(" / ", "/")


def _parse_weight(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("%", "")
    try:
        return float(text)
    except ValueError:
        return None


def _infer_columns(rows):
    if not rows:
        return None, None
    keys = {k.lower(): k for k in rows[0].keys()}
    sector_key = None
    weight_key = None
    for candidate in keys:
        if "sector" in candidate or "industry" in candidate:
            sector_key = keys[candidate]
            break
    for candidate in keys:
        if "weight" in candidate or "percent" in candidate or "percentage" in candidate:
            weight_key = keys[candidate]
            break
    return sector_key, weight_key


def _fetch_provider_csv(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36",
        "Accept": "text/csv,application/json,text/plain,*/*",
    }
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    text = resp.text
    reader = csv.DictReader(StringIO(text))
    return list(reader)


def _fetch_yahoo_sector_weights(symbol):
    url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
    params = {"modules": "topHoldings"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36",
        "Accept": "application/json,text/plain,*/*",
    }
    resp = requests.get(url, params=params, headers=headers, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    result = payload.get("quoteSummary", {}).get("result", [])
    if not result:
        return {}
    top_holdings = result[0].get("topHoldings", {})
    sector_weightings = top_holdings.get("sectorWeightings", [])
    if not sector_weightings:
        return {}
    weights = {}
    for entry in sector_weightings:
        if not isinstance(entry, dict):
            continue
        for key, value in entry.items():
            if isinstance(value, dict):
                value = value.get("raw")
            weight = _parse_weight(value)
            if weight is None:
                continue
            sector = _title_case_label(key.replace("_", " "))
            weights[sector] = weights.get(sector, 0.0) + weight
    total = sum(weights.values())
    if total <= 0:
        return {}
    return {sector: value / total for sector, value in weights.items()}


def _parse_schwab_sector_table(html):
    try:
        tables = pd.read_html(StringIO(html))
    except ValueError:
        tables = []
    for table in tables:
        columns = [str(col).strip().lower() for col in table.columns]
        if "sector" in columns:
            for col in columns:
                if "assets" in col or "net assets" in col:
                    sector_col = table.columns[columns.index("sector")]
                    weight_col = table.columns[columns.index(col)]
                    weights = {}
                    for _, row in table.iterrows():
                        sector = _title_case_label(row.get(sector_col))
                        weight = _parse_weight(row.get(weight_col))
                        if sector and weight is not None:
                            weights[sector] = weights.get(sector, 0.0) + weight
                    total = sum(weights.values())
                    if total > 0:
                        return {sector: value / total for sector, value in weights.items()}
    return {}


def _parse_schwab_sector_text(text):
    pattern = re.compile(r"•\s*([A-Za-z0-9&/.\-\s]+)\s*\|?\s*([0-9]+(?:\.[0-9]+)?)%")
    matches = pattern.findall(text)
    if not matches:
        return {}
    weights = {}
    for sector_raw, value in matches:
        sector = _title_case_label(sector_raw.replace("Disc", "Discretionary").strip())
        weight = _parse_weight(value)
        if sector and weight is not None:
            weights[sector] = weights.get(sector, 0.0) + weight
    total = sum(weights.values())
    if total <= 0:
        return {}
    return {sector: value / total for sector, value in weights.items()}


def _fetch_schwab_sector_weights(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    html = resp.text
    weights = _parse_schwab_sector_table(html)
    if weights:
        return weights
    return _parse_schwab_sector_text(html)


def _infer_source_type(url):
    if not url:
        return None
    lowered = url.lower()
    if "schwab.wallst.com" in lowered:
        return "schwab_portfolio"
    if lowered.endswith(".csv") or "csv" in lowered:
        return "provider_csv"
    if "query2.finance.yahoo.com" in lowered:
        return "yahoo_top_holdings"
    return None


def _ensure_default_sources():
    sources_df = db_manager.get_etf_sources()
    if sources_df.empty:
        for symbol, source in DEFAULT_ETF_SOURCES.items():
            db_manager.upsert_etf_source(symbol, source["source_type"], source.get("url"))


def _auto_lookup_source(symbol):
    symbol = symbol.upper()
    etf_url = f"https://www.schwab.wallst.com/Prospect/Research/etfs/portfolio.asp?symbol={symbol}"
    mf_url = f"https://www.schwab.wallst.com/Prospect/Research/mutualfunds/portfolio.asp?symbol={symbol}"
    for url in (etf_url, mf_url):
        try:
            weights = _fetch_schwab_sector_weights(url)
            if weights:
                return {"source_type": "schwab_portfolio", "url": url}
        except Exception:
            continue
    try:
        weights = _fetch_yahoo_sector_weights(symbol)
        if weights:
            return {"source_type": "yahoo_top_holdings", "url": None}
    except Exception:
        pass
    return None


def resolve_source(symbol, url=None, source_type=None, allow_auto_lookup=True):
    symbol = symbol.upper()
    if url and not source_type:
        source_type = _infer_source_type(url)
    if source_type:
        db_manager.upsert_etf_source(symbol, source_type, url)
        return {"symbol": symbol, "source_type": source_type, "url": url}
    if allow_auto_lookup:
        looked_up = _auto_lookup_source(symbol)
        if looked_up:
            db_manager.upsert_etf_source(symbol, looked_up["source_type"], looked_up.get("url"))
            return {"symbol": symbol, **looked_up}
    db_manager.upsert_etf_source(symbol, "yahoo_top_holdings", None)
    return {"symbol": symbol, "source_type": "yahoo_top_holdings", "url": None}


def _extract_sector_weights(rows, sector_key=None, weight_key=None):
    if not rows:
        return {}
    if sector_key is None or weight_key is None:
        inferred_sector, inferred_weight = _infer_columns(rows)
        sector_key = sector_key or inferred_sector
        weight_key = weight_key or inferred_weight
    if not sector_key or not weight_key:
        return {}
    weights = {}
    for row in rows:
        sector = _title_case_label(row.get(sector_key))
        weight = _parse_weight(row.get(weight_key))
        if sector and weight is not None:
            weights[sector] = weights.get(sector, 0.0) + weight
    total = sum(weights.values())
    if total <= 0:
        return {}
    return {sector: value / total for sector, value in weights.items()}


def _fallback_single_sector(symbol):
    sector = polygon_api.get_polygon_industry(symbol)
    if not sector:
        return {}
    return {_title_case_label(sector): 1.0}


def _is_stale(updated_at, refresh_days):
    if not updated_at:
        return True
    try:
        updated = dt.datetime.fromisoformat(updated_at)
    except ValueError:
        return True
    return (dt.datetime.utcnow() - updated) > dt.timedelta(days=refresh_days)


def get_sector_breakdown(symbol, refresh_days=7):
    symbol = symbol.upper()
    _ensure_default_sources()
    cached = db_manager.get_etf_sector_breakdown(symbol)
    updated_at = None
    if not cached.empty:
        updated_at = cached["updated_at"].dropna().max()
        if not _is_stale(updated_at, refresh_days):
            return dict(zip(cached["sector"], cached["weight"]))

    source = db_manager.get_etf_source(symbol)
    if source is None:
        resolve_source(symbol, allow_auto_lookup=True)
        source = db_manager.get_etf_source(symbol)
    weights = {}
    if source and source.get("source_type") == "provider_csv" and source.get("url"):
        try:
            rows = _fetch_provider_csv(source["url"])
            weights = _extract_sector_weights(
                rows,
                sector_key=source.get("sector_column"),
                weight_key=source.get("weight_column"),
            )
        except Exception:
            weights = {}
    elif source and source.get("source_type") == "schwab_portfolio" and source.get("url"):
        try:
            weights = _fetch_schwab_sector_weights(source["url"])
        except Exception:
            weights = {}
    elif source and source.get("source_type") == "yahoo_top_holdings":
        try:
            weights = _fetch_yahoo_sector_weights(symbol)
        except Exception:
            weights = {}

    if not weights:
        try:
            weights = _fetch_yahoo_sector_weights(symbol)
        except Exception:
            weights = {}

    if not weights:
        weights = _fallback_single_sector(symbol)

    if weights:
        db_manager.clear_etf_sector_breakdown(symbol)
        now = dt.datetime.utcnow().isoformat()
        for sector, weight in weights.items():
            db_manager.upsert_etf_sector_breakdown(
                symbol,
                sector,
                float(weight),
                source=(source.get("url") if source and source.get("url") else "Yahoo"),
                updated_at=now,
            )
        return weights

    if not cached.empty:
        return dict(zip(cached["sector"], cached["weight"]))
    return {}


def is_tracked_etf(symbol):
    _ensure_default_sources()
    return db_manager.get_etf_source(symbol.upper()) is not None
