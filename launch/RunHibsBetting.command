#!/bin/bash
# Double-click this file in Finder to launch HibsBetting.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f ".env" ]; then
  osascript -e 'display dialog "HibsBetting cannot start without a .env file in the app root. Copy .env.example and fill in your API keys." buttons {"OK"} default button "OK"'
  exit 1
fi

PYTHON=${PYTHON:-python3}
if [ -f ".venv/bin/activate" ]; then
  source ".venv/bin/activate"
  PYTHON=${PYTHON:-python}
fi

# Start Flask server in the background and open the dashboard.
$PYTHON src/hibs_predictor/web.py &
APP_PID=$!

sleep 4
if command -v open >/dev/null 2>&1; then
  open "http://127.0.0.1:5000"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://127.0.0.1:5000"
fi

wait $APP_PID
