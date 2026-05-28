#!/usr/bin/env bash
# Restart production app after rsync deploy and run smoke checks.
set -euo pipefail

HOST="${DEPLOY_HOST:-77.68.89.73}"
USER="${DEPLOY_USER:-root}"
APP="${DEPLOY_PATH:-/opt/hibs-bet}"
CLEAR_CACHE="${CLEAR_CACHE:-1}"

echo "==> restart hibs-bet on ${USER}@${HOST}"
ssh "${USER}@${HOST}" "sudo systemctl restart hibs-bet && sleep 2 && sudo systemctl is-active hibs-bet"

if [[ "$CLEAR_CACHE" == "1" ]]; then
  echo "==> clear stale fixture cache (one-time after big deploy)"
  ssh "${USER}@${HOST}" "sudo -u www-data rm -rf ${APP}/.cache/all_fixtures* ${APP}/.cache/league_* 2>/dev/null || true"
fi

echo "==> smoke tests"
curl -sS --max-time 30 -o /dev/null -w 'health %{http_code}\n' "https://hibs-bet.co.uk/api/health" || true
curl -sS --max-time 30 -o /dev/null -w 'login %{http_code}\n' "https://hibs-bet.co.uk/login" || true

echo "==> deployed markers on server"
ssh "${USER}@${HOST}" "grep -q block_reason ${APP}/src/hibs_predictor/rate_limiter.py && echo 'hardening: ok'; test -f ${APP}/templates/_players_dock.html && echo 'players dock: ok'"

echo "Done. Hard-refresh the browser (Cmd+Shift+R). Check Settings → Hibs Home/Away UI and right Players dock."
