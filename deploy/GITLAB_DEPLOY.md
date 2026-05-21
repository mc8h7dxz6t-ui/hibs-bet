# GitLab CI deploy (hibs-bet.co.uk)

Production lives at **`/opt/hibs-bet`** (see `deploy/hibs-bet.service`). Pushing to the **default branch** (`main`) runs tests, then SSH deploys to the VPS.

**Why the site stayed old after `git push`:** deploy only runs in GitLab CI (not from your laptop). Until CI variables and server SSH are set up, pipelines fail or skip deploy. Previously deploy was **manual**; it is now **automatic** on `main` after tests pass.

---

## 1. GitLab project variables (one-time)

In GitLab: **Settings → CI/CD → Variables → Add variable**

| Variable | Type | Protected | Masked | Example / notes |
|----------|------|-----------|--------|-----------------|
| `SSH_PRIVATE_KEY` | **File** (preferred) or Variable | Yes | No* | PEM private key for the deploy SSH user. Full key including `-----BEGIN ...-----` / `-----END ...-----`. *File type cannot be masked. |
| `DEPLOY_HOST` | Variable | Yes | No | VPS hostname or IP serving hibs-bet.co.uk |
| `DEPLOY_USER` | Variable | Yes | No | SSH user (e.g. `deploy` or `www-data`) |
| `DEPLOY_PATH` | Variable | Yes | No | `/opt/hibs-bet` (default in `.gitlab-ci.yml` if omitted) |

**Optional but recommended**

| Variable | Notes |
|----------|--------|
| `SSH_KNOWN_HOSTS` | Output of `ssh-keyscan -H your.vps.example.com` — avoids MITM on first connect |

Do **not** commit keys or `.env` to the repo.

---

## 2. Server one-time setup

On the VPS (as root or with sudo):

### 2.1 Clone app

```bash
sudo mkdir -p /opt/hibs-bet
sudo chown "$DEPLOY_USER:$DEPLOY_USER" /opt/hibs-bet
sudo -u "$DEPLOY_USER" git clone git@gitlab.com:hibsbetting-group/hibsbetting.git /opt/hibs-bet
cd /opt/hibs-bet
git checkout main
```

`$DEPLOY_USER` must be able to **`git pull`** here (GitLab deploy key on the server, or HTTPS token in `~/.git-credentials`).

### 2.2 Python venv

```bash
cd /opt/hibs-bet
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 2.3 Secrets and cache

```bash
cp .env.example .env
# edit /opt/hibs-bet/.env — API keys, HIBS_CACHE_DIR=/opt/hibs-bet/.cache, etc.
```

### 2.4 systemd

```bash
sudo cp /opt/hibs-bet/deploy/hibs-bet.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hibs-bet
```

### 2.5 Authorize GitLab CI SSH key

On your laptop, create a key pair used **only** for CI (do not commit the private key):

```bash
ssh-keygen -t ed25519 -f gitlab-ci-deploy -N ""
```

- Add **`gitlab-ci-deploy` (private)** to GitLab as `SSH_PRIVATE_KEY` (File variable).
- Append **`gitlab-ci-deploy.pub`** to the server:

```bash
# on server, as DEPLOY_USER
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo 'PASTE_PUBLIC_KEY_LINE' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

### 2.6 Passwordless sudo for restart

GitLab runs `scripts/deploy_remote.sh`, which ends with `sudo systemctl restart hibs-bet.service`.

```bash
sudo visudo -f /etc/sudoers.d/hibs-bet-deploy
```

Example (replace `deploy` with your `DEPLOY_USER`):

```
deploy ALL=(root) NOPASSWD: /bin/systemctl restart hibs-bet.service, /bin/systemctl status hibs-bet.service
```

---

## 3. What happens on push to `main`

1. **test** — `python test_app.py` (project test runner; fast sanity check).
2. **deploy_production** — SSH to `DEPLOY_USER@DEPLOY_HOST`, run `scripts/deploy_remote.sh`:
   - `git pull --ff-only`
   - `.venv/bin/pip install -r requirements.txt`
   - remove stale fixture cache files under `.cache/`
   - `sudo systemctl restart hibs-bet.service`

Check **CI/CD → Pipelines** in GitLab. A green deploy job means production was updated.

**Manual deploy** (re-run without a new commit): open the latest pipeline on `main` → play button on **deploy_production** if you temporarily set it to manual, or push an empty commit.

---

## 4. Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| Pipeline passes but site unchanged | Deploy job skipped (not on `main`) or failed — open job logs |
| `Permission denied (publickey)` | Wrong `SSH_PRIVATE_KEY` or pubkey not in `authorized_keys` |
| `git pull` fails on server | Server clone has no fetch credentials; add GitLab deploy key to project and server |
| `sudo: a password is required` | Missing sudoers rule for `systemctl restart` |
| App old data after deploy | Fixture cache — deploy script clears `fixtures_*` / `all_fixtures_*`; use dashboard Refresh if needed |

Local checklist: [deploy/README.md](README.md).

---

## 5. Alternative: pull-based deploy (webhook on server)

Use this if you prefer **not** to store `SSH_PRIVATE_KEY` in GitLab. GitLab still runs tests; deploy is triggered on the VPS.

1. Install a small webhook listener on the server (e.g. `webhook` package or a 20-line Flask hook) listening only on localhost or firewalled port.
2. In GitLab: **Settings → Webhooks** → URL `https://your-vps/internal/deploy` (or SSH tunnel), trigger **Push events** on `main`, secret token.
3. Webhook script runs the same steps as `scripts/deploy_remote.sh` (pull, pip, cache clear, restart).

**Trade-offs:** no CI SSH key in GitLab; you must secure the webhook URL and token. The SSH pipeline in `.gitlab-ci.yml` is the default for this repo.

---

## 6. Related files

- `.gitlab-ci.yml` — pipeline definition
- `scripts/deploy_remote.sh` — remote deploy steps
- `deploy/hibs-bet.service` — gunicorn on `:8000`
