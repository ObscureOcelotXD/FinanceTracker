"""Tests for api.quant_risk: compute_risk_summary, ensure_benchmark_history."""
from pathlib import Path

import pytest


def _init_temp_db(tmp_path):
    import db_manager
    db_manager.DATABASE = str(tmp_path / "test_finance_data.db")
    db_manager.init_db()
    return db_manager.DATABASE


def test_compute_risk_summary_empty_db_returns_expected_keys(tmp_path):
    _init_temp_db(tmp_path)
    from api.quant_risk import compute_risk_summary
    out = compute_risk_summary()
    assert out["volatility_pct"] is None
    assert out["max_drawdown_pct"] is None
    assert out["beta"] is None
    assert out["last_updated"] is None
    assert out["fresh"] is False
    assert out["top_sector"] is None
    assert out["top_sector_pct"] is None
    assert out["hhi"] is None
    assert out["diversification_ratio"] is None


def test_compute_risk_summary_returns_dict(tmp_path):
    _init_temp_db(tmp_path)
    from api.quant_risk import compute_risk_summary
    out = compute_risk_summary()
    assert isinstance(out, dict)
    for key in ("volatility_pct", "max_drawdown_pct", "beta", "last_updated", "fresh",
                "top_sector", "top_sector_pct", "hhi", "diversification_ratio"):
        assert key in out
