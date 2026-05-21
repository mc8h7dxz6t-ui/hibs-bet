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

- [ ] `HIBS_PREDICTION_LOG_ENABLED=1` (+ periodic `pred-log-sync`) for calibration / CLV
- [ ] Scrape flags aligned with quota: `HIBS_MAX_DATA`, `HIBS_ENABLE_HEAVY_SCRAPERS`, `HIBS_ENABLE_FOTMOB_FIXTURES` (default on)
- [ ] Sky dock: `HIBS_SHOW_SKY_PANEL=1` (default); panel hides automatically if YouTube embed probe fails
- [ ] Deep enrich only when needed: `HIBS_DEEP_ENRICH=1` or `HIBS_TARGET_DQ_PCT` (off by default — extra HTTP)

### Nice-to-have (defer)

- [ ] Staging side-by-side on **:8001** (`hibs-bet-staging.service`)
- [ ] `HIBS_AUDIT_API_TOKEN` for `/api/audit/summary`
- [ ] Fit `calibration_v1.json` after enough logged results

### Do not

- Commit `.env`, `.env.txt`, or API keys
- Share production `.cache` with staging
