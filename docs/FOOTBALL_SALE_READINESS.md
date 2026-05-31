# Football asset sale readiness (hibs-bet)

## What buyers need to see

1. **Closed audit loop** — pre-kickoff snapshots joined to full-time results in `data/prediction_audit.sqlite`.
2. **Calibration proof** — Brier score (1X2) and log loss on `/performance` and `pred-log-report` (target: Brier &lt; 0.66 baseline on scale cohort).
3. **Transparent league profiles** — coefficients in `config/league_profiles.yaml`, not hidden Python tweaks.
4. **API sustainability** — chunked enrich (`HIBS_ENRICH_CHUNK_SIZE=8`, `HIBS_ENRICH_CHUNK_PAUSE_SEC=65`) for Football-Data.org 10 req/min.

## Close the loop (ops)

```bash
# On VPS (www-data)
sudo bash /opt/hibs-bet/deploy/cron-hibs-calibration.sh --install

# One-off backfill after deploy
cd /opt/hibs-bet && HOME=/opt/hibs-bet PYTHONPATH=src .venv/bin/python -m hibs_predictor.main pred-log-sync --verbose

# Proof metrics
PYTHONPATH=src .venv/bin/python -m hibs_predictor.main pred-log-report
```

Cron: **06:30 UTC** and **23:00 UTC** daily (`pred-log-sync --verbose`).

Requires: `HIBS_PREDICTION_LOG_ENABLED=1`, `API_SPORTS_FOOTBALL_KEY` in `.env`.

### Why 540 snapshots / 0 settled happens

- Cron not installed or stale log.
- Snapshots logged with non-API fixture ids (FotMob slugs). **Fixed:** logging uses `api_fixture_id`; sync resolves by team + date when id is wrong.
- Matches not FT yet (`HIBS_PRED_LOG_SYNC_MIN_HOURS` default 2.5h after kickoff).

## Brier / log loss

Already computed in `prediction_log.report_summary_dict()` and shown on Performance + `/tracker` when `HIBS_PUBLIC_TRACKER=1`.

## League profiles

See `config/league_profiles.yaml` and `league_profiles.profile_config_source()`. Engine reads YAML first, Python catalog fills gaps.

## Newsletter / B2B feed

```bash
PYTHONPATH=src python3 scripts/export_match_previews.py --min-dq 88 --out previews.txt
```

## Optional sale fetch scope (top-5 + Europe)

Not enabled by default (summer Nordics focus). For diligence:

```bash
HIBS_SALE_TOP5_ONLY=1   # when implemented in tournament_focus — restrict fetch set
```

## Twin-asset positioning

| Product | Buyer | Proof |
|---------|-------|-------|
| hibs-bet (football) | Media / newsletter | Audit DB + Brier + automated previews |
| hibs-racing | Syndicates | LightGBM + public ledger |
