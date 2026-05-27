#!/usr/bin/env bash
# GitLab CI deploy: rsync checkout to VPS (no git required on server).
# Requires: DEPLOY_HOST, DEPLOY_USER, SSH agent with SSH_PRIVATE_KEY loaded.
# Optional: DEPLOY_PATH (default /opt/hibs-bet).
set -euo pipefail

HOST="${DEPLOY_HOST:?Set DEPLOY_HOST in GitLab CI/CD variables}"
USER="${DEPLOY_USER:?Set DEPLOY_USER in GitLab CI/CD variables}"
APP="${DEPLOY_PATH:-/opt/hibs-bet}"
REPO_ROOT="${CI_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

echo "==> rsync ${REPO_ROOT}/ -> ${USER}@${HOST}:${APP}/"
rsync -avz --delete \
  --exclude '.venv/' \
  --exclude '.cache/' \
  --exclude '.cache-staging/' \
  --exclude '.env' \
  --exclude '.env.*' \
  --exclude '.git/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.DS_Store' \
  --exclude 'data/prediction_audit.sqlite' \
  "${REPO_ROOT}/" "${USER}@${HOST}:${APP}/"

echo "==> remote install + tuning + restart"
ssh -o StrictHostKeyChecking=yes -o BatchMode=yes "${USER}@${HOST}" \
  "export DEPLOY_PATH='${APP}'; bash -s" < "${REPO_ROOT}/scripts/_deploy_vps_post.sh"

echo "==> deploy complete"
