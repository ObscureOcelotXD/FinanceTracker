#!/usr/bin/env bash
# Run pytest in the project venv. Usage: ./test.sh   or   ./test.sh -v   or   ./test.sh tests/test_db_manager.py
ROOT="$(cd "$(dirname "$0")" && pwd)"
if [ ! -d "$ROOT/venv" ]; then
  echo "No venv found. Run ./start.sh first to create it and install dependencies."
  exit 1
fi
exec "$ROOT/venv/bin/python" -m pytest tests/ "$@"
