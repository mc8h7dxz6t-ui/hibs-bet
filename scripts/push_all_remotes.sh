#!/usr/bin/env bash
# Push main to GitHub (origin) and GitLab (production CI). No feature/DQ changes — sync only.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

branch="${1:-main}"
if [[ "$(git branch --show-current)" != "$branch" ]]; then
  echo "ERROR: checkout $branch first (on $(git branch --show-current))." >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: uncommitted changes — commit or stash before pushing." >&2
  git status -sb
  exit 1
fi

echo "==> GitHub (origin)"
git push origin "$branch"

echo "==> GitLab (gitlab)"
if ! git remote get-url gitlab &>/dev/null; then
  echo "GitLab remote missing. Run:"
  echo "  git remote add gitlab git@gitlab.com:hibsbetting-group/hibsbetting.git"
  exit 0
fi

gitlab_pushed=0
if ssh -o BatchMode=yes -T git@gitlab.com 2>&1 | grep -q 'Welcome to GitLab'; then
  git fetch gitlab "$branch" 2>/dev/null || true
  git push gitlab "$branch" --force-with-lease
  echo "GitLab updated (SSH)."
  gitlab_pushed=1
elif [[ -f "$REPO_ROOT/.env" ]] && grep -q '^GITLAB_TOKEN=' "$REPO_ROOT/.env" 2>/dev/null; then
  # shellcheck disable=SC1091
  set -a && source "$REPO_ROOT/.env" && set +a
  if [[ -n "${GITLAB_TOKEN:-}" ]]; then
    git push "https://oauth2:${GITLAB_TOKEN}@gitlab.com/hibsbetting-group/hibsbetting.git" \
      "$branch" --force-with-lease
    echo "GitLab updated (HTTPS token)."
    gitlab_pushed=1
  fi
fi

if [[ "$gitlab_pushed" -eq 0 ]]; then
  echo "GitLab push skipped: add your SSH key (deploy/GITLAB_SSH_SETUP.md)"
  echo "  or set GITLAB_TOKEN in .env (write_repository scope)."
  echo "  Your public key:"
  cat "${HOME}/.ssh/id_ed25519.pub" 2>/dev/null || cat "${HOME}/.ssh/id_rsa.pub" 2>/dev/null || true
fi

echo "==> Done. Tip: ./scripts/vps_restart_test.sh after deploy"
