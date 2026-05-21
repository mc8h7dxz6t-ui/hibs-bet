#!/usr/bin/env bash
# Run on the VPS (e.g. GitLab: ssh ... "export DEPLOY_PATH=...; bash -s" < scripts/deploy_remote.sh).
# Or run locally from a checkout: export DEPLOY_PATH=/path/to/repo (optional); ./scripts/deploy_remote.sh
# Expects: git remote configured, optional VENV_PATH (default: REPO_ROOT/.venv), systemd unit hibs-bet.
set -euo pipefail

if [[ -n "${DEPLOY_PATH:-}" ]]; then
  REPO_ROOT="$DEPLOY_PATH"
else
  REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
cd "$REPO_ROOT"

git pull --ff-only

VENV="${VENV_PATH:-$REPO_ROOT/.venv}"
if [[ ! -x "$VENV/bin/pip" ]]; then
  echo "deploy_remote.sh: missing venv at $VENV (create: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt)" >&2
  exit 1
fi

"$VENV/bin/pip" install -r requirements.txt

CACHE_DIR="${HIBS_CACHE_DIR:-$REPO_ROOT/.cache}"
if [[ -d "$CACHE_DIR" ]]; then
  rm -f "$CACHE_DIR"/fixtures_* "$CACHE_DIR"/all_fixtures_* "$CACHE_DIR"/enriched_fixture_* 2>/dev/null || true
fi

sudo systemctl restart hibs-bet.service
