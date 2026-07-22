"""Parse and apply holdings / covered-call spreadsheet uploads (CSV or XLSX)."""
from __future__ import annotations

import base64
import csv
import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from services import db_manager

HOLDINGS_REQUIRED = ("ticker", "shares")
HOLDINGS_COLUMNS = ("brokerage", "account", "ticker", "shares", "cost_basis")

COVERED_CALLS_REQUIRED = ("ticker", "strike", "expiration_date")
COVERED_CALLS_COLUMNS = (
    "brokerage",
    "account",
    "ticker",
    "strike",
    "expiration_date",
    "contracts",
    "premium_received",
    "open_date",
    "status",
    "notes",
)

# Canonical app storage / download format (one file for stocks + covered calls).
# cost_basis/premium: stock rows = cost basis; call rows = premium received (cash credit).
PORTFOLIO_COLUMNS = (
    "type",
    "brokerage",
    "account",
    "ticker",
    "shares",
    "cost_basis/premium",
    "strike",
    "expiration_date",
    "contracts",
    "open_date",
    "status",
    "notes",
)

# Verbose: SOFI 09/18/2026 24.00 C
_VERBOSE_OPTION_RE = re.compile(
    r"^([A-Za-z][A-Za-z0-9.\-]*)\s+(\d{1,2}/\d{1,2}/\d{2,4})\s+(\d+(?:\.\d+)?)\s+([CPcp])\s*$"
)
# OCC compact: -NVDA260828C260 or NVDA260828C00150000
_OCC_OPTION_RE = re.compile(r"^-?([A-Za-z]{1,10})(\d{6})([CPcp])(\d{1,8})\s*$")

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "static" / "templates"


def holdings_template_csv() -> str:
    return (
        "brokerage,account,ticker,shares,cost_basis\n"
        "Schwab,IRA,AAPL,250,42000\n"
        "Fidelity,Taxable,MSFT,100,35000\n"
        "Manual,Manage Stocks,VOO,40,18000\n"
    )


def covered_calls_template_csv() -> str:
    return (
        "brokerage,account,ticker,strike,expiration_date,contracts,premium_received,open_date,status,notes\n"
        "Schwab,IRA,AAPL,220,2026-08-15,2,450,2026-07-01,open,Aug monthly\n"
        "Fidelity,Taxable,MSFT,450,2026-07-18,1,180,2026-06-20,open,\n"
    )


def mixed_portfolio_template_csv() -> str:
    """Broker-style flexible upload example (still accepted on import)."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_NONNUMERIC)
    writer.writerow(["brokerage", "account", "ticker", "shares", "market_value"])
    writer.writerow(["Schwab", "Individual", "SOFI 09/18/2026 24.00 C", -2, -88.67])
    writer.writerow(["Fidelity", "Rollover IRA", "NVDA260828C260", -1, 167.34])
    writer.writerow(["SOFI", "Individual", "NVDA", 100, 17510])
    writer.writerow(["Schwab", "Individual", "SOFI", 544, 10169.21])
    writer.writerow(["Fidelity", "Rollover IRA", "NVDA", 100, 14874.98])
    writer.writerow(["Fidelity", "M/M INC", "FXAIX", 177.915, 41185.21])
    return buf.getvalue()


def portfolio_canonical_template_csv() -> str:
    """Canonical download/storage format used by the app."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_NONNUMERIC)
    writer.writerow(list(PORTFOLIO_COLUMNS))
    writer.writerow(
        ["stock", "Schwab", "Individual", "SOFI", 544, 10169.21, "", "", "", "", "", ""]
    )
    writer.writerow(
        ["stock", "Fidelity", "Rollover IRA", "NVDA", 100, 14874.98, "", "", "", "", "", ""]
    )
    writer.writerow(
        [
            "call",
            "Schwab",
            "Individual",
            "SOFI",
            "",
            88.67,
            24.0,
            "2026-09-18",
            2,
            "2026-07-01",
            "open",
            "Aug monthly",
        ]
    )
    writer.writerow(
        [
            "call",
            "Fidelity",
            "Rollover IRA",
            "NVDA",
            "",
            167.34,
            260.0,
            "2026-08-28",
            1,
            "",
            "open",
            "",
        ]
    )
    return buf.getvalue()


def ensure_template_files() -> tuple[Path, Path, Path, Path]:
    _TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    holdings_path = _TEMPLATE_DIR / "holdings_template.csv"
    calls_path = _TEMPLATE_DIR / "covered_calls_template.csv"
    mixed_path = _TEMPLATE_DIR / "portfolio_mixed_template.csv"
    canonical_path = _TEMPLATE_DIR / "portfolio_template.csv"
    holdings_path.write_text(holdings_template_csv(), encoding="utf-8", newline="\n")
    calls_path.write_text(covered_calls_template_csv(), encoding="utf-8", newline="\n")
    mixed_path.write_text(mixed_portfolio_template_csv(), encoding="utf-8", newline="\n")
    canonical_path.write_text(portfolio_canonical_template_csv(), encoding="utf-8", newline="\n")
    return holdings_path, calls_path, mixed_path, canonical_path


