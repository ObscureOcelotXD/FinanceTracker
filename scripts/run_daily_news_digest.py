#!/usr/bin/env python3
"""
Daily (or ad-hoc) free news digest POC.

Uses public RSS feeds only — no API keys. Writes:
  data/news_digest/latest.json
  data/news_digest/latest.md

Schedule once per day (cron example, macOS/Linux):
  0 7 * * * cd /path/to/FinanceTracker && .venv/bin/python scripts/run_daily_news_digest.py >> /tmp/news_digest.log 2>&1

Or run manually:
  python scripts/run_daily_news_digest.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from repo root or scripts/
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.news_digest import run_daily_digest


def main() -> int:
    jp, mp = run_daily_digest()
    print(f"Wrote {jp}")
    print(f"Wrote {mp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
