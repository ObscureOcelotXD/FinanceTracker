"""Classify tickers as stock / etf / mutual_fund for UI filtering (not storage)."""
from __future__ import annotations

import datetime
from typing import Any, Iterable, Optional

import pandas as pd
import requests

from services import db_manager

# US mutual-fund tickers are almost always 5 letters ending in X (FXAIX, VTSAX, …).
_MUTUAL_FUND_TICKER_RE = __import__("re").compile(r"^[A-Z]{4}X$")

KNOWN_MUTUAL_FUNDS = frozenset(
    {
        "FXAIX",
        "VTSAX",
        "VFIAX",
        "FSKAX",
        "FZROX",
        "SWTSX",
        "SWPPX",
        "VTSMX",
        "DFIEX",
        "FFRHX",
        "FTIHX",
        "FXNAX",
        "VBTLX",
        "VWENX",
        "VIMAX",
        "VSMAX",
        "VTIAX",
    }
)

KNOWN_ETFS = frozenset(
    {
        "VTI",
        "VOO",
        "IVV",
        "SPY",
        "QQQ",
        "SCHD",
        "SCHB",
        "ITOT",
        "IWM",
        "DIA",
        "VEA",
        "VWO",
        "BND",
        "AGG",
        "GLD",
        "SLV",
        "ARKK",
        "XLF",
        "XLK",
        "XLE",
    }
)

SecurityType = str  # "stock" | "etf" | "mutual_fund"


def _today_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def looks_like_mutual_fund_ticker(ticker: str) -> bool:
    sym = (ticker or "").strip().upper()
    if not sym:
        return False
    if sym in KNOWN_MUTUAL_FUNDS:
        return True
    return bool(_MUTUAL_FUND_TICKER_RE.match(sym))


def looks_like_etf_ticker(ticker: str) -> bool:
    sym = (ticker or "").strip().upper()
    return sym in KNOWN_ETFS


def _from_etf_source_registry(ticker: str) -> Optional[SecurityType]:
    """Use ETF Source Registry URL/path hints when present."""
    try:
        from api import etf_breakdown

        # Ensures default VTI/FXAIX/… rows exist for URL-based classification.
        etf_breakdown.is_tracked_etf(ticker)
    except Exception:
        pass
    row = db_manager.get_etf_source(ticker)
    if not row:
        return None
    url = str(row.get("url") or "").lower()
    source_type = str(row.get("source_type") or "").lower()
    if "mutualfund" in url or "mutual_fund" in url or "mutual-fund" in url:
        return "mutual_fund"
    if "etf" in url or "etf" in source_type:
        return "etf"
    # Registry hit with no clear path — treat as ETF (legacy registry name).
    return "etf"


def _finnhub_get(path: str, symbol: str) -> dict:
    from api.finnhub_api import _get_finnhub_api_key

    key = _get_finnhub_api_key()
    if not key:
        return {}
    try:
        resp = requests.get(
            f"https://finnhub.io/api/v1{path}",
            params={"symbol": symbol, "token": key},
            timeout=12,
        )
        if resp.status_code != 200:
            return {}
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _profile_nonempty(data: dict) -> bool:
    if not data:
        return False
    # Finnhub wraps some profiles under "profile"
    profile = data.get("profile") if isinstance(data.get("profile"), dict) else data
    if not isinstance(profile, dict) or not profile:
        return False
    return bool(profile.get("name") or profile.get("symbol") or profile.get("ticker") or profile.get("isin"))


def _from_polygon(ticker: str) -> Optional[SecurityType]:
    try:
        from api import polygon_api

        data = polygon_api.fetch_ticker_profile(ticker)
    except Exception:
        return None
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, dict):
        return None
    type_code = str(results.get("type") or "").upper()
    if type_code in {"ETF", "ETN", "ETP"}:
        return "etf"
    if type_code in {"FUND", "MUTUAL", "MF"}:
        return "mutual_fund"
    # Polygon uses CS for common stock; UNIT etc. leave for later checks
    if type_code == "CS":
        return "stock"
    name = str(results.get("name") or "").lower()
    if "etf" in name or "exchange traded" in name:
        return "etf"
    if "fund" in name and "etf" not in name:
        # Could be mutual fund or closed-end; prefer mutual_fund when ticker looks like one
        if looks_like_mutual_fund_ticker(ticker):
            return "mutual_fund"
    return None


