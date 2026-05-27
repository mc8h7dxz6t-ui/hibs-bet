#!/usr/bin/env bash
# Legacy entrypoint — delegates to the full-data VPS profile (removes 1GB lite flags).
#   sudo bash /opt/hibs-bet/deploy/apply-vps-production-tuning.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${ROOT}/apply-vps-safe-production.sh"
