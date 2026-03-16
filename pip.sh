#!/usr/bin/env bash
# Run pip inside the project venv. Usage: ./pip.sh install <package>   or   ./pip.sh install -r requirements.txt
ROOT="$(cd "$(dirname "$0")" && pwd)"
if [ ! -d "$ROOT/venv" ]; then
  echo "No venv found. Run ./start.sh first to create it and install dependencies."
  exit 1
fi
exec "$ROOT/venv/bin/python" -m pip "$@"
