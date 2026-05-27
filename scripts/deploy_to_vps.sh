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
ssh "${USER}@${HOST}" "export DEPLOY_PATH='${APP}'; bash -s" < "${REPO_ROOT}/scripts/_deploy_vps_post.sh"

echo "==> smoke test"
curl -sS --max-time 30 -o /dev/null -w 'health %{http_code}\n' "https://hibs-bet.co.uk/api/health" || true