def _parse_money(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if pd.isna(value):
            return None
        return float(value)
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    neg = False
    if text.startswith("(") and text.endswith(")"):
        neg = True
        text = text[1:-1]
    text = text.replace("$", "").replace(",", "").replace(" ", "")
    if text.startswith("-"):
        neg = True
        text = text[1:]
    if text.startswith("+"):
        text = text[1:]
    if not text:
        return None
    try:
        num = float(text)
    except ValueError:
        return None
    return -abs(num) if neg else num


def _normalize_expiration(text: str) -> Optional[str]:
    text = (text or "").strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_option_symbol(raw: Any) -> Optional[dict[str, Any]]:
    """
    Parse broker option symbols into ticker/strike/expiration/right.

    Supports:
    - Verbose: ``SOFI 09/18/2026 24.00 C``
    - OCC compact: ``-NVDA260828C260`` / ``NVDA260828C00150000``
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    text = str(raw).strip()
    if not text or text.lower() == "nan":
        return None
    short_marker = text.startswith("-") and not (len(text) > 1 and text[1].isdigit())
    bare = text[1:].strip() if short_marker else text

    m = _VERBOSE_OPTION_RE.match(bare)
    if m:
        ticker, exp_raw, strike_raw, right = m.groups()
        exp = _normalize_expiration(exp_raw)
        if not exp:
            return None
        return {
            "ticker": ticker.upper(),
            "expiration_date": exp,
            "strike": float(strike_raw),
            "right": right.upper(),
            "short_marker": short_marker,
            "raw": text,
        }

    m = _OCC_OPTION_RE.match(bare)
    if not m:
        m = _OCC_OPTION_RE.match(text)
    if m:
        ticker, yymmdd, right, strike_digits = m.groups()
        try:
            exp = datetime.strptime(yymmdd, "%y%m%d").date().isoformat()
        except ValueError:
            return None
        if len(strike_digits) >= 6:
            strike = int(strike_digits) / 1000.0
        else:
            strike = float(strike_digits)
        return {
            "ticker": ticker.upper(),
            "expiration_date": exp,
            "strike": strike,
            "right": right.upper(),
            "short_marker": short_marker or text.startswith("-"),
            "raw": text,
        }
    return None


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [
        str(c).strip().lower().replace(" ", "_").replace("-", "_")
        for c in out.columns
    ]
    aliases = {
        "symbol": "ticker",
        "description": "ticker",
        "security": "ticker",
        "security_description": "ticker",
        "qty": "shares",
        "quantity": "shares",
        "share_count": "shares",
        "expiry": "expiration_date",
        "expiration": "expiration_date",
        "exp_date": "expiration_date",
        "premium": "premium_received",
        "premium_total": "premium_received",
        "premium_received": "premium_received",
        # Shared money column in canonical portfolio CSV:
        # stock rows → cost basis; call rows → premium received.
        "cost_basis/premium": "cost_basis_premium",
        "cost_basis_premium": "cost_basis_premium",
        "costbasis_premium": "cost_basis_premium",
        "cost_or_premium": "cost_basis_premium",
        "broker": "brokerage",
        "institution": "brokerage",
        "account_name": "account",
        "account_type": "account",
        "acct": "account",
        "opened": "open_date",
        "open": "open_date",
        "cost": "cost_basis",
        "basis": "cost_basis",
        "costbasis": "cost_basis",
        "value": "market_value",
        "market_value": "market_value",
        "total_value": "market_value",
        "position_value": "market_value",
        "current_value": "market_value",
    }
    rename = {
        c: aliases[c]
        for c in out.columns
        if c in aliases and aliases[c] not in out.columns
    }
    if rename:
        out = out.rename(columns=rename)
    return out


def _money_from_row(raw: dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        if key not in raw:
            continue
        val = _parse_money(raw.get(key))
        if val is not None:
            return val
    return None


def _coerce_broker_export_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    If the sheet has no recognizable headers (common broker paste), assume:
    brokerage, account, ticker, shares, market_value
    """
    df = df.copy()
    cols = [str(c) for c in df.columns]
    looks_numeric_headers = all(re.fullmatch(r"\d+", c) for c in cols)
    known = {
        "ticker",
        "shares",
        "strike",
        "expiration_date",
        "brokerage",
        "symbol",
        "quantity",
        "qty",
        "market_value",
        "value",
    }
    normalized_probe = {str(c).strip().lower().replace(" ", "_") for c in df.columns}
    if looks_numeric_headers or not (normalized_probe & known):
        if df.shape[1] >= 5:
            df = df.iloc[:, :5].copy()
            df.columns = ["brokerage", "account", "ticker", "shares", "market_value"]
        elif df.shape[1] == 4:
            df = df.iloc[:, :4].copy()
            df.columns = ["brokerage", "account", "ticker", "shares"]
    return df


def _decode_upload(contents: str) -> bytes:
    if not contents:
        raise ValueError("Empty upload")
    if "," in contents:
        contents = contents.split(",", 1)[1]
    return base64.b64decode(contents)


def _read_csv_bytes(raw: bytes) -> pd.DataFrame:
    text = None
    for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "latin-1"):
        try:
            candidate = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        # Reject UTF-8 misreads of UTF-16 (lots of NULs).
        if "\x00" in candidate and not encoding.startswith("utf-16"):
            continue
        text = candidate
        break
    if text is None:
        text = raw.decode("utf-8", errors="replace")

    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    text = "\n".join(lines)
    if not text.strip():
        return pd.DataFrame()

    sep = ","
    try:
        sample = "\n".join(lines[:30])
        sep = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        if text.count(";") > text.count(","):
            sep = ";"

    df = pd.read_csv(io.StringIO(text), sep=sep)
    df = _coerce_broker_export_columns(df)
    first_col = str(df.columns[0]).strip().lower()
    brokerish = {
        "schwab",
        "fidelity",
        "sofi",
        "vanguard",
        "etrade",
        "robinhood",
        "td",
        "ameritrade",
        "interactive",
        "ibkr",
    }
    if first_col in brokerish or any(first_col.startswith(b) for b in brokerish):
        raw_again = pd.read_csv(io.StringIO(text), header=None, sep=sep)
        if raw_again.shape[1] >= 4:
            n = min(5, raw_again.shape[1])
            raw_again = raw_again.iloc[:, :n].copy()
            names = ["brokerage", "account", "ticker", "shares", "market_value"][:n]
            raw_again.columns = names
            df = raw_again
    return _normalize_columns(df)


