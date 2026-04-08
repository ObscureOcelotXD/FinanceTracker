"""
Streamlit backtesting UI for FinanceTracker.

Run:
    streamlit run streamlit_backtest.py
"""

from __future__ import annotations

import datetime as dt
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
import plotly.io as pio
import streamlit as st

from quant.quant_backtest import SAMPLE_PORTFOLIO, normalize_portfolio_input
from services import db_manager, quant_job


def _render_quant_run_results(job_id: str, row: dict[str, Any], *, key_suffix: str) -> None:
    """Stats tables + Plotly charts from DB row and ``data/quant_figures/<job_id>/``."""
    p = row.get("params") or {}
    port = p.get("portfolio") if isinstance(p.get("portfolio"), dict) else {}
    tickers_s = ", ".join(sorted(str(k).upper() for k in port.keys())) if port else "—"
    st.caption(
        f"Saved (UTC): {row.get('created_at_utc', '—')} · "
        f"Strategy: **{p.get('strategy_name', '?')}** · "
        f"{p.get('start', '')} → {p.get('end', '')} · Tickers: {tickers_s}"
    )
    if (p.get("strategy_name") or "") == "sma":
        st.caption(f"SMA: fast={p.get('fast_window')}, slow={p.get('slow_window')}")
    st.caption(f"Monthly rebalance: {p.get('rebalance_monthly', False)}")

    st.subheader("Key stats (strategy)")
    st.table(pd.DataFrame([row["stats"]]))
    fig_root = Path.cwd() / "data" / "quant_figures" / job_id
    col1, col2 = st.columns([2, 1])
    with col1:
        p_eq = fig_root / "equity_curve.json"
        if p_eq.exists():
            st.plotly_chart(
                pio.from_json(p_eq.read_text(encoding="utf-8")),
                use_container_width=True,
                key=f"{key_suffix}_eq",
            )
        else:
            st.caption("Equity chart file not found (older run or local data cleared).")
    with col2:
        p_dd = fig_root / "drawdown.json"
        if p_dd.exists():
            st.plotly_chart(
                pio.from_json(p_dd.read_text(encoding="utf-8")),
                use_container_width=True,
                key=f"{key_suffix}_dd",
            )
    p_tr = fig_root / "trades.json"
    if p_tr.exists():
        st.plotly_chart(
            pio.from_json(p_tr.read_text(encoding="utf-8")),
            use_container_width=True,
            key=f"{key_suffix}_tr",
        )
    st.subheader("Buy & hold comparison")
    st.table(pd.DataFrame([row["benchmark_stats"]]))


st.set_page_config(page_title="Quant Backtesting", layout="wide")

st.title("Quant Backtesting")
st.caption("Educational/simulation use only. Not financial advice.")

db_manager.init_db()
status = quant_job.read_status()


def _parse_portfolio(tickers_str: str, shares_str: str) -> Union[Dict[str, float], List[str]]:
    tickers = [t.strip().upper() for t in tickers_str.split(",") if t.strip()]
    if not tickers:
        raise ValueError("Please enter at least one ticker.")
    shares = [s.strip() for s in shares_str.split(",") if s.strip()]
    if shares and len(shares) == len(tickers):
        return {ticker: float(share) for ticker, share in zip(tickers, shares)}
    return tickers


def _params_for_job(
    portfolio_raw: Union[Dict[str, float], List[str]],
    start_date: dt.date,
    end_date: dt.date,
    strategy_label: str,
    fast_window: int,
    slow_window: int,
    rebalance: bool,
) -> Dict[str, Any]:
    port_map = normalize_portfolio_input(portfolio_raw)
    return {
        "portfolio": port_map,
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "strategy_name": "buy_hold" if strategy_label == "Buy & Hold" else "sma",
        "fast_window": int(fast_window),
        "slow_window": int(slow_window),
        "rebalance_monthly": rebalance,
    }


