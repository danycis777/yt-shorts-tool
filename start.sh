#!/usr/bin/env sh
# Start ShortsRadar (macOS / Linux). Opens the dashboard in your browser.
cd "$(dirname "$0")" || exit 1
if [ -x .venv/bin/python ]; then exec .venv/bin/python run.py "$@"; fi
if command -v python3 >/dev/null 2>&1; then exec python3 run.py "$@"; fi
exec python run.py "$@"
