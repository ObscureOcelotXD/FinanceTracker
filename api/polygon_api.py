# polygon_api.py
import os
import requests
from dotenv import load_dotenv

# Load .env so the key is available when this module is imported.
load_dotenv()

POLYGON_TICKER_URL = "https://api.polygon.io/v3/reference/tickers/{ticker}"

TYPE_LABELS = {
    "ETF": "ETF",
    "ETN": "ETN",
    "ADRC": "ADR Common Stock",
    "ADRP": "ADR Preferred",
    "ADRR": "ADR Rights",
    "ADRW": "ADR Warrants",
    "PFD": "Preferred Stock",
    "FUND": "Fund",
    "TRUST": "Trust",
    "WRT": "Warrant",
    "RTS": "Rights",
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


def _get_polygon_api_key():
    key = os.getenv("POLYGON_API_KEY")
    if key:
        return key.strip()
    return None


def fetch_ticker_profile(ticker):
    api_key = _get_polygon_api_key()
    if not api_key:
        print(f"[Polygon] Missing API key. Skipping {ticker}.")
        return {}
    params = {
        "apiKey": api_key,
    }
    url = POLYGON_TICKER_URL.format(ticker=ticker.upper())
    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code != 200:
            print(f"[Polygon] {ticker} HTTP {response.status_code}: {response.text[:200]}")
            return {}
        data = response.json()
        print(f"[Polygon] {ticker} profile fetched.")
        return data
    except Exception:
        print(f"[Polygon] {ticker} request failed.")
        return {}


def get_polygon_industry(ticker):
    data = fetch_ticker_profile(ticker)
    if not isinstance(data, dict):
        print(f"[Polygon] {ticker} invalid profile payload.")
        return None
    results = data.get("results") or {}
    if not isinstance(results, dict):
        print(f"[Polygon] {ticker} missing results.")
        return None
    sic = results.get("sic_description")
    if sic:
        print(f"[Polygon] {ticker} sic_description: {sic}")
        return _title_case_label(sic)
    industry = results.get("industry")
    if industry:
        print(f"[Polygon] {ticker} industry: {industry}")
        return _title_case_label(industry)
    sector = results.get("sector")
    if sector:
        print(f"[Polygon] {ticker} sector: {sector}")
        return _title_case_label(sector)
    type_code = results.get("type")
    if type_code and type_code != "CS":
        print(f"[Polygon] {ticker} type: {type_code}")
        return TYPE_LABELS.get(type_code, type_code)
    print(f"[Polygon] {ticker} no industry data.")
    return None
