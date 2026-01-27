"""
SEC Filings Info (Streamlit)

Setup:
  pip install sec-edgar-downloader beautifulsoup4 lxml google-genai streamlit yfinance
  Get a free Gemini API key at https://aistudio.google.com/
  Set GEMINI_API_KEY in .env or Streamlit secrets.
"""

from __future__ import annotations

import hashlib
import inspect
import importlib.metadata
import os
import re
import time
from datetime import date
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import streamlit as st
import yfinance as yf
from bs4 import BeautifulSoup
from google import genai
import pyrate_limiter
import requests

import db_manager


def _patch_pyrate_limiter() -> None:
    try:
        sig = inspect.signature(pyrate_limiter.Limiter.__init__)
    except (TypeError, ValueError):
        return
    if "raise_when_fail" in sig.parameters:
        return

    original_init = pyrate_limiter.Limiter.__init__

    def _init(self, *args, **kwargs):
        kwargs.pop("raise_when_fail", None)
        kwargs.pop("max_delay", None)
        return original_init(self, *args, **kwargs)

    pyrate_limiter.Limiter.__init__ = _init


_patch_pyrate_limiter()

from sec_edgar_downloader import Downloader
from sec_edgar_downloader._constants import ROOT_SAVE_FOLDER_NAME
import sec_edgar_downloader._sec_gateway as sec_gateway


DEFAULT_MODEL = "gemini-2.0-flash"
FALLBACK_MODEL = "gemini-flash-latest"
MODEL_CANDIDATES = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-flash-latest",
    "gemini-pro-latest",
]
FILING_TYPES = ["10-K", "10-Q", "DEF 14A"]
DEFAULT_TICKERS = "AAPL"
MAX_TICKERS = 5
CHUNK_SIZE = 4000
MAX_CHUNKS = 8
MAX_FILINGS_PER_TYPE = 1
DOWNLOAD_PAUSE_SECONDS = 0.25
SEC_MIN_INTERVAL_SECONDS = 0.2
SEC_FILINGS_RETENTION_DAYS = 30


DISCLAIMER = (
    "AI-generated summaries are approximate and for educational use only. "
    "Always read the official SEC filings at sec.gov. Not financial advice "
    "or investment recommendation."
)


SYSTEM_PROMPT = (
    "You are a clear, helpful financial analyst explaining to everyday investors. "
    "Summarize this excerpt from an SEC filing in simple, jargon-free English using "
    "bullet points only. Focus on: "
    "- Key financial highlights and changes (revenue, profits, etc.) for 10-K/10-Q "
    "- Major risks and uncertainties "
    "- Management's discussion and analysis points "
    "- For DEF 14A (proxies): executive compensation, shareholder proposals, voting results. "
    "Be concise, objective, and explain any terms simply."
)


def _create_downloader(base_dir: Path) -> Downloader:
    user_agent = os.getenv("SEC_EDGAR_USER_AGENT")
    company = os.getenv("SEC_EDGAR_COMPANY") or "FinanceTracker"
    email = os.getenv("SEC_EDGAR_EMAIL") or "you@example.com"
    try:
        init_sig = inspect.signature(Downloader.__init__)
    except (TypeError, ValueError):
        init_sig = None
    try:
        if user_agent:
            return Downloader(str(base_dir), user_agent)
    except TypeError:
        pass
    try:
        if init_sig and "email_address" in init_sig.parameters:
            return Downloader(company, email, str(base_dir))
        return Downloader(str(base_dir), company, email)
    except TypeError:
        if init_sig and "email_address" in init_sig.parameters:
            return Downloader(company, email)
        return Downloader(str(base_dir))


def _patch_sec_gateway() -> None:
    try:
        version = importlib.metadata.version("pyrate-limiter")
        major = int(version.split(".", maxsplit=1)[0])
    except Exception:
        return
    if major < 4:
        return
    if getattr(sec_gateway, "_ft_patched", False):
        return

    last_call = {"t": 0.0}

    def _call_sec(uri: str, user_agent: str, host: str):
        now = time.monotonic()
        elapsed = now - last_call["t"]
        if elapsed < SEC_MIN_INTERVAL_SECONDS:
            time.sleep(SEC_MIN_INTERVAL_SECONDS - elapsed)
        last_call["t"] = time.monotonic()
        resp = sec_gateway.requests.get(
            uri,
            headers={
                **sec_gateway.STANDARD_HEADERS,
                "User-Agent": user_agent,
                "Host": host,
            },
        )
        resp.raise_for_status()
        return resp

    sec_gateway._call_sec = _call_sec
    sec_gateway._ft_patched = True


