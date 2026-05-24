#!/usr/bin/env bash
# VPS cron helpers for prediction audit sync + weekly calibration fit.
#
# Install (as root on the server):
#   sudo bash /opt/hibs-bet/deploy/cron-hibs-calibration.sh --install
#
# Or paste the CRON_LINES below into `crontab -u www-data -e`.
#
# Requires: HIBS_PREDICTION_LOG_ENABLED=1, API_SPORTS_FOOTBALL_KEY in .env.
# CLV closing odds: HIBS_CLV_LOG_ENABLED=1 (set by apply-vps-safe-production.sh).
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-bet}"
PY="${APP_ROOT}/.venv/bin/python"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"

CRON_LINES=(
  "# hibs-bet: backfill FT scores + closing 1X2 for CLV (daily 06:30 UTC)"
  "30 6 * * * cd ${APP_ROOT} && HOME=${APP_ROOT} PYTHONPATH=src ${PY} -m hibs_predictor.main pred-log-sync >> ${LOG_DIR}/pred-log-sync.log 2>&1"
  "# hibs-bet: fit league Brier shrink → .cache/calibration_v1.json (Sun 07:00 UTC)"
  "0 7 * * 0 cd ${APP_ROOT} && HOME=${APP_ROOT} PYTHONPATH=src ${PY} -m hibs_predictor.main calibration-fit >> ${LOG_DIR}/calibration-fit.log 2>&1"
)

usage() {
  echo "Usage: $0 [--print|--install]"
  echo "  --print    Show recommended crontab lines (default)"
  echo "  --install  Append lines to www-data crontab (skips duplicates)"
}

print_lines() {
  printf '%s\n' "${CRON_LINES[@]}"
}

install_cron() {
  mkdir -p "${LOG_DIR}"
  chown www-data:www-data "${LOG_DIR}" 2>/dev/null || true
  local existing tmp marker
  marker="# hibs-bet: backfill FT scores"
  existing="$(crontab -u www-data -l 2>/dev/null || true)"
  if printf '%s\n' "${existing}" | grep -qF "${marker}"; then
    echo "Cron already contains hibs-bet pred-log-sync line — skipping install."
    print_lines
    exit 0
  fi
  tmp="$(mktemp)"
  {
    printf '%s\n' "${existing}"
    printf '\n'
    print_lines
  } >"${tmp}"
  crontab -u www-data "${tmp}"
  rm -f "${tmp}"
  echo "Installed www-data crontab entries. Logs: ${LOG_DIR}/pred-log-sync.log, calibration-fit.log"
}

case "${1:---print}" in
  --print) print_lines ;;
  --install) install_cron ;;
  -h|--help) usage ;;
  *) usage; exit 1 ;;
esac
