# Deploy

**GitLab CI (hibs-bet.co.uk):** see [GITLAB_DEPLOY.md](GITLAB_DEPLOY.md) — variables, SSH key, push-to-`main` pipeline.

## Production (`hibs-bet.service`)

- Gunicorn binds **0.0.0.0:8000** (see `hibs-bet.service`).
- Working directory: `/opt/hibs-bet` (adjust on your server).
- Secrets: `/opt/hibs-bet/.env` (from `.env.example`).

```bash
sudo cp deploy/hibs-bet.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hibs-bet
```

### HTTPS (nginx + Let's Encrypt)

Gunicorn only listens on **:8000**. For `https://hibs-bet.co.uk`:

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx
sudo cp deploy/hibs-bet.nginx.conf /etc/nginx/sites-available/hibs-bet
sudo ln -sf /etc/nginx/sites-available/hibs-bet /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d hibs-bet.co.uk -d www.hibs-bet.co.uk
```


### Safer full data (~2GB VPS)

Balanced profile: 7-day fixture window, `HIBS_MAX_DATA=1`, live dashboard (`HIBS_DASHBOARD_LITE=0`), skip heavy scrapes when APIs are strong, 3 fixture workers, warm cache, player/injury insight flags. Gunicorn **2 workers**, **180s** timeout.

```bash
sudo bash /opt/hibs-bet/deploy/apply-vps-safe-production.sh
```

**From your Mac:** SSH must use your deploy key (`root@77.68.89.73`). If you see `Permission denied (publickey,password)`, the Cursor agent sandbox cannot use your Mac keychain — run the script locally:

```bash
ssh root@77.68.89.73 'cd /opt/hibs-bet && git pull && sudo bash deploy/apply-vps-safe-production.sh'
```

Or pipe the script: `ssh root@77.68.89.73 'bash -s' < deploy/apply-vps-safe-production.sh` (after `git pull` on the server so the script exists).

### 1 GB VPS tuning (worker timeout / OOM)

Default unit uses **1 worker** and **300s** timeout. After deploy, on the server:

```bash
sudo bash /opt/hibs-bet/deploy/apply-vps-production-tuning.sh
```

Sets `www-data` ownership on `.cache`, appends lite `.env` flags (`HIBS_DASHBOARD_LITE`, `HIBS_WARM_FIXTURE_CACHE`, …), patches nginx timeouts, restarts `hibs-bet`.

## Staging (`hibs-bet-staging.service`)

Run staging **beside** production on a different port and cache directory so you can test `HIBS_MAX_DATA=1`, Scottish FBref xG, and UI changes without touching live traffic.

| | Production | Staging |
|---|------------|---------|
| Unit | `hibs-bet.service` | `hibs-bet-staging.service` |
| Port | 8000 | **8001** |
| Env file | `.env` | **`.env.staging`** |
| Cache | `.cache` (default) | **`.cache-staging`** |

```bash
# On server (example paths)
sudo mkdir -p /opt/hibs-bet-staging
# deploy code + venv, then:
cp deploy/staging.env.example /opt/hibs-bet-staging/.env.staging
# edit keys in .env.staging

sudo cp deploy/hibs-bet-staging.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hibs-bet-staging
```

Local dev (no systemd): `PORT=5002 PYTHONPATH=src python3 src/hibs_predictor/web.py` with `HIBS_CACHE_DIR=.cache-staging` in `.env`.

## Pre-push checklist (hibs-bet.co.uk)

### Must-do

- [ ] `pytest test_app.py -q tests/test_betting_strategy.py tests/test_assistant_features.py` — all green
- [ ] Server `.env` from `.env.example` (at minimum: `FOOTBALL_DATA_ORG_KEY`, `ODDS_API_KEY`; add `API_SPORTS_FOOTBALL_KEY` / `SPORTSMONK_KEY` if you use them)
- [ ] `HIBS_CACHE_DIR` set for production (systemd: `/opt/hibs-bet/.cache` in `hibs-bet.service`)
- [ ] After deploy: clear fixture cache for **v22** (dashboard Refresh or `POST /api/cache/clear`; delete stale `fixtures_*` / `all_fixtures_*` if needed)
- [ ] `sudo systemctl daemon-reload && sudo systemctl restart hibs-bet` (gunicorn **:8000**)

### Should-do

- [ ] `HIBS_PREDICTION_LOG_ENABLED=1` + `HIBS_CLV_LOG_ENABLED=1` (+ daily `pred-log-sync`, weekly `calibration-fit` via `deploy/cron-hibs-calibration.sh`)
- [ ] Scrape flags aligned with quota: `HIBS_MAX_DATA`, `HIBS_ENABLE_HEAVY_SCRAPERS`, `HIBS_ENABLE_FOTMOB_FIXTURES` (default on)
- [ ] Players dock: on by default (right rail); hide with `HIBS_SHOW_PLAYERS_DOCK=0`
- [ ] Optional Sky dock: `HIBS_SHOW_SKY_PANEL=1` (off by default); hides automatically if YouTube embed probe fails
- [ ] Deep enrich: safe production sets `HIBS_TARGET_DQ_PCT=90`, `HIBS_DEEP_ENRICH_TODAY_ONLY=1`, `HIBS_DEEP_ENRICH_MAX_RETRIES=2` (today’s fixtures only; stays within API budget)

### Nice-to-have (defer)

- [ ] Staging side-by-side on **:8001** (`hibs-bet-staging.service`)
- [ ] `HIBS_AUDIT_API_TOKEN` for `/api/audit/summary`
- [ ] Fit `calibration_v1.json` after enough logged results

### Do not

- Commit `.env`, `.env.txt`, or API keys
- Share production `.cache` with staging