def _parse_tickers(raw: str) -> List[str]:
    tickers = [t.strip().upper() for t in raw.split(",") if t.strip()]
    return tickers[:MAX_TICKERS]


def _download_filings(
    dl: Downloader,
    base_dir: Path,
    ticker: str,
    filing_types: Iterable[str],
    after_date: str,
) -> None:
    for ftype in filing_types:
        existing = _find_filing_files(base_dir, ticker, ftype)
        if existing:
            continue
        try:
            dl.get(
                ftype,
                ticker,
                after=after_date,
                download_details=False,
                limit=MAX_FILINGS_PER_TYPE,
            )
        except Exception as exc:
            st.warning(f"{ticker} {ftype}: download failed ({exc}).")
        time.sleep(DOWNLOAD_PAUSE_SECONDS)


def _candidate_roots(base_dir: Path) -> List[Path]:
    roots = [
        base_dir / ROOT_SAVE_FOLDER_NAME,
        base_dir,
        Path.cwd() / ROOT_SAVE_FOLDER_NAME,
        Path.cwd(),
    ]
    unique_roots = []
    for root in roots:
        if root not in unique_roots:
            unique_roots.append(root)
    return unique_roots


def _prune_old_filings(base_dir: Path) -> None:
    retention_raw = os.getenv("SEC_FILINGS_RETENTION_DAYS")
    try:
        retention_days = int(retention_raw) if retention_raw else SEC_FILINGS_RETENTION_DAYS
    except ValueError:
        retention_days = SEC_FILINGS_RETENTION_DAYS
    if retention_days <= 0:
        return
    root = base_dir / ROOT_SAVE_FOLDER_NAME
    if not root.exists():
        return
    cutoff = time.time() - (retention_days * 86400)
    for path in root.rglob("*"):
        if path.is_file() and path.stat().st_mtime < cutoff:
            try:
                path.unlink()
            except OSError:
                pass
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass


def _find_filing_files(base_dir: Path, ticker: str, filing_type: str) -> List[Path]:
    patterns = [
        f"**/{ticker}/{filing_type}/**/*.htm",
        f"**/{ticker}/{filing_type}/**/*.html",
        f"**/{ticker}/{filing_type}/**/*.txt",
    ]
    matches: List[Path] = []
    for root in _candidate_roots(base_dir):
        for pattern in patterns:
            matches.extend(root.glob(pattern))
    matches = sorted(matches, key=lambda p: p.stat().st_mtime, reverse=True)
    return matches


def _extract_text(path: Path) -> str:
    text = path.read_text(errors="ignore")
    soup = BeautifulSoup(text, "lxml")
    return soup.get_text(separator="\n", strip=True)


def _hash_file(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def _read_streamlit_secret(key: str):
    secrets_paths = [
        Path.home() / ".streamlit" / "secrets.toml",
        Path.cwd() / ".streamlit" / "secrets.toml",
    ]
    if not any(path.exists() for path in secrets_paths):
        return None
    try:
        return st.secrets.get(key)
    except Exception:
        return None


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, max_chunks: int = MAX_CHUNKS) -> List[str]:
    chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
    return chunks[:max_chunks]


def _guess_filing_date(path: Path) -> str:
    try:
        with path.open("r", errors="ignore") as handle:
            header = handle.read(20000)
    except OSError:
        header = ""

    def _extract(label: str) -> Optional[str]:
        match = re.search(rf"{label}:\s*(\d{{8}})", header)
        if not match:
            return None
        raw = match.group(1)
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"

    for label in ("FILED AS OF DATE", "FILING DATE", "CONFORMED PERIOD OF REPORT"):
        parsed = _extract(label)
        if parsed:
            return parsed

    match = re.search(r"\b(19|20)\d{2}-\d{2}-\d{2}\b", str(path))
    if match:
        return match.group(0)
    return date.fromtimestamp(path.stat().st_mtime).isoformat()


def _pick_model(client, override: str | None) -> str:
    try:
        available = [m.name for m in client.models.list()]
    except Exception:
        available = []
    if override:
        return override
    for candidate in MODEL_CANDIDATES:
        if not available or candidate in available or f"models/{candidate}" in available:
            return candidate
    return FALLBACK_MODEL


def _maybe_wait_on_quota(exc: Exception) -> bool:
    msg = str(exc)
    if "RESOURCE_EXHAUSTED" not in msg and "Quota exceeded" not in msg:
        return False
    match = re.search(r"retryDelay': '(\d+)s'", msg) or re.search(r"retryDelay\": \"(\d+)s", msg)
    if match:
        wait_seconds = int(match.group(1))
        time.sleep(wait_seconds)
        return True
    return False


