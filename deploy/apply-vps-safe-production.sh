#!/usr/bin/env bash
# Safer full-data profile for ~2GB VPS (hibs-bet.co.uk).
# Run on the server as root after code is in /opt/hibs-bet:
#   sudo bash /opt/hibs-bet/deploy/apply-vps-safe-production.sh
#
# From your Mac (if SSH works):
#   ssh root@77.68.89.73 'bash -s' < deploy/apply-vps-safe-production.sh
#   # or: scp deploy/apply-vps-safe-production.sh root@77.68.89.73:/tmp/ && ssh root@77.68.89.73 sudo bash /tmp/apply-vps-safe-production.sh
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-bet}"
ENV_FILE="${APP_ROOT}/.env"
SERVICE_DST="/etc/systemd/system/hibs-bet.service"
NGINX_SITE="/etc/nginx/sites-available/hibs-bet"
LITE_MARKER="# --- VPS 1GB production tuning (hibs-bet deploy) ---"
SAFE_MARKER="# --- VPS 2GB safer full data (hibs-bet deploy) ---"

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

strip_lite_block() {
  local f="$1"
  [[ -f "$f" ]] || return 0
  if ! grep -qF "${LITE_MARKER}" "$f"; then
    return 0
  fi
  local tmp
  tmp="$(mktemp)"
  awk -v m="${LITE_MARKER}" '
    $0 == m { skip=1; next }
    skip && /^HIBS_/ { next }
    skip && /^$/ { skip=0; next }
    skip && /^#/ { skip=0 }
    { print }
  ' "$f" >"$tmp"
  mv "$tmp" "$f"
  echo "    Removed 1GB lite tuning block from ${f}"
}

strip_unwanted_env() {
  local f="$1"
  [[ -f "$f" ]] || return 0
  local tmp
  tmp="$(mktemp)"
  grep -vE '^(HIBS_PREFER_FOOTBALL_DATA_FIXTURES=1|HIBS_DISABLE_API_SPORTS=1)\s*$' "$f" >"$tmp" || true
  mv "$tmp" "$f"
}

upsert_safe_env() {
  local f="$1"
  touch "$f"
  strip_lite_block "$f"
  strip_unwanted_env "$f"
  if grep -qF "${SAFE_MARKER}" "$f"; then
    local tmp
    tmp="$(mktemp)"
    awk -v m="${SAFE_MARKER}" '
      $0 == m { skip=1; next }
      skip && /^HIBS_/ { next }
      skip && /^$/ { skip=0; next }
      skip && /^[^#]/ { skip=0 }
      { print }
    ' "$f" >"$tmp"
    mv "$tmp" "$f"
  fi
  cat >>"$f" <<EOF

${SAFE_MARKER}
HIBS_FETCH_DAYS=7
HIBS_MAX_DATA=1
HIBS_DASHBOARD_LITE=0
HIBS_ALWAYS_DEEP_SCRAPE=0
HIBS_SKIP_HEAVY_WHEN_API_STRONG=1
HIBS_FIXTURE_FETCH_WORKERS=3
HIBS_WARM_FIXTURE_CACHE=1
HIBS_ENABLE_PLAYER_INSIGHT=1
HIBS_USE_INJURY_LAMBDA_ADJUST=1
EOF
  chown www-data:www-data "$f"
  chmod 640 "$f"
  echo "    Applied safer full-data flags to ${f}"
}

echo "==> Production .env (safer 2GB profile)"
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "    No ${ENV_FILE} — copy from .env.example on the server before restart." >&2
else
  upsert_safe_env "${ENV_FILE}"
fi

echo "==> systemd (2 workers, 180s timeout, HOME=${APP_ROOT})"
cp "${APP_ROOT}/deploy/hibs-bet.service" "${SERVICE_DST}"
sed -i 's/--workers [0-9]\+/--workers 2/' "${SERVICE_DST}"
sed -i 's/--timeout [0-9]\+/--timeout 180/' "${SERVICE_DST}"
systemctl daemon-reload
systemctl enable hibs-bet

echo "==> nginx proxy timeouts (180s, >= gunicorn)"
if [[ -f "${NGINX_SITE}" ]]; then
  sed -i 's/proxy_connect_timeout [0-9]\+s/proxy_connect_timeout 180s/g' "${NGINX_SITE}" 2>/dev/null || true
  sed -i 's/proxy_read_timeout [0-9]\+s/proxy_read_timeout 180s/g' "${NGINX_SITE}" 2>/dev/null || true
  sed -i 's/proxy_send_timeout [0-9]\+s/proxy_send_timeout 180s/g' "${NGINX_SITE}" 2>/dev/null || true
  if ! grep -q 'proxy_read_timeout' "${NGINX_SITE}"; then
    sed -i '/proxy_set_header X-Forwarded-Proto/a\        proxy_connect_timeout 180s;\n        proxy_read_timeout 180s;\n        proxy_send_timeout 180s;' "${NGINX_SITE}"
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
echo "Done. Safer profile: 7-day window, MAX_DATA=1, live dashboard, skip heavy when APIs strong."
echo "Test:"
echo "  curl -sS --max-time 30 -o /dev/null -w 'health %{http_code}\n' http://127.0.0.1:8000/api/health"
echo "  curl -sS --max-time 200 -o /dev/null -w 'home %{http_code}\n' http://127.0.0.1:8000/"
