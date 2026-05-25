#!/usr/bin/env bash
# Sync repo from this Mac to production VPS (does not touch server .env).
# Usage: ./scripts/deploy_to_vps.sh
# Env overrides: DEPLOY_HOST DEPLOY_USER DEPLOY_PATH
set -euo pipefail

HOST="${DEPLOY_HOST:-77.68.89.73}"
USER="${DEPLOY_USER:-root}"
APP="${DEPLOY_PATH:-/opt/hibs-bet}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> rsync ${REPO_ROOT}/ -> ${USER}@${HOST}:${APP}/"
rsync -avz --delete \
  --exclude '.venv/' \
  --exclude '.cache/' \
  --exclude '.env' \
  --exclude '.env.*' \
  --exclude '.git/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.DS_Store' \
  "${REPO_ROOT}/" "${USER}@${HOST}:${APP}/"

echo "==> remote install + tuning + restart"
ssh "${USER}@${HOST}" "set -euo pipefail
  cd '${APP}'
  if [[ -x .venv/bin/pip ]]; then
    .venv/bin/pip install -q -r requirements.txt
  else
    python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
  fi
  cp deploy/hibs-bet.service /etc/systemd/system/hibs-bet.service
  CACHE_DIR=\"\${HIBS_CACHE_DIR:-${APP}/.cache}\"
  echo \"==> clear fixture caches (v28 + dq8 enrich)\"
  rm -f \"\${CACHE_DIR}\"/all_fixtures_*.json \"\${CACHE_DIR}\"/fixtures_*.json \"\${CACHE_DIR}\"/league_*.json \"\${CACHE_DIR}\"/enriched_fixture_*.json 2>/dev/null || true
  chown -R www-data:www-data \"\${CACHE_DIR}\" 2>/dev/null || true
  bash deploy/apply-vps-production-tuning.sh
"

echo "==> smoke test"
curl -sS --max-time 30 -o /dev/null -w 'health %{http_code}\n' "https://hibs-bet.co.uk/api/health" || true