with st.sidebar:
    st.header("Inputs")
    tickers_input = st.text_input(
        "Tickers (comma-separated)",
        value=", ".join(SAMPLE_PORTFOLIO.keys()),
    )
    shares_input = st.text_input(
        "Shares (comma-separated, optional)",
        value=", ".join(str(v) for v in SAMPLE_PORTFOLIO.values()),
    )
    strategy = st.selectbox("Strategy", ["SMA Crossover", "Buy & Hold"])
    fast_window = st.number_input("Fast SMA", min_value=5, max_value=200, value=50)
    slow_window = st.number_input("Slow SMA", min_value=20, max_value=400, value=200)
    rebalance = st.checkbox("Monthly rebalance (portfolio mode)", value=False)
    period = st.selectbox("Period", ["1y", "3y", "5y", "Custom"])
    end_date = dt.date.today()
    if period == "Custom":
        start_date = st.date_input("Start date", value=end_date - dt.timedelta(days=365 * 3))
        end_date = st.date_input("End date", value=end_date)
    else:
        years = {"1y": 1, "3y": 3, "5y": 5}[period]
        start_date = end_date - dt.timedelta(days=365 * years)

    run_button = st.button("Run Backtest")
    st.divider()
    show_history = st.checkbox("Show history", value=False)
    history_ticker = st.text_input("History filter ticker (substring)", value="", placeholder="e.g. AAPL")
    history_strategy = st.selectbox("History filter strategy", ["(any)", "sma", "buy_hold"])
    history_limit = st.number_input("History limit", min_value=1, max_value=200, value=25, step=1)

if run_button:
    try:
        portfolio = _parse_portfolio(tickers_input, shares_input)
        if strategy == "SMA Crossover" and fast_window >= slow_window:
            st.warning("Fast SMA should be smaller than Slow SMA for a crossover.")
            st.stop()
        params = _params_for_job(
            portfolio,
            start_date,
            end_date,
            strategy,
            int(fast_window),
            int(slow_window),
            rebalance,
        )
        started = quant_job.start_quant_job_if_idle(params, quant_job.execute_quant_backtest_job)
        if not started:
            st.warning("A backtest is already running.")
        else:
            st.rerun()
    except Exception as exc:
        st.error(f"Could not start backtest: {exc}")

if status.get("status") == "running":
    st.info(
        "Backtest **running in the background**. You can switch tabs or open the main dashboard; "
        "results are saved when finished."
    )
    with st.spinner("Working…"):
        time.sleep(2)
    st.rerun()

done_acked = st.session_state.setdefault("quant_done_acked_jobs", [])
err_acked = st.session_state.setdefault("quant_err_acked_jobs", [])

if status.get("status") == "error":
    jid = status.get("job_id")
    if jid and jid not in err_acked:
        if status.get("toast_eligible"):
            st.toast("Quant backtest failed.", icon="⚠️")
        err_acked.append(jid)
        st.error(status.get("error") or "Unknown error")
    elif jid:
        st.caption(f"Last backtest error: {status.get('error')}")

if status.get("status") == "done":
    jid = status.get("job_id")
    if jid and jid not in done_acked:
        if status.get("toast_eligible"):
            st.toast("Quant backtest completed.", icon="✅")
        done_acked.append(jid)
        st.success(status.get("message", "Completed"))
        row = db_manager.get_quant_backtest_run_by_job_id(jid)
        if row:
            ks = jid.replace("-", "")[:16]
            _render_quant_run_results(jid, row, key_suffix=f"qcur_{ks}")
    elif jid:
        st.caption(f"Last backtest: {status.get('message', 'Done')}")

if status.get("status") in (None, "idle") and not run_button:
    st.info(
        "Configure inputs and click **Run Backtest**. The run continues in the background "
        "so you do not need to keep this tab focused."
    )

if show_history:
    st.divider()
    st.subheader("Backtest history")
    strat_f: Optional[str] = None if history_strategy == "(any)" else str(history_strategy)
    hist = db_manager.get_quant_backtest_runs_filtered(
        limit=int(history_limit),
        ticker_contains=history_ticker.strip() or None,
        strategy_name=strat_f,
    )
    if not hist:
        st.info("No backtest runs match your filters yet. Run a backtest above or loosen filters.")
    else:
        st.caption(f"Showing {len(hist)} run(s), newest first.")
        for rec in hist:
            jid = str(rec.get("job_id") or "")
            p = rec.get("params") or {}
            port = p.get("portfolio") if isinstance(p.get("portfolio"), dict) else {}
            tick_short = ", ".join(sorted(str(k).upper() for k in list(port.keys())[:6]))
            if len(port) > 6:
                tick_short += ", …"
            title = (
                f"{p.get('strategy_name', '?')} · {p.get('start', '')} → {p.get('end', '')}"
                f" · {tick_short or '—'}"
            )
            ks = jid.replace("-", "")[:16]
            with st.expander(title, expanded=False):
                _render_quant_run_results(jid, rec, key_suffix=f"qh_{ks}")

st.markdown(
    """
### Extensions
- Parameter optimization (grid search)
- More strategies (RSI, MACD)
- Walk-forward testing
- Upgrade to vectorbt for faster vectorized portfolio runs
"""
)