def read_upload_to_frames(contents: str, filename: str) -> dict[str, pd.DataFrame]:
    raw = _decode_upload(contents)
    name = (filename or "").lower()
    if name.endswith(".csv"):
        return {"data": _read_csv_bytes(raw)}
    if name.endswith(".xlsx") or name.endswith(".xls"):
        try:
            book = pd.read_excel(io.BytesIO(raw), sheet_name=None, engine="openpyxl")
        except Exception as exc:
            raise ValueError(f"Could not read Excel file: {exc}") from exc
        frames = {}
        for sheet_name, df in book.items():
            key = str(sheet_name).strip().lower().replace(" ", "_")
            frames[key] = _normalize_columns(_coerce_broker_export_columns(df))
        return frames
    raise ValueError(
        "Unsupported file type. Use .csv or .xlsx (export from Google Sheets / LibreOffice)."
    )


def _sheet_frame(frames: dict[str, pd.DataFrame], *candidates: str) -> Optional[pd.DataFrame]:
    for name in candidates:
        if name in frames and frames[name] is not None and not frames[name].empty:
            return frames[name]
    if len(frames) == 1:
        return next(iter(frames.values()))
    return None


def parse_holdings_frame(df: pd.DataFrame) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    if df is None or df.empty:
        return [], ["Holdings sheet/file is empty."]
    df = _normalize_columns(df)
    for col in HOLDINGS_REQUIRED:
        if col not in df.columns:
            return [], [f"Holdings missing required column: {col}"]
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for i, raw in enumerate(df.to_dict("records"), start=2):
        ticker_raw = str(raw.get("ticker") or "").strip()
        if not ticker_raw or ticker_raw.lower() == "nan":
            if all(str(raw.get(c) or "").strip() in ("", "nan", "None") for c in df.columns):
                continue
            errors.append(f"Row {i}: ticker is required")
            continue
        if parse_option_symbol(ticker_raw):
            errors.append(
                f"Row {i}: option symbol '{ticker_raw}' belongs in a mixed portfolio file "
                "(or covered-calls CSV), not a holdings-only file."
            )
            continue
        ticker = ticker_raw.upper()
        shares = _parse_money(raw.get("shares"))
        if shares is None:
            errors.append(f"Row {i} ({ticker}): shares must be a number")
            continue
        if shares <= 0:
            errors.append(f"Row {i} ({ticker}): shares must be > 0")
            continue
        cost_val = None
        if "cost_basis" in df.columns:
            cost_val = _parse_money(raw.get("cost_basis"))
        brokerage = str(raw.get("brokerage") or "Manual").strip() or "Manual"
        if brokerage.lower() == "nan":
            brokerage = "Manual"
        account = str(raw.get("account") or "Manage Stocks").strip() or "Manage Stocks"
        if account.lower() == "nan":
            account = "Manage Stocks"
        key = (brokerage.lower(), account.lower(), ticker)
        if key in seen:
            errors.append(f"Row {i}: duplicate {brokerage} / {account} / {ticker}")
            continue
        seen.add(key)
        rows.append(
            {
                "brokerage": brokerage,
                "account": account,
                "ticker": ticker,
                "shares": shares,
                "cost_basis": cost_val,
            }
        )
    return rows, errors


