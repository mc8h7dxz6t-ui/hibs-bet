#!/usr/bin/env bash
# Remote post-sync steps (run on VPS via ssh). Expects cwd = DEPLOY_PATH.
set -euo pipefail

APP="${DEPLOY_PATH:-$(pwd)}"
cd "$APP"

if [[ -x .venv/bin/pip ]]; then
  .venv/bin/pip install -q -r requirements.txt
else
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

cp deploy/hibs-bet.service /etc/systemd/system/hibs-bet.service
systemctl daemon-reload

CACHE_DIR="${HIBS_CACHE_DIR:-${APP}/.cache}"
if grep -qE '^HIBS_CACHE_BUST=1' "${APP}/.env" 2>/dev/null; then
  echo "==> HIBS_CACHE_BUST=1 — clear fixture caches"
  rm -f "${CACHE_DIR}"/all_fixtures_*.json "${CACHE_DIR}"/fixtures_*.json \
    "${CACHE_DIR}"/league_*.json "${CACHE_DIR}"/enriched_fixture_*.json 2>/dev/null || true
  sed -i '/^HIBS_CACHE_BUST=1/d' "${APP}/.env"
else
  echo "==> keep fixture disk cache (set HIBS_CACHE_BUST=1 in .env once to bust)"
fi
chown -R www-data:www-data "${CACHE_DIR}" 2>/dev/null || true

bash deploy/apply-vps-safe-production.sh

if [[ "$(id -u)" -eq 0 ]]; then
  systemctl restart hibs-bet.service
else
  sudo systemctl restart hibs-bet.service
fi

echo "==> $(systemctl is-active hibs-bet.service 2>/dev/null || echo unknown)"
