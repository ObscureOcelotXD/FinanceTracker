#!/usr/bin/env bash
# Start FinanceTracker: create venv if needed, install deps, run Flask + Dash + Streamlit.
# Run from project root: ./start.sh

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if ! command -v python3 &>/dev/null; then
  echo "Python 3 is not installed or not on your PATH."
  echo "Install it from https://www.python.org/downloads/ or with: brew install python3"
  exit 1
fi

if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv venv
fi

echo "Using virtual environment at $ROOT/venv"
source venv/bin/activate

echo "Installing/updating dependencies..."
"$ROOT/venv/bin/python" -m pip install -q -r requirements.txt

echo ""
echo "Starting FinanceTracker..."
echo "  Flask + Dash (main app): http://127.0.0.1:5000"
echo "  Streamlit backtest:      http://127.0.0.1:8501 (if enabled)"
echo "  Streamlit filings:       http://127.0.0.1:8502 (if enabled)"
echo ""
"$ROOT/venv/bin/python" main.py
