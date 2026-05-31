#!/bin/bash
# Install hibs-bet local cron (macOS/Linux) — prediction log sync + weekly calibration.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PY="${ROOT}/.venv/bin/python"
LOG_DIR="${ROOT}/logs"
mkdir -p "${LOG_DIR}"

if [[ ! -x "${PY}" ]]; then
  echo "ERROR: ${PY} not found — run: python3 -m venv .venv && pip install -e ." >&2
  exit 1
fi

SYNC="cd ${ROOT} && HOME=${ROOT} PYTHONPATH=src ${PY} -m hibs_predictor.main pred-log-sync --verbose >> ${LOG_DIR}/pred-log-sync.log 2>&1"
EVENING="cd ${ROOT} && HOME=${ROOT} PYTHONPATH=src ${PY} -m hibs_predictor.main pred-log-sync --verbose >> ${LOG_DIR}/pred-log-sync-evening.log 2>&1"
CALIB="cd ${ROOT} && HOME=${ROOT} PYTHONPATH=src ${PY} -m hibs_predictor.main calibration-fit >> ${LOG_DIR}/calibration-fit.log 2>&1"

# 06:30 and 23:00 local time (set TZ=UTC in crontab if you prefer UTC on VPS)
CRON_0630="30 6 * * * ${SYNC}"
CRON_2300="0 23 * * * ${EVENING}"
CRON_WEEKLY="0 7 * * 0 ${CALIB}"

EXISTING="$(crontab -l 2>/dev/null || true)"
FILTERED="$(printf '%s\n' "${EXISTING}" \
  | grep -v 'hibs_predictor.main pred-log-sync' \
  | grep -v 'hibs_predictor.main calibration-fit' \
  | sed '/^$/d' || true)"

{
  printf '%s\n' "${FILTERED}"
  echo "# hibs-bet automation"
  echo "${CRON_0630}"
  echo "${CRON_2300}"
  echo "${CRON_WEEKLY}"
} | crontab -

echo "Installed hibs-bet cron jobs:"
crontab -l | grep -A3 'hibs-bet automation' || true
echo ""
echo "Morning sync:  06:30 local"
echo "Evening sync:  23:00 local"
echo "Calibration:   Sun 07:00 local"
echo "Logs:          ${LOG_DIR}/"
echo "Requires:      HIBS_PREDICTION_LOG_ENABLED=1 in .env"
