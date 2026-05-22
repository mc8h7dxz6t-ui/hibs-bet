#!/usr/bin/env bash
# Sync repo from this Mac to production VPS (does not touch server .env).
# Usage: ./scripts/deploy_to_vps.sh
# Env overrides: DEPLOY_HOST DEPLOY_USER DEPLOY_PATH
set -euo pipefail

HOST="${DEPLOY_HOST:-77.68.89.75}"
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
  bash deploy/apply-vps-production-tuning.sh
"

echo "==> smoke test"
curl -sS --max-time 30 -o /dev/null -w 'health %{http_code}\n' "https://hibs-bet.co.uk/api/health" || true
