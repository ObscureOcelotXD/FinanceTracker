"""
Quant backtesting utilities.

Educational/simulation use only. Not financial advice. Does not account for
slippage, commissions, taxes, or real-world execution unless modeled.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
from backtesting import Backtest, Strategy
from backtesting.lib import crossover


RISK_FREE_RATE = 0.04
TRADING_DAYS = 252


def _sma(series: pd.Series, window: int) -> np.ndarray:
    values = pd.Series(series)
    return values.rolling(window).mean().to_numpy()


class BuyAndHoldStrategy(Strategy):
    def init(self):
        self._entered = False

    def next(self):
        if not self._entered:
            self.buy()
            self._entered = True


class SmaCrossStrategy(Strategy):
    fast_window = 50
    slow_window = 200

    def init(self):
        self.sma_fast = self.I(_sma, self.data.Close, self.fast_window)
        self.sma_slow = self.I(_sma, self.data.Close, self.slow_window)

    def next(self):
        if crossover(self.sma_fast, self.sma_slow):
            self.buy()
        elif crossover(self.sma_slow, self.sma_fast):
            self.sell()


def normalize_portfolio_input(
    portfolio: Union[Dict[str, float], Iterable[str], pd.DataFrame],
) -> Dict[str, float]:
    if isinstance(portfolio, pd.DataFrame):
        if "ticker" in portfolio.columns and "shares" in portfolio.columns:
            return dict(zip(portfolio["ticker"], portfolio["shares"]))
        raise ValueError("DataFrame input must have 'ticker' and 'shares' columns.")
    if isinstance(portfolio, dict):
        return {str(k).upper(): float(v) for k, v in portfolio.items()}
    tickers = [str(t).upper() for t in portfolio]
    return {ticker: 1.0 for ticker in tickers}


def fetch_price_data(
    tickers: List[str],
    start: str,
    end: str,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    data = yf.download(
        tickers=tickers,
        start=start,
        end=end,
        auto_adjust=False,
        progress=False,
        group_by="column",
        actions=True,
    )
    if data.empty:
        raise ValueError("No data returned. Check tickers or date range.")

    if len(tickers) == 1:
        if "Adj Close" in data.columns:
            adj_col = "Adj Close"
        else:
            adj_col = "Close"
        ohlcv = data[["Open", "High", "Low", "Close", adj_col, "Volume"]].copy()
        ohlcv.rename(columns={adj_col: "AdjClose"}, inplace=True)
        if ohlcv["AdjClose"].dropna().empty:
            raise ValueError(f"No adjusted close data for {tickers[0]}.")
        prices = ohlcv[["AdjClose"]].rename(columns={"AdjClose": tickers[0]})
        return ohlcv, prices

    if "Adj Close" not in data.columns:
        raise ValueError("Adjusted close data not available.")
    prices = data["Adj Close"].copy()
    if isinstance(prices, pd.Series):
        prices = prices.to_frame(tickers[0])
    prices = prices.dropna(axis=1, how="all")
    if prices.empty:
        raise ValueError("Missing adjusted close data.")
    return data, prices


def build_portfolio_series(
    prices: pd.DataFrame,
    weights: Optional[pd.Series] = None,
    rebalance: bool = False,
) -> pd.Series:
    returns = prices.pct_change().fillna(0)
    if weights is None:
        weights = pd.Series(1.0, index=prices.columns)
    weights = weights / weights.sum()

    portfolio_value = []
    current_weights = weights.copy()
    value = 1.0
    for date, row in returns.iterrows():
        if rebalance and date.day == 1:
            current_weights = weights.copy()
        daily_return = float((current_weights * row).sum())
        value *= 1 + daily_return
        portfolio_value.append(value)
        current_weights = current_weights * (1 + row)
        if current_weights.sum() != 0:
            current_weights = current_weights / current_weights.sum()
    return pd.Series(portfolio_value, index=returns.index, name="Close")


def build_portfolio_ohlcv(series: pd.Series) -> pd.DataFrame:
    df = pd.DataFrame(index=series.index)
    df["Close"] = series
    df["Open"] = series.shift(1).fillna(series)
    df["High"] = df[["Open", "Close"]].max(axis=1)
    df["Low"] = df[["Open", "Close"]].min(axis=1)
    df["Volume"] = 0
    return df


def _stats_from_equity(
    equity_curve: pd.DataFrame,
    risk_free_rate: float = RISK_FREE_RATE,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if equity_curve.empty or "Equity" not in equity_curve.columns:
        return None, None, None
    returns = equity_curve["Equity"].pct_change().dropna()
    if returns.empty:
        return None, None, None
    total_return = (equity_curve["Equity"].iloc[-1] / equity_curve["Equity"].iloc[0]) - 1
    years = len(returns) / TRADING_DAYS
    annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else None
    daily_rf = risk_free_rate / TRADING_DAYS
    sharpe = ((returns.mean() - daily_rf) / returns.std()) * np.sqrt(TRADING_DAYS) if returns.std() else None
    return total_return, annual_return, sharpe


def _plot_equity_curve(equity_curve: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=equity_curve.index, y=equity_curve["Equity"], name="Equity"))
    fig.update_layout(title="Equity Curve", template="plotly_dark", height=400)
    return fig


def _plot_drawdown(equity_curve: pd.DataFrame) -> go.Figure:
    drawdown = equity_curve["Equity"] / equity_curve["Equity"].cummax() - 1
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=equity_curve.index, y=drawdown, name="Drawdown"))
    fig.update_layout(title="Drawdown", template="plotly_dark", height=250)
    return fig


def _plot_trades(equity_curve: pd.DataFrame, trades: pd.DataFrame) -> go.Figure:
    fig = _plot_equity_curve(equity_curve)
    if trades is None or trades.empty:
        return fig
    entry_times = trades["EntryTime"]
    exit_times = trades["ExitTime"]
    entries = equity_curve.reindex(entry_times)["Equity"]
    exits = equity_curve.reindex(exit_times)["Equity"]
    fig.add_trace(go.Scatter(
        x=entry_times,
        y=entries,
        mode="markers",
        name="Buy",
        marker=dict(color="lime", size=8),
    ))
    fig.add_trace(go.Scatter(
        x=exit_times,
        y=exits,
        mode="markers",
        name="Sell",
        marker=dict(color="red", size=8),
    ))
    fig.update_layout(title="Equity Curve with Trades")
    return fig


def run_backtest(
    portfolio: Union[Dict[str, float], Iterable[str], pd.DataFrame],
    start: str,
    end: str,
    strategy_name: str = "sma",
    fast_window: int = 50,
    slow_window: int = 200,
    initial_cash: float = 10000,
    rebalance_monthly: bool = False,
) -> Tuple[Dict[str, Optional[float]], Dict[str, go.Figure]]:
    portfolio_map = normalize_portfolio_input(portfolio)
    tickers = list(portfolio_map.keys())
    raw_data, prices = fetch_price_data(tickers, start, end)

    if len(tickers) == 1:
        data = raw_data.copy()
        data["Close"] = data["AdjClose"]
        ohlcv = data[["Open", "High", "Low", "Close", "Volume"]].dropna()
    else:
        prices = prices.ffill().dropna()
        weights = pd.Series(portfolio_map)
        weights = weights.reindex(prices.columns).dropna()
        if weights.empty:
            raise ValueError("No valid tickers with data in this period.")
        weights = weights * prices.iloc[0]
        ohlcv = build_portfolio_ohlcv(
            build_portfolio_series(prices, weights=weights, rebalance=rebalance_monthly)
        )
    ohlcv = ohlcv.copy()
    ohlcv.index = pd.to_datetime(ohlcv.index)
    ohlcv = ohlcv[~ohlcv.index.duplicated()].sort_index()
    ohlcv = ohlcv.apply(pd.to_numeric, errors="coerce")
    ohlcv = ohlcv.dropna()
    if ohlcv.empty or ohlcv["Close"].dropna().empty:
        raise ValueError("No usable price data after cleaning.")

    if strategy_name == "buy_hold":
        strategy = BuyAndHoldStrategy
        strategy_kwargs = {}
    else:
        strategy = SmaCrossStrategy
        strategy_kwargs = {"fast_window": fast_window, "slow_window": slow_window}
        min_bars = max(fast_window, slow_window) + 2
        if ohlcv["Close"].dropna().shape[0] < min_bars:
            raise ValueError(
                f"Not enough data for SMA windows. Need at least {min_bars} bars, got {len(ohlcv)}."
            )

    bt = Backtest(
        ohlcv,
        strategy,
        cash=initial_cash,
        commission=0.0,
        trade_on_close=True,
    )
    stats = bt.run(**strategy_kwargs)

    equity_curve = stats.get("_equity_curve")
    trades = stats.get("_trades")
    total_ret, annual_ret, sharpe = _stats_from_equity(equity_curve)

    stats_out = {
        "total_return_pct": round(total_ret * 100, 2) if total_ret is not None else None,
        "annualized_return_pct": round(annual_ret * 100, 2) if annual_ret is not None else None,
        "sharpe_ratio": round(sharpe, 2) if sharpe is not None else None,
        "max_drawdown_pct": round(stats.get("Max. Drawdown [%]", 0), 2) if stats is not None else None,
        "trades": int(stats.get("# Trades", 0)) if stats is not None else 0,
        "win_rate_pct": round(stats.get("Win Rate [%]", 0), 2) if stats is not None else None,
    }

    figures = {
        "equity_curve": _plot_equity_curve(equity_curve),
        "drawdown": _plot_drawdown(equity_curve),
        "trades": _plot_trades(equity_curve, trades),
    }

    return stats_out, figures


SAMPLE_PORTFOLIO = {"AAPL": 10, "TSLA": 5, "GOOG": 8, "JPM": 12}
