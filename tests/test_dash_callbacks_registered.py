"""Smoke test: Dash page callbacks register on the shared app."""
import os


def test_dash_page_callbacks_are_registered():
    os.environ["NEWS_DIGEST_DISABLE_SCHEDULER"] = "1"
    from dashApp import dash_app

    keys = list(dash_app.callback_map.keys())
    joined = "\n".join(keys)
    assert "cc-coverable-table.data" in joined
    assert "cc-open-table.data" in joined
    assert "stocks-table.data" in joined or "stocks-table" in joined
    assert "import-auto-result" in joined
    assert len(keys) >= 20