def _summarize_with_groq(prompt: str) -> Tuple[Optional[str], Optional[str]]:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None, None
    model = os.getenv("GROQ_MODEL") or "llama-3.1-70b-versatile"
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 400,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        return (content or "").strip(), f"groq:{model}"
    except Exception:
        return None, None


def _summarize_with_hf(prompt: str) -> Tuple[Optional[str], Optional[str]]:
    api_key = os.getenv("HF_API_KEY")
    if not api_key:
        return None, None
    model = os.getenv("HF_MODEL") or "meta-llama/Meta-Llama-3-8B-Instruct"
    url = f"https://api-inference.huggingface.co/models/{model}"
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "inputs": f"{SYSTEM_PROMPT}\n\n{prompt}",
                "parameters": {"max_new_tokens": 400, "temperature": 0.2},
            },
            timeout=60,
        )
        if resp.status_code == 503:
            return None, None
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and data:
            content = data[0].get("generated_text")
            return (content or "").strip(), f"hf:{model}"
        return None, None
    except Exception:
        return None, None


def _summarize_with_fallbacks(prompt: str) -> Tuple[Optional[str], Optional[str]]:
    text, label = _summarize_with_hf(prompt)
    if text:
        return text, label
    return None, None


def _init_gemini():
    api_key = os.getenv("GEMINI_API_KEY") or _read_streamlit_secret("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY (env var or Streamlit secrets).")
    override_model = os.getenv("GEMINI_MODEL") or _read_streamlit_secret("GEMINI_MODEL")
    try:
        client = genai.Client(api_key=api_key)
        return client, _pick_model(client, override_model)
    except Exception:
        try:
            client = genai.Client(api_key=api_key)
            return client, _pick_model(client, override_model)
        except Exception:
            client = genai.Client(api_key=api_key)
            return client, _pick_model(client, override_model)


def _summarize_chunks(client, chunks: Iterable[str], model_name: str) -> Tuple[List[str], Optional[str], str]:
    summaries: List[str] = []
    used_labels = set()
    for chunk in chunks:
        prompt = f"{SYSTEM_PROMPT}\n\nExcerpt:\n{chunk}"
        try:
            groq_text, groq_label = _summarize_with_groq(prompt)
            if groq_text:
                summaries.append(groq_text)
                used_labels.add(groq_label or "groq")
                continue
            result = client.models.generate_content(model=model_name, contents=prompt)
            summaries.append((result.text or "").strip())
            used_labels.add(f"gemini:{model_name}")
        except Exception as exc:
            if _maybe_wait_on_quota(exc):
                try:
                    result = client.models.generate_content(model=model_name, contents=prompt)
                    summaries.append((result.text or "").strip())
                    used_labels.add(f"gemini:{model_name}")
                    continue
                except Exception as retry_exc:
                    summaries.append(f"- Summary failed for a chunk ({retry_exc}).")
                    continue
            summaries.append(f"- Summary failed for a chunk ({exc}).")
    combined = None
    if summaries:
        combo_prompt = (
            f"{SYSTEM_PROMPT}\n\nCombine these bullet summaries into a single, "
            f"concise bullet list:\n\n" + "\n".join(summaries)
        )
        try:
            groq_text, groq_label = _summarize_with_groq(combo_prompt)
            if groq_text:
                combined = groq_text
                used_labels.add(groq_label or "groq")
            else:
                result = client.models.generate_content(model=model_name, contents=combo_prompt)
                combined = (result.text or "").strip()
                used_labels.add(f"gemini:{model_name}")
        except Exception as exc:
            if _maybe_wait_on_quota(exc):
                try:
                    result = client.models.generate_content(model=model_name, contents=combo_prompt)
                    combined = (result.text or "").strip()
                    used_labels.add(f"gemini:{model_name}")
                except Exception:
                    combined = None
            else:
                combined = None
    if not used_labels:
        used_labels.add(f"gemini:{model_name}")
    label = sorted(used_labels)
    return summaries, combined, ", ".join(label) if len(label) == 1 else f"mixed:{', '.join(label)}"


def _ticker_label(ticker: str) -> str:
    try:
        info = yf.Ticker(ticker).info
        name = info.get("shortName") or info.get("longName")
        if name:
            return f"{ticker} — {name}"
    except Exception:
        pass
    return ticker