def _from_finnhub(ticker: str) -> Optional[SecurityType]:
    mf = _finnhub_get("/mutual-fund/profile", ticker)
    if _profile_nonempty(mf):
        return "mutual_fund"
    etf = _finnhub_get("/etf/profile", ticker)
    if _profile_nonempty(etf):
        return "etf"
    stock = _finnhub_get("/stock/profile2", ticker)
    if _profile_nonempty(stock):
        return "stock"
    return None


def classify_ticker(ticker: str, *, force_refresh: bool = False) -> SecurityType:
    """
    Return stock | etf | mutual_fund.

    Uses local cache, heuristics, ETF registry, Polygon type, then Finnhub profiles.
    Defaults to stock when unknown so UI filters do not hide unrecognized names.
    """
    sym = (ticker or "").strip().upper()
    if not sym:
        return "stock"

    if not force_refresh:
        cached = db_manager.get_security_type(sym)
        if cached in {"stock", "etf", "mutual_fund"}:
            return cached

    resolved: Optional[SecurityType] = None
    source = "default"

    if looks_like_mutual_fund_ticker(sym):
        resolved, source = "mutual_fund", "heuristic"
    elif looks_like_etf_ticker(sym):
        resolved, source = "etf", "known_list"
    else:
        reg = _from_etf_source_registry(sym)
        if reg:
            resolved, source = reg, "etf_registry"
        else:
            poly = _from_polygon(sym)
            if poly:
                resolved, source = poly, "polygon"
            else:
                fh = _from_finnhub(sym)
                if fh:
                    resolved, source = fh, "finnhub"

    if not resolved:
        resolved, source = "stock", "default"

    db_manager.upsert_security_type(sym, resolved, source=source, updated_at=_today_iso())
    return resolved


def classify_tickers(tickers: Iterable[str], *, force_refresh: bool = False) -> dict[str, SecurityType]:
    out: dict[str, SecurityType] = {}
    for t in tickers:
        sym = str(t or "").strip().upper()
        if not sym or sym in out:
            continue
        out[sym] = classify_ticker(sym, force_refresh=force_refresh)
    return out


def filter_tickers_for_ui(tickers: Iterable[str]) -> list[str]:
    """Drop ETF / mutual-fund tickers when the matching hide toggle is on."""
    hide_mf = db_manager.get_hide_mutual_funds()
    hide_etf = db_manager.get_hide_etfs()
    if not hide_mf and not hide_etf:
        return [str(t).strip().upper() for t in tickers if t]

    types = classify_tickers(tickers)
    kept: list[str] = []
    for t in tickers:
        sym = str(t or "").strip().upper()
        if not sym:
            continue
        kind = types.get(sym, "stock")
        if hide_mf and kind == "mutual_fund":
            continue
        if hide_etf and kind == "etf":
            continue
        kept.append(sym)
    return kept


def filter_holdings_df_for_ui(df: pd.DataFrame, ticker_col: str = "ticker") -> pd.DataFrame:
    """Filter a holdings DataFrame for display according to hide toggles (DB unchanged)."""
    if df is None or df.empty or ticker_col not in df.columns:
        return df
    hide_mf = db_manager.get_hide_mutual_funds()
    hide_etf = db_manager.get_hide_etfs()
    if not hide_mf and not hide_etf:
        return df
    types = classify_tickers(df[ticker_col].dropna().astype(str).tolist())
    mask = []
    for raw in df[ticker_col].tolist():
        sym = str(raw or "").strip().upper()
        kind = types.get(sym, "stock")
        if hide_mf and kind == "mutual_fund":
            mask.append(False)
        elif hide_etf and kind == "etf":
            mask.append(False)
        else:
            mask.append(True)
    return df.loc[mask].reset_index(drop=True)


def security_type_summary(tickers: Optional[Iterable[str]] = None) -> dict[str, Any]:
    if tickers is None:
        tickers = db_manager.get_all_tickers()
    types = classify_tickers(tickers)
    counts = {"stock": 0, "etf": 0, "mutual_fund": 0}
    for kind in types.values():
        counts[kind] = counts.get(kind, 0) + 1
    return {"counts": counts, "types": types}
