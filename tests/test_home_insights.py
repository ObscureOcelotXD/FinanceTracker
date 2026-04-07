"""Home page Groq cross-insights (news + SEC)."""

import json
from unittest.mock import MagicMock

import api.home_insights as hi
import db_manager


def test_normalize_sources_merges_labels():
    catalog = [
        {"kind": "news", "label": "N1", "title": "Headline", "url": "https://a.com/x"},
        {"kind": "sec", "label": "S1", "title": "MSFT 10-K", "detail": "2024-01-01"},
    ]
    raw = [
        {"kind": "news", "label": "N1", "title": ""},
        {"kind": "sec", "label": "S1", "title": "MSFT 10-K"},
    ]
    out = hi._normalize_sources(raw, catalog)
    assert len(out) == 2
    assert out[0].get("url") == "https://a.com/x"


def test_generate_stores_insight(tmp_path, monkeypatch):
    db_path = tmp_path / "t.db"
    db_manager.DATABASE = str(db_path)
    db_manager.init_db()
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("HOME_INSIGHTS_ENABLED", "1")

    mock_post = MagicMock()
    mock_post.return_value.raise_for_status = MagicMock()
    mock_post.return_value.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "insights": "- First point\n- Second",
                            "sources": [{"kind": "news", "title": "T", "label": "N1", "url": "https://z.com"}],
                        }
                    )
                }
            }
        ]
    }
    monkeypatch.setattr(hi.requests, "post", mock_post)
    monkeypatch.setattr(hi, "_build_context", lambda: ("prompt body", [{"kind": "news", "label": "N1", "title": "T", "url": "https://z.com"}]))

    assert hi.generate_and_store_home_insights() is True
    row = db_manager.get_home_insights()
    assert row
    assert "First point" in (row.get("insight_text") or "")
