import sys
import time
import datetime as dt
from pathlib import Path
import requests

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import db_manager

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
YAHOO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
}


def _year_start_end(year):
    start = dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc)
    end = dt.datetime(year + 1, 1, 1, tzinfo=dt.timezone.utc) - dt.timedelta(seconds=1)
    return start, end


def fetch_yahoo_daily_candles(symbol, year):
    start, end = _year_start_end(year)
    url = YAHOO_CHART_URL.format(symbol=symbol)
    params = {
        "period1": int(start.timestamp()),
        "period2": int(end.timestamp()),
        "interval": "1d",
        "events": "div,splits",
        "includePrePost": "false",
    }
    resp = requests.get(url, params=params, headers=YAHOO_HEADERS, timeout=30)
    data = resp.json()
    try:
        result = data["chart"]["result"][0]
        timestamps = result.get("timestamp", [])
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        return list(zip(timestamps, closes)), None
    except (KeyError, IndexError, TypeError):
        return None, data


def backfill_daily_prices(year=2025, pause_seconds=0.8):
    tickers = db_manager.get_all_tickers()
    print(f"[Yahoo] Backfilling daily prices for {len(tickers)} tickers ({year})")

    for ticker in tickers:
        candles, error = fetch_yahoo_daily_candles(ticker, year)
        if error:
            print(f"[Yahoo] {ticker}: error {error}")
            time.sleep(pause_seconds)
            continue
        if not candles:
            print(f"[Yahoo] {ticker}: no daily data returned.")
            time.sleep(pause_seconds)
            continue
        for ts, close in candles:
            if close is None:
                continue
            date_str = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).date().isoformat()
            db_manager.upsert_stock_price(ticker, date_str, float(close))
        print(f"[Yahoo] {ticker}: stored {len(candles)} daily closes.")
        time.sleep(pause_seconds)


if __name__ == "__main__":
    backfill_daily_prices()