def parse_covered_calls_frame(df: pd.DataFrame) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    if df is None or df.empty:
        return [], ["Covered calls sheet/file is empty."]
    df = _normalize_columns(df)
    for col in COVERED_CALLS_REQUIRED:
        if col not in df.columns:
            return [], [f"Covered calls missing required column: {col}"]
    rows: list[dict[str, Any]] = []
    for i, raw in enumerate(df.to_dict("records"), start=2):
        ticker = str(raw.get("ticker") or "").upper().strip()
        if not ticker or ticker == "NAN":
            if all(str(raw.get(c) or "").strip() in ("", "nan", "None") for c in df.columns):
                continue
            errors.append(f"Row {i}: ticker is required")
            continue
        strike = _parse_money(raw.get("strike"))
        if strike is None or strike <= 0:
            errors.append(f"Row {i} ({ticker}): strike must be a positive number")
            continue
        exp = raw.get("expiration_date")
        if hasattr(exp, "strftime"):
            expiration_date = exp.strftime("%Y-%m-%d")
        else:
            expiration_date = _normalize_expiration(str(exp or "").strip()) or str(exp or "").strip()[:10]
        if not expiration_date or expiration_date.lower() == "nan":
            errors.append(f"Row {i} ({ticker}): expiration_date is required (YYYY-MM-DD)")
            continue
        try:
            contracts = int(float(raw.get("contracts") or 1))
            if contracts < 1:
                raise ValueError("contracts")
        except (TypeError, ValueError):
            errors.append(f"Row {i} ({ticker}): contracts must be an integer >= 1")
            continue
        premium = _parse_money(raw.get("premium_received"))
        if premium is None:
            premium = _parse_money(raw.get("cost_basis_premium"))
        if premium is None:
            premium = _parse_money(raw.get("cost_basis"))
        if premium is None:
            premium = 0.0
        premium = abs(premium)
        open_raw = raw.get("open_date")
        if open_raw is None or str(open_raw).strip() in ("", "nan", "None"):
            open_date = None
        elif hasattr(open_raw, "strftime"):
            open_date = open_raw.strftime("%Y-%m-%d")
        else:
            open_date = _normalize_expiration(str(open_raw).strip()) or str(open_raw).strip()[:10]
        status = str(raw.get("status") or "open").strip().lower() or "open"
        if status == "nan":
            status = "open"
        notes = raw.get("notes")
        if notes is None or str(notes).strip().lower() in ("", "nan", "none"):
            notes = None
        else:
            notes = str(notes).strip()
        brokerage = str(raw.get("brokerage") or "Manual").strip() or "Manual"
        if brokerage.lower() == "nan":
            brokerage = "Manual"
        account = str(raw.get("account") or "Covered Calls").strip() or "Covered Calls"
        if account.lower() == "nan":
            account = "Covered Calls"
        rows.append(
            {
                "brokerage": brokerage,
                "account": account,
                "ticker": ticker,
                "strike": strike,
                "expiration_date": expiration_date,
                "contracts": contracts,
                "premium_received": premium,
                "open_date": open_date,
                "status": status,
                "notes": notes,
            }
        )
    return rows, errors


