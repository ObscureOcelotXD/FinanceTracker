"""
Streamlit backtesting UI for FinanceTracker.

Run:
    streamlit run streamlit_backtest.py
"""

import datetime as dt

import pandas as pd
import streamlit as st

from quant_backtest import (
    SAMPLE_PORTFOLIO,
    run_backtest,
)


st.set_page_config(page_title="Quant Backtesting", layout="wide")

st.title("Quant Backtesting")
st.caption("Educational/simulation use only. Not financial advice.")

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


def _parse_portfolio(tickers_str, shares_str):
    tickers = [t.strip().upper() for t in tickers_str.split(",") if t.strip()]
    if not tickers:
        raise ValueError("Please enter at least one ticker.")
    shares = [s.strip() for s in shares_str.split(",") if s.strip()]
    if shares and len(shares) == len(tickers):
        return {ticker: float(share) for ticker, share in zip(tickers, shares)}
    return tickers


if run_button:
    try:
        portfolio = _parse_portfolio(tickers_input, shares_input)
        strategy_name = "buy_hold" if strategy == "Buy & Hold" else "sma"
        if strategy_name == "sma" and fast_window >= slow_window:
            st.warning("Fast SMA should be smaller than Slow SMA for a crossover.")
            st.stop()
        stats, figs = run_backtest(
            portfolio=portfolio,
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            strategy_name=strategy_name,
            fast_window=int(fast_window),
            slow_window=int(slow_window),
            rebalance_monthly=rebalance,
        )

        st.subheader("Key Stats")
        st.table(pd.DataFrame([stats]))

        col1, col2 = st.columns([2, 1])
        with col1:
            st.plotly_chart(figs["equity_curve"], use_container_width=True, key="equity_curve")
        with col2:
            st.plotly_chart(figs["drawdown"], use_container_width=True, key="drawdown")
        st.plotly_chart(figs["trades"], use_container_width=True, key="trades")

        st.subheader("Buy & Hold Comparison")
        buy_stats, _ = run_backtest(
            portfolio=portfolio,
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            strategy_name="buy_hold",
            rebalance_monthly=rebalance,
        )
        st.table(pd.DataFrame([buy_stats]))
    except Exception as exc:
        st.error(f"Backtest failed: {exc}")

st.markdown(
    """
### Extensions
- Parameter optimization (grid search)
- More strategies (RSI, MACD)
- Walk-forward testing
- Upgrade to vectorbt for faster vectorized portfolio runs
"""
)
