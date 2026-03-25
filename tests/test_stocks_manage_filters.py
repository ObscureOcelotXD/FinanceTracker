"""Unit tests for stocks_manage Python-side filtering."""

import pandas as pd

import dashApp  # noqa: F401

from dashPages.stocks_manage import apply_filter_to_df


def _sample_df():
    return pd.DataFrame(
        [
            {"id": 1, "ticker": "NVDA", "shares": 10, "cost_basis": 1000, "position_value": 1500, "gain_loss": 500, "gain_loss_pct": 0.50},
            {"id": 2, "ticker": "MSFT", "shares": 5, "cost_basis": 2000, "position_value": 2200, "gain_loss": 200, "gain_loss_pct": 0.10},
            {"id": 3, "ticker": "AAPL", "shares": 20, "cost_basis": 3000, "position_value": 2800, "gain_loss": -200, "gain_loss_pct": -0.067},
        ]
    )


def test_no_filter_returns_all_rows():
    df = _sample_df()
    result = apply_filter_to_df(df, {})
    assert len(result) == 3


def test_none_filter_returns_all_rows():
    df = _sample_df()
    result = apply_filter_to_df(df, None)
    assert len(result) == 3


def test_ticker_filter_case_insensitive():
    df = _sample_df()
    result = apply_filter_to_df(df, {"ticker": "nv"})
    assert len(result) == 1
    assert result.iloc[0]["ticker"] == "NVDA"


def test_ticker_filter_partial_match():
    df = _sample_df()
    result = apply_filter_to_df(df, {"ticker": "MS"})
    assert len(result) == 1
    assert result.iloc[0]["ticker"] == "MSFT"


def test_numeric_gte_filter():
    df = _sample_df()
    result = apply_filter_to_df(df, {"col": "shares", "op": ">=", "val": 10})
    assert len(result) == 2
    assert set(result["ticker"]) == {"NVDA", "AAPL"}


def test_numeric_lte_filter():
    df = _sample_df()
    result = apply_filter_to_df(df, {"col": "gain_loss", "op": "<=", "val": 0})
    assert len(result) == 1
    assert result.iloc[0]["ticker"] == "AAPL"


def test_combined_ticker_and_numeric():
    df = _sample_df()
    result = apply_filter_to_df(df, {"ticker": "A", "col": "shares", "op": ">=", "val": 15})
    assert len(result) == 1
    assert result.iloc[0]["ticker"] == "AAPL"


def test_empty_df_returns_empty():
    df = pd.DataFrame()
    result = apply_filter_to_df(df, {"ticker": "NV"})
    assert result.empty