def parse_canonical_portfolio_frame(
    df: pd.DataFrame,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """
    Parse the app's canonical portfolio CSV (type = stock | call).

    One file stores both holdings and covered calls for download / re-upload.
    """
    errors: list[str] = []
    holdings: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    if df is None or df.empty:
        return [], [], ["Portfolio file is empty."]
    df = _normalize_columns(df)
    if "type" not in df.columns or "ticker" not in df.columns:
        return [], [], ["Canonical portfolio needs type and ticker columns."]

    seen_holdings: set[tuple[str, str, str]] = set()
    for i, raw in enumerate(df.to_dict("records"), start=2):
        row_type = str(raw.get("type") or "").strip().lower()
        if not row_type or row_type in ("nan", "none"):
            if all(str(raw.get(c) or "").strip() in ("", "nan", "None") for c in df.columns):
                continue
            errors.append(f"Row {i}: type is required (stock or call)")
            continue
        if row_type in ("stock", "holding", "equity", "shares"):
            row_type = "stock"
        elif row_type in ("call", "covered_call", "covered call", "cc", "option"):
            row_type = "call"
        else:
            errors.append(f"Row {i}: unknown type '{raw.get('type')}' (use stock or call)")
            continue

        ticker = str(raw.get("ticker") or "").upper().strip()
        if not ticker or ticker == "NAN":
            errors.append(f"Row {i}: ticker is required")
            continue

        brokerage = str(raw.get("brokerage") or "Manual").strip() or "Manual"
        if brokerage.lower() == "nan":
            brokerage = "Manual"

        if row_type == "stock":
            account = str(raw.get("account") or "Manage Stocks").strip() or "Manage Stocks"
            if account.lower() == "nan":
                account = "Manage Stocks"
            shares = _parse_money(raw.get("shares"))
            if shares is None or shares <= 0:
                errors.append(f"Row {i} ({ticker}): stock shares must be a number > 0")
                continue
            cost_val = _money_from_row(raw, "cost_basis_premium", "cost_basis")
            key = (brokerage.lower(), account.lower(), ticker)
            if key in seen_holdings:
                errors.append(f"Row {i}: duplicate {brokerage} / {account} / {ticker}")
                continue
            seen_holdings.add(key)
            holdings.append(
                {
                    "brokerage": brokerage,
                    "account": account,
                    "ticker": ticker,
                    "shares": float(shares),
                    "cost_basis": cost_val,
                }
            )
            continue

        account = str(raw.get("account") or "Covered Calls").strip() or "Covered Calls"
        if account.lower() == "nan":
            account = "Covered Calls"
        strike = _parse_money(raw.get("strike"))
        if strike is None or strike <= 0:
            errors.append(f"Row {i} ({ticker}): call strike must be a positive number")
            continue
        exp = raw.get("expiration_date")
        if hasattr(exp, "strftime"):
            expiration_date = exp.strftime("%Y-%m-%d")
        else:
            expiration_date = _normalize_expiration(str(exp or "").strip()) or str(exp or "").strip()[:10]
        if not expiration_date or expiration_date.lower() == "nan":
            errors.append(f"Row {i} ({ticker}): expiration_date is required (YYYY-MM-DD)")
            continue
        try:
            contracts = int(float(raw.get("contracts") or 1))
            if contracts < 1:
                raise ValueError("contracts")
        except (TypeError, ValueError):
            errors.append(f"Row {i} ({ticker}): contracts must be an integer >= 1")
            continue
        # cost_basis/premium on call rows = cash premium received when the call was sold.
        premium = _money_from_row(raw, "cost_basis_premium", "premium_received", "cost_basis", "market_value")
        if premium is None:
            premium = 0.0
        premium = abs(premium)
        open_raw = raw.get("open_date")
        if open_raw is None or str(open_raw).strip() in ("", "nan", "None"):
            open_date = None
        elif hasattr(open_raw, "strftime"):
            open_date = open_raw.strftime("%Y-%m-%d")
        else:
            open_date = _normalize_expiration(str(open_raw).strip()) or str(open_raw).strip()[:10]
        status = str(raw.get("status") or "open").strip().lower() or "open"
        if status == "nan":
            status = "open"
        notes = raw.get("notes")
        if notes is None or str(notes).strip().lower() in ("", "nan", "none"):
            notes = None
        else:
            notes = str(notes).strip()
        calls.append(
            {
                "brokerage": brokerage,
                "account": account,
                "ticker": ticker,
                "strike": float(strike),
                "expiration_date": expiration_date,
                "contracts": contracts,
                "premium_received": premium,
                "open_date": open_date,
                "status": status,
                "notes": notes,
            }
        )
    return holdings, calls, errors


def parse_mixed_portfolio_frame(
    df: pd.DataFrame,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """
    Split one broker-style sheet into holdings + covered-call rows.

    Stock rows: plain tickers with positive quantity.
    Option rows: verbose or OCC symbols; short calls (qty < 0 and/or leading '-') become covered calls.
    """
    errors: list[str] = []
    holdings: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    if df is None or df.empty:
        return [], [], ["Portfolio file is empty."]
    df = _normalize_columns(df)
    if "ticker" not in df.columns or "shares" not in df.columns:
        return [], [], ["Mixed portfolio needs ticker/symbol and shares/quantity columns."]

    seen_holdings: set[tuple[str, str, str]] = set()
    for i, raw in enumerate(df.to_dict("records"), start=2):
        symbol_raw = str(raw.get("ticker") or "").strip()
        if not symbol_raw or symbol_raw.lower() == "nan":
            if all(str(raw.get(c) or "").strip() in ("", "nan", "None") for c in df.columns):
                continue
            errors.append(f"Row {i}: ticker/symbol is required")
            continue
        qty = _parse_money(raw.get("shares"))
        if qty is None:
            errors.append(f"Row {i} ({symbol_raw}): quantity must be a number")
            continue
        brokerage = str(raw.get("brokerage") or "Manual").strip() or "Manual"
        if brokerage.lower() == "nan":
            brokerage = "Manual"
        account = str(raw.get("account") or "Manage Stocks").strip() or "Manage Stocks"
        if account.lower() == "nan":
            account = "Manage Stocks"
        market_value = _parse_money(raw.get("market_value")) if "market_value" in df.columns else None
        cost_basis = _parse_money(raw.get("cost_basis")) if "cost_basis" in df.columns else None

        opt = parse_option_symbol(symbol_raw)
        if opt:
            if opt["right"] != "C":
                errors.append(
                    f"Row {i}: put options are not imported yet ({symbol_raw}). Only covered calls (C) are supported."
                )
                continue
            is_short = qty < 0 or opt.get("short_marker")
            if not is_short:
                errors.append(
                    f"Row {i}: long call '{symbol_raw}' skipped — covered-call tracker expects short calls "
                    "(negative quantity or leading '-')."
                )
                continue
            contracts = abs(int(qty)) if float(qty).is_integer() else abs(int(round(qty)))
            if contracts < 1:
                errors.append(f"Row {i}: covered call contracts must be >= 1 ({symbol_raw})")
                continue
            premium = abs(market_value) if market_value is not None else 0.0
            if premium == 0.0 and cost_basis is not None:
                # Broker mixed files sometimes put option credit in a cost/basis-style column.
                premium = abs(cost_basis)
            notes = f"Imported {opt['raw']} from {brokerage} / {account}"
            if market_value is not None:
                notes += f"; mark/value={market_value}"
            elif cost_basis is not None:
                notes += f"; cost_basis/premium={cost_basis}"
            calls.append(
                {
                    "brokerage": brokerage,
                    "account": account,
                    "ticker": opt["ticker"],
                    "strike": float(opt["strike"]),
                    "expiration_date": opt["expiration_date"],
                    "contracts": contracts,
                    "premium_received": premium,
                    "open_date": None,
                    "status": "open",
                    "notes": notes,
                }
            )
            continue

        # Equity / fund row
        if qty <= 0:
            errors.append(f"Row {i} ({symbol_raw}): stock quantity must be > 0")
            continue
        ticker = symbol_raw.upper()
        key = (brokerage.lower(), account.lower(), ticker)
        if key in seen_holdings:
            errors.append(f"Row {i}: duplicate {brokerage} / {account} / {ticker}")
            continue
        seen_holdings.add(key)
        holdings.append(
            {
                "brokerage": brokerage,
                "account": account,
                "ticker": ticker,
                "shares": float(qty),
                "cost_basis": cost_basis,
            }
        )
    return holdings, calls, errors


def frame_looks_mixed(df: pd.DataFrame) -> bool:
    """True when a sheet mixes equities and option symbols, or is broker-export shaped without strike col."""
    df = _normalize_columns(df)
    if "ticker" not in df.columns or "shares" not in df.columns:
        return False
    if "strike" in df.columns and "expiration_date" in df.columns:
        return False
    has_option = False
    has_equity = False
    for raw in df.to_dict("records"):
        sym = str(raw.get("ticker") or "").strip()
        if not sym or sym.lower() == "nan":
            continue
        if parse_option_symbol(sym):
            has_option = True
        else:
            has_equity = True
        if has_option and has_equity:
            return True
    # Option-only broker export still uses mixed parser (writes covered calls, clears equities)
    return has_option


def apply_holdings_upload(contents: str, filename: str) -> dict[str, Any]:
    frames = read_upload_to_frames(contents, filename)
    df = _sheet_frame(frames, "holdings", "stocks", "positions", "data")
    if df is None:
        return {
            "ok": False,
            "errors": [
                "Could not find a holdings sheet. Use a CSV, or an XLSX sheet named Holdings / Stocks."
            ],
            "rows": [],
            "count": 0,
            "kind": "holdings",
        }
    return _apply_holdings_df(df)


def apply_covered_calls_upload(contents: str, filename: str) -> dict[str, Any]:
    frames = read_upload_to_frames(contents, filename)
    df = _sheet_frame(frames, "covered_calls", "coveredcalls", "calls", "options", "data")
    if df is None:
        return {
            "ok": False,
            "errors": [
                "Could not find a covered-calls sheet. Use a CSV, or an XLSX sheet named Covered Calls."
            ],
            "rows": [],
            "count": 0,
            "kind": "covered_calls",
        }
    return _apply_covered_calls_df(df)


def detect_frame_kind(df: pd.DataFrame, sheet_hint: str = "") -> Optional[str]:
    hint = (sheet_hint or "").strip().lower().replace(" ", "_")
    if hint in {"holdings", "stocks", "positions"}:
        return "holdings"
    if hint in {"covered_calls", "coveredcalls", "calls", "options"}:
        return "covered_calls"
    if hint in {"portfolio", "mixed", "all"}:
        # Prefer canonical when a type column is present
        cols_hint = set(_normalize_columns(df).columns)
        if "type" in cols_hint:
            return "canonical"
        return "mixed"

    cols = set(_normalize_columns(df).columns)
    if "type" in cols and "ticker" in cols:
        return "canonical"
    has_shares = "shares" in cols
    has_strike = "strike" in cols
    has_exp = "expiration_date" in cols
    if has_strike and has_exp and not has_shares:
        return "covered_calls"
    if frame_looks_mixed(df):
        return "mixed"
    if has_shares and not has_strike:
        return "holdings"
    if has_shares and has_strike and has_exp:
        return "covered_calls"
    return None


def _refresh_prices_after_holdings_change() -> None:
    """Best-effort quote refresh so the dashboard is not stuck on stale/missing prices."""
    try:
        from api.finnhub_api import update_stock_prices

        update_stock_prices(forceUpdate=True)
    except Exception as exc:
        print(f"[Import] Price refresh after holdings change failed: {exc}")


def _apply_holdings_df(df: pd.DataFrame) -> dict[str, Any]:
    rows, errors = parse_holdings_frame(df)
    if errors:
        return {"ok": False, "errors": errors, "rows": rows, "count": 0, "kind": "holdings"}
    count = db_manager.replace_all_stocks(rows)
    _refresh_prices_after_holdings_change()
    return {"ok": True, "errors": [], "rows": rows, "count": count, "kind": "holdings"}


def _apply_covered_calls_df(df: pd.DataFrame) -> dict[str, Any]:
    rows, errors = parse_covered_calls_frame(df)
    if errors:
        return {"ok": False, "errors": errors, "rows": rows, "count": 0, "kind": "covered_calls"}
    count = db_manager.replace_all_covered_calls(rows)
    return {"ok": True, "errors": [], "rows": rows, "count": count, "kind": "covered_calls"}


def _apply_portfolio_sides(
    holdings: list[dict[str, Any]],
    calls: list[dict[str, Any]],
    errors: list[str],
    *,
    note: str,
) -> dict[str, Any]:
    if errors and not holdings and not calls:
        return {
            "holdings": {"ok": False, "errors": errors, "rows": [], "count": 0, "kind": "holdings"},
            "covered_calls": {
                "ok": False,
                "errors": errors,
                "rows": [],
                "count": 0,
                "kind": "covered_calls",
            },
            "detected": [],
            "note": None,
            "errors": errors,
        }
    result: dict[str, Any] = {
        "holdings": None,
        "covered_calls": None,
        "detected": [],
        "note": note,
        "warnings": errors,
    }
    # Replace each dataset present in the file; empty side clears that table
    # so one CSV remains source of truth.
    h_count = db_manager.replace_all_stocks(holdings)
    result["holdings"] = {
        "ok": True,
        "errors": [],
        "rows": holdings,
        "count": h_count,
        "kind": "holdings",
    }
    result["detected"].append("holdings")
    c_count = db_manager.replace_all_covered_calls(calls)
    result["covered_calls"] = {
        "ok": True,
        "errors": [],
        "rows": calls,
        "count": c_count,
        "kind": "covered_calls",
    }
    result["detected"].append("covered_calls")
    _refresh_prices_after_holdings_change()
    if errors:
        result["note"] = (
            (result["note"] or "")
            + f" {len(errors)} row warning(s) — see details."
        ).strip()
    return result


def _apply_mixed_df(df: pd.DataFrame) -> dict[str, Any]:
    holdings, calls, errors = parse_mixed_portfolio_frame(df)
    return _apply_portfolio_sides(
        holdings,
        calls,
        errors,
        note="Detected mixed portfolio file (stocks + option symbols in one sheet).",
    )


def _apply_canonical_df(df: pd.DataFrame) -> dict[str, Any]:
    holdings, calls, errors = parse_canonical_portfolio_frame(df)
    return _apply_portfolio_sides(
        holdings,
        calls,
        errors,
        note="Detected canonical portfolio CSV (type = stock | call).",
    )


def apply_auto_upload(contents: str, filename: str) -> dict[str, Any]:
    """
    Auto-detect holdings and/or covered calls from one CSV or XLSX upload.

    Supports:
    - Canonical portfolio CSV (type = stock | call) — preferred download/storage format
    - Mixed broker export (stocks + option symbols in one sheet)
    - XLSX with Holdings + Covered Calls sheets
    - Holdings-only or covered-calls-only files
    """
    frames = read_upload_to_frames(contents, filename)
    named_holdings = None
    for key in ("holdings", "stocks", "positions"):
        if key in frames and frames[key] is not None and not frames[key].empty:
            named_holdings = frames[key]
            break
    named_calls = None
    for key in ("covered_calls", "coveredcalls", "calls", "options"):
        if key in frames and frames[key] is not None and not frames[key].empty:
            named_calls = frames[key]
            break
    named_portfolio = None
    for key in ("portfolio", "all"):
        if key in frames and frames[key] is not None and not frames[key].empty:
            named_portfolio = frames[key]
            break

    result: dict[str, Any] = {
        "holdings": None,
        "covered_calls": None,
        "note": None,
        "detected": [],
    }

    if named_portfolio is not None and named_holdings is None and named_calls is None:
        kind = detect_frame_kind(named_portfolio, sheet_hint="portfolio")
        if kind == "canonical":
            return _apply_canonical_df(named_portfolio)
        return _apply_mixed_df(named_portfolio)

    if named_holdings is not None or named_calls is not None:
        # Prefer mixed/canonical parse when a "holdings" sheet actually contains both
        if named_holdings is not None and named_calls is None:
            kind = detect_frame_kind(named_holdings)
            if kind == "canonical":
                return _apply_canonical_df(named_holdings)
            if frame_looks_mixed(named_holdings):
                return _apply_mixed_df(named_holdings)
        if named_holdings is not None:
            result["holdings"] = _apply_holdings_df(named_holdings)
            result["detected"].append("holdings")
        if named_calls is not None:
            result["covered_calls"] = _apply_covered_calls_df(named_calls)
            result["detected"].append("covered_calls")
        return result

    if not frames:
        return {
            "holdings": None,
            "covered_calls": None,
            "note": None,
            "detected": [],
            "errors": ["Upload contained no readable sheets."],
        }

    sheet_name, df = next(iter(frames.items()))
    kind = detect_frame_kind(df, sheet_hint=sheet_name if sheet_name != "data" else "")
    if kind == "canonical":
        return _apply_canonical_df(df)
    if kind == "mixed":
        return _apply_mixed_df(df)
    if kind == "holdings":
        result["holdings"] = _apply_holdings_df(df)
        result["detected"] = ["holdings"]
        result["note"] = "Detected holdings file (shares column)."
        return result
    if kind == "covered_calls":
        result["covered_calls"] = _apply_covered_calls_df(df)
        result["detected"] = ["covered_calls"]
        result["note"] = "Detected covered calls file (strike / expiration columns)."
        return result

    return {
        "holdings": None,
        "covered_calls": None,
        "detected": [],
        "note": None,
        "errors": [
            "Could not detect file type. Prefer the canonical portfolio CSV "
            "(type, brokerage, account, ticker, …) from Download, "
            "or a mixed broker CSV with stocks and/or option symbols, "
            "or an XLSX with sheets named Holdings and Covered Calls."
        ],
    }


def apply_workbook_upload(contents: str, filename: str) -> dict[str, Any]:
    """Backward-compatible alias for apply_auto_upload. """
    return apply_auto_upload(contents, filename)


def export_holdings_csv() -> str:
    df = db_manager.get_stocks()
    if df.empty:
        return "brokerage,account,ticker,shares,cost_basis\n"
    out = pd.DataFrame(
        {
            "brokerage": df.get("brokerage", "Manual"),
            "account": df.get("account", "Manage Stocks"),
            "ticker": df["ticker"],
            "shares": df["shares"],
            "cost_basis": df.get("cost_basis"),
        }
    )
    return out.to_csv(index=False)


def export_covered_calls_csv() -> str:
    df = db_manager.get_covered_calls()
    cols = list(COVERED_CALLS_COLUMNS)
    if df.empty:
        return ",".join(cols) + "\n"
    out = pd.DataFrame({c: df[c] if c in df.columns else "" for c in cols})
    return out.to_csv(index=False)


def export_portfolio_csv() -> str:
    """
    Canonical one-file export: stocks and covered calls with a type column.

    Shared column ``cost_basis/premium`` is cost basis for stocks and premium
    received (cash credit) for covered calls.
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(list(PORTFOLIO_COLUMNS))

    stocks = db_manager.get_stocks()
    if not stocks.empty:
        stocks = stocks.sort_values(
            by=[c for c in ("brokerage", "account", "ticker") if c in stocks.columns]
        )
        for _, row in stocks.iterrows():
            writer.writerow(
                [
                    "stock",
                    row.get("brokerage") or "Manual",
                    row.get("account") or "Manage Stocks",
                    str(row.get("ticker") or "").upper(),
                    row.get("shares") if row.get("shares") is not None else "",
                    row.get("cost_basis") if pd.notna(row.get("cost_basis")) else "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )

    calls = db_manager.get_covered_calls()
    if not calls.empty:
        sort_cols = [c for c in ("brokerage", "account", "expiration_date", "ticker") if c in calls.columns]
        if sort_cols:
            calls = calls.sort_values(by=sort_cols)
        for _, row in calls.iterrows():
            writer.writerow(
                [
                    "call",
                    row.get("brokerage") or "Manual",
                    row.get("account") or "Covered Calls",
                    str(row.get("ticker") or "").upper(),
                    "",
                    row.get("premium_received") if row.get("premium_received") is not None else "",
                    row.get("strike") if row.get("strike") is not None else "",
                    row.get("expiration_date") or "",
                    row.get("contracts") if row.get("contracts") is not None else "",
                    row.get("open_date") if pd.notna(row.get("open_date")) and row.get("open_date") else "",
                    row.get("status") or "open",
                    row.get("notes") if pd.notna(row.get("notes")) and row.get("notes") else "",
                ]
            )

    return buf.getvalue()


def export_portfolio_zip_bytes() -> bytes:
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("portfolio.csv", export_portfolio_csv())
        zf.writestr("holdings.csv", export_holdings_csv())
        zf.writestr("covered_calls.csv", export_covered_calls_csv())
        zf.writestr("portfolio_template.csv", portfolio_canonical_template_csv())
    return buf.getvalue()
