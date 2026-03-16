"""
Quant risk summary: volatility, drawdown, beta, sector concentration.
Used by the /quant/risk_summary Flask route.
"""
import math
import datetime as dt
from typing import Any, Dict, Optional

import pandas as pd
import requests

import db_manager


def fetch_yahoo_history(symbol: str, start_date: dt.datetime, end_date: dt.datetime):
    """Return (list of (ts, close), error_data or None)."""
    url = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {
        "period1": int(start_date.timestamp()),
        "period2": int(end_date.timestamp()),
        "interval": "1d",
        "events": "div,splits",
        "includePrePost": "false",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json,text/plain,*/*",
    }
    resp = requests.get(url.format(symbol=symbol), params=params, headers=headers, timeout=20)
    data = resp.json()
    try:
        result = data["chart"]["result"][0]
        timestamps = result.get("timestamp", [])
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
    except (KeyError, IndexError, TypeError):
        return None, data
    return list(zip(timestamps, closes)), None


def ensure_benchmark_history(symbol: str, start_date: dt.datetime, end_date: dt.datetime) -> pd.DataFrame:
    """Ensure we have benchmark prices in DB for the range; return series."""
    series = db_manager.get_benchmark_price_series(symbol)
    if not series.empty:
        last_date = series["date"].max()
        if last_date >= end_date - dt.timedelta(days=2):
            return series
    candles, error = fetch_yahoo_history(symbol, start_date, end_date)
    if error:
        return series
    for ts, close in candles or []:
        if close is None:
            continue
        date_str = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).date().isoformat()
        db_manager.upsert_benchmark_price(symbol, date_str, float(close), source="Yahoo")
    return db_manager.get_benchmark_price_series(symbol)


def compute_risk_summary() -> Dict[str, Any]:
    """Compute portfolio risk metrics. Returns a dict suitable for jsonify."""
    empty = {
        "volatility_pct": None,
        "max_drawdown_pct": None,
        "beta": None,
        "last_updated": None,
        "fresh": False,
        "top_sector": None,
        "top_sector_pct": None,
        "hhi": None,
        "diversification_ratio": None,
    }
    df = db_manager.get_portfolio_value_history()
    if df.empty or len(df) < 2:
        return empty

    df = df.sort_values("date").copy()
    df["returns"] = df["portfolio_value"].pct_change()
    returns = df["returns"].dropna()
    volatility_raw = None
    volatility = None
    if not returns.empty:
        volatility_raw = float(returns.std() * math.sqrt(252))
        volatility = volatility_raw * 100

    running_max = df["portfolio_value"].cummax()
    drawdown = df["portfolio_value"] / running_max - 1
    max_drawdown = float(drawdown.min() * 100) if not drawdown.empty else None

    start_date = df["date"].min()
    end_date = df["date"].max() + dt.timedelta(days=1)
    last_updated = df["date"].max().date()
    today = dt.datetime.now(dt.timezone.utc).date()
    wd = today.weekday()
    last_business_day = (
        today - dt.timedelta(days=3) if wd == 0
        else today - dt.timedelta(days=2) if wd == 6
        else today - dt.timedelta(days=1) if wd == 5
        else today
    )
    fresh = last_updated >= last_business_day

    top_sector = None
    top_sector_pct = None
    hhi = None
    diversification_ratio = None
    value_df = db_manager.get_value_stocks()
    if not value_df.empty:
        value_df = value_df.copy()
        total_value = value_df["position_value"].sum()
        if total_value > 0:
            value_df["weight"] = value_df["position_value"] / total_value
            try:
                from api import finnhub_api, etf_breakdown
                tickers = value_df["ticker"].tolist()
                sector_map = finnhub_api.get_sector_allocation_map(tickers)
                sector_weights: Dict[str, float] = {}
                for _, row in value_df.iterrows():
                    ticker = row["ticker"]
                    weight = float(row["weight"])
                    if etf_breakdown.is_tracked_etf(ticker):
                        breakdown = etf_breakdown.get_sector_breakdown(ticker, refresh_days=7)
                        if breakdown:
                            for sector, portion in breakdown.items():
                                sector_weights[sector] = sector_weights.get(sector, 0.0) + weight * float(portion)
                        continue
                    sector = sector_map.get(ticker) or "Unknown"
                    sector_weights[sector] = sector_weights.get(sector, 0.0) + weight
                if sector_weights:
                    total_sw = sum(sector_weights.values())
                    if total_sw > 0:
                        normalized = {k: v / total_sw for k, v in sector_weights.items()}
                        top_sector = max(normalized, key=normalized.get)
                        top_sector_pct = float(normalized[top_sector] * 100)
                        hhi = float(sum(v**2 for v in normalized.values()))
            except Exception:
                pass
        price_df = db_manager.get_stock_prices_df()
        if not price_df.empty and "weight" in value_df.columns and volatility_raw is not None:
            price_df = price_df.copy()
            price_df["date"] = pd.to_datetime(price_df["date"])
            price_df["closing_price"] = pd.to_numeric(price_df["closing_price"], errors="coerce")
            price_df = price_df.sort_values(["ticker", "date"])
            price_df["returns"] = price_df.groupby("ticker")["closing_price"].pct_change()
            vol_by_ticker = price_df.groupby("ticker")["returns"].std() * math.sqrt(252)
            vol_by_ticker = vol_by_ticker.dropna()
            if not vol_by_ticker.empty:
                weights = value_df.set_index("ticker")["weight"]
                aligned = vol_by_ticker.to_frame("vol").join(weights.to_frame("weight"), how="inner")
                if not aligned.empty:
                    weighted_avg_vol = float((aligned["vol"] * aligned["weight"]).sum())
                    if weighted_avg_vol > 0:
                        diversification_ratio = float(volatility_raw / weighted_avg_vol)

    beta = None
    spy = ensure_benchmark_history("SPY", start_date, end_date)
    if not spy.empty:
        spy = spy.sort_values("date").copy()
        spy["returns"] = spy["closing_price"].pct_change()
        merged = pd.merge(
            df[["date", "returns"]],
            spy[["date", "returns"]].rename(columns={"returns": "spy_returns"}),
            on="date",
            how="inner",
        ).dropna()
        if len(merged) >= 3 and merged["spy_returns"].var() != 0:
            beta = float(merged["returns"].cov(merged["spy_returns"]) / merged["spy_returns"].var())

    def rnd(x: Optional[float], d: int) -> Optional[float]:
        return round(x, d) if x is not None else None

    return {
        "volatility_pct": rnd(volatility, 2),
        "max_drawdown_pct": rnd(max_drawdown, 2),
        "beta": rnd(beta, 2),
        "last_updated": last_updated.isoformat(),
        "fresh": fresh,
        "top_sector": top_sector,
        "top_sector_pct": rnd(top_sector_pct, 2),
        "hhi": rnd(hhi, 4),
        "diversification_ratio": rnd(diversification_ratio, 2),
    }
