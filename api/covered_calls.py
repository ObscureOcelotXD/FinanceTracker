"""Covered call helpers: coverable holdings, open-position metrics, expiration calendar."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from services import db_manager

ASSIGNMENT_NEAR_PCT = 2.0


def _parse_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def compute_covered_call_metrics(
    *,
    strike: float,
    expiration_date: Any,
    contracts: int,
    premium_received: float,
    current_price: Optional[float],
    as_of: Optional[date] = None,
    near_pct: float = ASSIGNMENT_NEAR_PCT,
) -> dict[str, Any]:
    """Risk snapshot for one open covered call."""
    today = as_of or date.today()
    exp = _parse_date(expiration_date)
    strike_val = float(strike or 0)
    contract_count = max(int(contracts or 0), 0)
    premium = float(premium_received or 0)
    shares_at_risk = contract_count * 100
    notional = strike_val * shares_at_risk if strike_val and shares_at_risk else None

    dte = None
    if exp:
        dte = (exp - today).days

    price = float(current_price) if current_price is not None else None
    otm_itm_pct = None
    moneyness_label = "No price"
    assignment_warning = False
    assignment_reason = None

    if price is not None and price > 0 and strike_val:
        # Positive = OTM (strike above spot); negative = ITM.
        otm_itm_pct = ((strike_val - price) / price) * 100.0
        if otm_itm_pct > 0.5:
            moneyness_label = f"{otm_itm_pct:.1f}% OTM"
        elif otm_itm_pct < -0.5:
            moneyness_label = f"{abs(otm_itm_pct):.1f}% ITM"
        else:
            moneyness_label = "At the money"

        if price >= strike_val:
            assignment_warning = True
            assignment_reason = "In the money"
        elif price >= strike_val * (1 - near_pct / 100.0):
            assignment_warning = True
            assignment_reason = f"Within {near_pct:.0f}% of strike"

    premium_yield_pct = None
    if notional and notional > 0:
        premium_yield_pct = (premium / notional) * 100.0

    return {
        "current_price": price,
        "otm_itm_pct": otm_itm_pct,
        "moneyness_label": moneyness_label,
        "days_to_expiration": dte,
        "shares_at_risk": shares_at_risk,
        "premium_yield_pct": premium_yield_pct,
        "assignment_warning": assignment_warning,
        "assignment_reason": assignment_reason,
    }


def enrich_covered_call_row(row: dict[str, Any], prices: dict[str, float], as_of: Optional[date] = None) -> dict[str, Any]:
    ticker = str(row.get("ticker") or "").upper()
    price = prices.get(ticker)
    metrics = compute_covered_call_metrics(
        strike=row.get("strike"),
        expiration_date=row.get("expiration_date"),
        contracts=row.get("contracts"),
        premium_received=row.get("premium_received"),
        current_price=price,
        as_of=as_of,
    )
    out = dict(row)
    out.update(metrics)
    return out


def get_open_covered_calls_enriched(as_of: Optional[date] = None) -> list[dict[str, Any]]:
    df = db_manager.get_covered_calls(status="open")
    if df.empty:
        return []
    tickers = [str(t).upper() for t in df["ticker"].tolist()]
    prices = db_manager.get_latest_stock_prices_map(tickers)
    rows = df.to_dict("records")
    enriched = [enrich_covered_call_row(r, prices, as_of=as_of) for r in rows]
    enriched.sort(key=lambda r: (r.get("expiration_date") or "", r.get("ticker") or ""))
    return enriched


def build_expiration_calendar(open_calls: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
    """
    Group open covered calls by expiration date for calendar display.
    Returns list of {expiration_date, days_to_expiration, items: [enriched rows]}.
    """
    calls = open_calls if open_calls is not None else get_open_covered_calls_enriched()
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in calls:
        exp = str(row.get("expiration_date") or "")
        by_date.setdefault(exp, []).append(row)
    calendar = []
    for exp in sorted(by_date.keys()):
        items = by_date[exp]
        dte = items[0].get("days_to_expiration") if items else None
        calendar.append(
            {
                "expiration_date": exp,
                "days_to_expiration": dte,
                "items": items,
            }
        )
    return calendar


def get_coverable_holdings_records(min_shares: int = 100) -> list[dict[str, Any]]:
    from api import security_type as st

    df = db_manager.get_coverable_holdings_by_account(min_shares=min_shares)
    if df.empty:
        return []
    df = st.filter_holdings_df_for_ui(df)
    if df.empty:
        return []
    return df.to_dict("records")
