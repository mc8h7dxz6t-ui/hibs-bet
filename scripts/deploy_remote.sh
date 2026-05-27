#!/usr/bin/env bash
# Run on the VPS after `git pull` (legacy git-based deploy).
# GitLab CI uses scripts/deploy_ci_from_runner.sh (rsync) when the server has no git clone.
# Local Mac: prefer ./scripts/deploy_to_vps.sh
set -euo pipefail

if [[ -n "${DEPLOY_PATH:-}" ]]; then
  REPO_ROOT="$DEPLOY_PATH"
else
  REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
cd "$REPO_ROOT"

if [[ -d .git ]]; then
  git pull --ff-only
else
  echo "deploy_remote.sh: no .git in ${REPO_ROOT} — use deploy_ci_from_runner.sh (CI) or deploy_to_vps.sh (Mac rsync)" >&2
  exit 1
fi

export DEPLOY_PATH="$REPO_ROOT"
bash "${REPO_ROOT}/scripts/_deploy_vps_post.sh"
