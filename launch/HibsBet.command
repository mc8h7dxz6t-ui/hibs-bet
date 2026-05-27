#!/bin/bash
# Double-click launcher — waits until the server answers, then opens the browser.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$APP_ROOT"

# shellcheck source=launch/pick_port.sh
source "$SCRIPT_DIR/pick_port.sh"

if [ -f ".env" ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

export HIBS_CACHE_DIR="${HIBS_CACHE_DIR:-.cache}"
export PYTHONPATH=src
export HIBS_WARM_FIXTURE_CACHE="${HIBS_WARM_FIXTURE_CACHE:-0}"
export HIBS_PROGRESSIVE_LOAD="${HIBS_PROGRESSIVE_LOAD:-1}"
# Logging (audit + file log) — read-only side effects; does not change enrich/DQ.
export HIBS_APP_LOG_ENABLED="${HIBS_APP_LOG_ENABLED:-1}"
export HIBS_PREDICTION_LOG_ENABLED="${HIBS_PREDICTION_LOG_ENABLED:-1}"
export HIBS_CLV_LOG_ENABLED="${HIBS_CLV_LOG_ENABLED:-1}"

wait_for_ping() {
  local port="$1"
  local tries="${2:-90}"
  local i
  for ((i = 1; i <= tries; i++)); do
    if curl -sf -m 2 "http://127.0.0.1:${port}/api/ping" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

find_running_port() {
  local p
  for p in 5001 5002 5010 8080; do
    if curl -sf -m 2 "http://127.0.0.1:${p}/api/ping" >/dev/null 2>&1; then
      echo "$p"
      return 0
    fi
  done
  return 1
}

URL_FILE="$APP_ROOT/launch/hibs-bet.url"

open_dashboard() {
  local port="$1"
  local url="http://127.0.0.1:${port}/"
  echo "$url" >"$URL_FILE"
  echo ""
  echo "hibs-bet is running at $url"
  echo "(saved to launch/hibs-bet.url)"
  if [ -f "$APP_ROOT/logs/hibs-bet.log" ]; then
    echo "Log file: $APP_ROOT/logs/hibs-bet.log"
  fi
  if command -v open >/dev/null 2>&1; then
    open "$url"
  fi
}

RUNNING="$(find_running_port || true)"
if [ -n "$RUNNING" ]; then
  export PORT="$RUNNING"
  echo "Using existing hibs-bet on port $PORT"
  open_dashboard "$PORT"
  exit 0
fi

PREFERRED="${PORT:-5001}"
CHOSEN="$(pick_listen_port "$PREFERRED")"
export PORT="$CHOSEN"
if [ "$CHOSEN" != "$PREFERRED" ]; then
  echo "Port $PREFERRED in use — starting on $CHOSEN"
fi

PYTHON=${PYTHON:-python3}
if [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
  PYTHON=${PYTHON:-python}
elif [ -x ".pytest-venv/bin/python" ]; then
  PYTHON=".pytest-venv/bin/python"
elif command -v python3.11 >/dev/null 2>&1; then
  PYTHON="python3.11"
fi

echo "Starting hibs-bet on port $PORT…"
"$PYTHON" src/hibs_predictor/web.py &
APP_PID=$!

if ! wait_for_ping "$PORT" 90; then
  kill "$APP_PID" 2>/dev/null || true
  MSG="hibs-bet did not start on port ${PORT} within 90s. Check Terminal for errors, or run: cd ${APP_ROOT} && PYTHONPATH=src python3 src/hibs_predictor/web.py"
  echo "$MSG"
  if command -v osascript >/dev/null 2>&1; then
    osascript -e "display dialog \"${MSG}\" buttons {\"OK\"} default button \"OK\" with title \"hibs-bet\" giving up after 120"
  fi
  exit 1
fi

open_dashboard "$PORT"
wait "$APP_PID"
