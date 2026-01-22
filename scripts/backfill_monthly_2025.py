import os
import sys
import time
import datetime as dt
from pathlib import Path
import requests
import json
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

load_dotenv()

import db_manager

FINNHUB_CANDLE_URL = "https://finnhub.io/api/v1/stock/candle"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

YAHOO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
}


def _get_finnhub_api_key():
    key = os.getenv("FINNHUB_API_KEY")
    if key:
        return key.strip()
    return None


def _year_start_unix(year):
    return int(dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc).timestamp())


def _year_end_unix(year):
    end = dt.datetime(year + 1, 1, 1, tzinfo=dt.timezone.utc)
    return int(end.timestamp()) - 1


def fetch_daily_candles(ticker, year):
    api_key = _get_finnhub_api_key()
    if not api_key:
        raise RuntimeError("FINNHUB_API_KEY is not set.")

    start_ts = _year_start_unix(year)
    end_ts = _year_end_unix(year)
    params = {
        "symbol": ticker,
        "resolution": "D",
        "from": start_ts,
        "to": end_ts,
        "token": api_key,
    }
    resp = requests.get(FINNHUB_CANDLE_URL, params=params, timeout=30)
    data = _safe_json(resp)
    if data.get("s") != "ok":
        return None, data
    return data, None


def fetch_yahoo_daily_candles(ticker, year):
    start_ts = _year_start_unix(year)
    end_ts = _year_end_unix(year)
    url = YAHOO_CHART_URL.format(symbol=ticker)
    params = {
        "period1": start_ts,
        "period2": end_ts,
        "interval": "1d",
        "events": "div,splits",
        "includePrePost": "false",
    }
    resp = requests.get(url, params=params, headers=YAHOO_HEADERS, timeout=30)
    data = _safe_json(resp)
    try:
        result = data["chart"]["result"][0]
        timestamps = result.get("timestamp", [])
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        candles = {"t": timestamps, "c": closes, "s": "ok"}
        return candles, None
    except (KeyError, IndexError, TypeError):
        return None, data


def _safe_json(resp):
    try:
        return resp.json()
    except json.JSONDecodeError:
        return {"error": "Non-JSON response", "status": resp.status_code, "text": resp.text[:200]}


def pick_first_trading_day_closes(candles, year):
    """
    Use daily candles to find the first trading day in each month and
    store the close price for that day.
    """
    results = {}
    timestamps = candles.get("t", [])
    closes = candles.get("c", [])
    for ts, close in zip(timestamps, closes):
        date = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).date()
        if date.year != year:
            continue
        month_key = (date.year, date.month)
        if month_key not in results:
            results[month_key] = (date, round(float(close), 2))
    output = []
    for (_, _), (date, close) in sorted(results.items()):
        output.append((date.isoformat(), close))
    return output


def backfill_monthly_prices(year=2025, pause_seconds=0.8):
    tickers = db_manager.get_all_tickers()
    print(f"[Finnhub] Backfilling monthly prices for {len(tickers)} tickers ({year})")

    for ticker in tickers:
        try:
            candles, error = fetch_daily_candles(ticker, year)
            source = "Finnhub"
            if error:
                # Fallback to Yahoo for free-tier Finnhub limitations.
                if "access" in str(error).lower() or "not set" in str(error).lower():
                    candles, error = fetch_yahoo_daily_candles(ticker, year)
                    source = "Yahoo"
                if error:
                    print(f"[{source}] {ticker}: error {error}")
                    time.sleep(pause_seconds)
                    continue
            monthly = pick_first_trading_day_closes(candles, year)
            if not monthly:
                print(f"[{source}] {ticker}: no daily data returned.")
                time.sleep(pause_seconds)
                continue
            for date_str, close in monthly:
                db_manager.upsert_stock_price(ticker, date_str, close)
            print(f"[{source}] {ticker}: upserted {len(monthly)} monthly rows.")
        except Exception as exc:
            print(f"[Backfill] {ticker}: exception {exc}")
        time.sleep(pause_seconds)


if __name__ == "__main__":
    backfill_monthly_prices()
