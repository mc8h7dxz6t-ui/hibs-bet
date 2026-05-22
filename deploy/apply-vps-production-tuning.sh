#!/usr/bin/env bash
# Run on the VPS as root after code is in /opt/hibs-bet:
#   sudo bash /opt/hibs-bet/deploy/apply-vps-production-tuning.sh
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-bet}"
ENV_FILE="${APP_ROOT}/.env"
SERVICE_DST="/etc/systemd/system/hibs-bet.service"
NGINX_SITE="/etc/nginx/sites-available/hibs-bet"
MARKER="# --- VPS 1GB production tuning (hibs-bet deploy) ---"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

if [[ ! -d "${APP_ROOT}/deploy" ]]; then
  echo "Missing ${APP_ROOT}/deploy — sync or git pull the repo first." >&2
  exit 1
fi

echo "==> Permissions (www-data)"
mkdir -p "${APP_ROOT}/.cache"
touch "${APP_ROOT}/.rate_limit_state.json" 2>/dev/null || true
chown -R www-data:www-data "${APP_ROOT}/.cache" "${APP_ROOT}/.rate_limit_state.json" 2>/dev/null || true
chown -R www-data:www-data "${APP_ROOT}"
if [[ -f "${ENV_FILE}" ]]; then
  chown www-data:www-data "${ENV_FILE}"
  chmod 640 "${ENV_FILE}"
fi

echo "==> systemd (1 worker, 300s timeout, HOME=${APP_ROOT})"
cp "${APP_ROOT}/deploy/hibs-bet.service" "${SERVICE_DST}"
systemctl daemon-reload
systemctl enable hibs-bet

echo "==> Production .env lite flags (append if missing)"
if [[ -f "${ENV_FILE}" ]] && ! grep -qF "${MARKER}" "${ENV_FILE}"; then
  cat >>"${ENV_FILE}" <<EOF

${MARKER}
HIBS_FETCH_DAYS=3
HIBS_MAX_DATA=0
HIBS_ALWAYS_DEEP_SCRAPE=0
HIBS_SKIP_HEAVY_WHEN_API_STRONG=1
HIBS_DASHBOARD_LITE=1
HIBS_FIXTURE_FETCH_WORKERS=3
HIBS_WARM_FIXTURE_CACHE=1
EOF
  chown www-data:www-data "${ENV_FILE}"
  chmod 640 "${ENV_FILE}"
  echo "    Appended lite flags to ${ENV_FILE}"
elif [[ ! -f "${ENV_FILE}" ]]; then
  echo "    No ${ENV_FILE} — copy from your Mac with scp before restart."
else
  echo "    Lite flags already present in ${ENV_FILE}"
fi

echo "==> nginx proxy timeouts (300s)"
if [[ -f "${NGINX_SITE}" ]]; then
  if ! grep -q 'proxy_read_timeout' "${NGINX_SITE}"; then
    sed -i '/proxy_set_header X-Forwarded-Proto/a\        proxy_connect_timeout 300s;\n        proxy_read_timeout 300s;\n        proxy_send_timeout 300s;' "${NGINX_SITE}"
    echo "    Added timeouts to ${NGINX_SITE}"
  else
    echo "    Timeouts already in ${NGINX_SITE}"
  fi
  nginx -t
  systemctl reload nginx
else
  echo "    No ${NGINX_SITE} — install from deploy/hibs-bet.nginx.conf + certbot if needed."
fi

echo "==> Restart hibs-bet"
systemctl restart hibs-bet
sleep 2
systemctl status hibs-bet --no-pager || true

echo ""
echo "Test (health should be fast; / may take 1–3 min first load):"
echo "  curl -sS --max-time 30 -o /dev/null -w 'health %{http_code}\n' http://127.0.0.1:8000/api/health"
echo "  curl -sS --max-time 300 -o /dev/null -w 'home %{http_code}\n' http://127.0.0.1:8000/"
