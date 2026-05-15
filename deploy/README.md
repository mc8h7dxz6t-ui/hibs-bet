# Deploy

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