def main() -> None:
    st.set_page_config(page_title="SEC Filings Info", layout="wide")
    st.title("SEC Filings Info")
    st.caption("Fetch and summarize recent SEC filings for quick, high-level review.")
    st.warning(DISCLAIMER)
    db_manager.init_db()
    _patch_sec_gateway()

    with st.sidebar:
        st.header("Inputs")
        tickers_raw = st.text_input("Tickers (comma-separated, 1–5)", value=DEFAULT_TICKERS)
        filing_types = st.multiselect("Filing types", FILING_TYPES, default=["10-K", "10-Q"])
        after_date = st.date_input("After date", value=date(2024, 1, 1))
        run_btn = st.button("Fetch & Summarize", type="primary")
        st.divider()
        force_refresh = st.checkbox("Force refresh (ignore cache)", value=False)
        show_history = st.checkbox("Show history", value=False)
        history_ticker = st.text_input("History filter ticker", value="")
        history_type = st.selectbox("History filter type", ["", *FILING_TYPES])
        history_limit = st.number_input("History limit", min_value=1, max_value=200, value=25, step=1)
        if st.button("Clear cached summaries (filtered)"):
            db_manager.delete_sec_summaries(
                ticker=history_ticker.strip().upper() or None,
                filing_type=history_type or None,
            )
            scope_parts = []
            if history_ticker.strip():
                scope_parts.append(f"ticker={history_ticker.strip().upper()}")
            if history_type:
                scope_parts.append(f"type={history_type}")
            scope = ", ".join(scope_parts) if scope_parts else "all summaries"
            st.success(f"Cached summaries cleared ({scope}).")

    if not run_btn:
        st.info("Enter tickers and click Fetch & Summarize.")
        return

    tickers = _parse_tickers(tickers_raw)
    if not tickers:
        st.error("Please enter at least one ticker.")
        return

    if not filing_types:
        st.error("Select at least one filing type.")
        return

    base_dir = Path.cwd()
    _prune_old_filings(base_dir)
    dl = _create_downloader(base_dir)

    try:
        client, model_name = _init_gemini()
    except Exception as exc:
        st.error(str(exc))
        return
    st.caption("Provider: Groq (primary) → Gemini (fallback)")
    st.write("### Results")
    for ticker in tickers:
        st.subheader(_ticker_label(ticker))
        _download_filings(dl, base_dir, ticker, filing_types, after_date.isoformat())

        for ftype in filing_types:
            files = _find_filing_files(base_dir, ticker, ftype)
            if not files:
                st.warning(f"{ftype}: no filings found.")
                continue

            latest = files[0]
            filing_date = _guess_filing_date(latest)
            st.markdown(f"**{ftype}** — {filing_date}")
            st.caption(f"Source file: {latest}")

            doc_hash = _hash_file(latest)
            cached = None if force_refresh else db_manager.get_sec_summary(doc_hash)
            if cached:
                st.markdown(cached["summary_text"] or "")
                st.caption("Cached summary")
            else:
                try:
                    text = _extract_text(latest)
                except Exception as exc:
                    st.error(f"{ftype}: failed to parse filing ({exc}).")
                    continue

                chunks = _chunk_text(text)
                summaries, combined, used_model = _summarize_chunks(client, chunks, model_name)
                summary_text = combined or "\n".join(summaries)
                st.markdown(summary_text)
                st.caption(f"Used model: {used_model}")
                db_manager.upsert_sec_summary(
                    doc_hash=doc_hash,
                    ticker=ticker,
                    filing_type=ftype,
                    filing_date=filing_date,
                    source_path=str(latest),
                    summary_text=summary_text,
                    model=used_model,
                )

            st.divider()

    st.caption(DISCLAIMER)
    st.caption(
        "If Gemini rate limits or fails, you can swap the summarizer to a local model "
        "(Ollama) or a low-cost API like Groq in the same summarize function."
    )

    if show_history:
        st.divider()
        st.subheader("Summary history")
        ticker_filter = history_ticker.strip().upper() or None
        filing_type_filter = history_type or None
        records = db_manager.get_sec_summaries(
            limit=int(history_limit),
            ticker=ticker_filter,
            filing_type=filing_type_filter,
        )
        if not records:
            st.info("No summaries found yet.")
        for record in records:
            header = f"{record['ticker']} {record['filing_type']} — {record['filing_date']}"
            with st.expander(header, expanded=False):
                st.caption(f"Created: {record['created_at']} | Model: {record['model']}")
                st.caption(f"Source: {record['source_path']}")
                st.markdown(record["summary_text"] or "")


if __name__ == "__main__":
    main()
