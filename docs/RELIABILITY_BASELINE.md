# VPS reliability baseline (Scope A)

End-of-season profile for `/opt/hibs-bet` on the 2GB VPS. Applied by:

```bash
sudo bash /opt/hibs-bet/deploy/apply-vps-safe-production.sh
```

Prioritises **consistency over new features** — enables player/injury/lineup logic already in the repo, caps API use, and keeps domestic leagues through season end.

## Flags (what each does)

| Flag | Value | Purpose |
|------|-------|---------|
| `HIBS_USE_INJURY_LAMBDA_ADJUST` | `1` | Dampen Poisson λ when attack availability is low (injuries). |
| `HIBS_INJURY_LAMBDA_MAX_CUT` | `0.08` | Cap injury-driven λ reduction at ~8%. |
| `HIBS_ENABLE_PLAYER_INSIGHT` | `1` | Top-scorer / player context in structured match insight. |
| `HIBS_ENABLE_LINEUP_FETCH` | `1` | Fetch confirmed XIs from API-Football near kickoff. |
| `HIBS_LINEUP_FETCH_MAX_HOURS` | `6` | Only call lineups API within 6h of KO (saves quota). |
| `HIBS_SKIP_API_SQUAD_DEPTH` | `1` | **Off on VPS** — squad/roster API calls often trigger 429; injuries + lineups cover most signal. |
| `HIBS_TOURNAMENT_FOCUS` | `0` | Force domestic leagues; ignore World Cup auto-window until you re-enable. |
| `HIBS_PREDICTION_LOG_ENABLED` | `1` | SQLite audit trail of model picks. |
| `HIBS_CLV_LOG_ENABLED` | `1` | Store opening odds for closing-line value tracking. |
| `HIBS_FBREF_BLOCKED` | `1` | Skip FBref HTML (datacenter IPs usually 403). |
| `HIBS_API_SPORTS_HOURLY_LIMIT` | `400` | Client-side hourly cap (matches data-drop fix). |
| `HIBS_FIXTURE_FETCH_WORKERS` | `2` | Parallel league fetches (gentle on 2GB). |
| `HIBS_ENRICH_API_SEM` | `1` | One team-history API call at a time per worker. |
| `HIBS_SKIP_HEAVY_WHEN_API_STRONG` | `1` | Skip Understat/FBref when APIs already strong. |
| `HIBS_AUTH_ENABLED` | `1` | Require login on dashboard/APIs. |
| `HIBS_RESULTS_FETCH_EVENTS` | `1` | Goal scorers on Recent results via API-Football `fixtures/events` (default on). |
| `HIBS_RESULTS_MAX_EVENT_FETCHES` | `12` | Max new events API calls per results refresh (24h per-fixture cache). |

Also set by the script (not injury/lineup specific): `HIBS_FETCH_DAYS=7`, `HIBS_MAX_DATA=1`, `HIBS_DASHBOARD_LITE=0`, `HIBS_WARM_FIXTURE_CACHE=1`.

## Auth (manual — never in git)

After the script runs, add to `/opt/hibs-bet/.env`:

```bash
HIBS_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
HIBS_AUTH_PASSWORD=<strong password>
# optional: HIBS_AUTH_USERNAME=admin  HIBS_AUTH_PUBLIC_HEALTH=1
sudo systemctl restart hibs-bet
```

## Tweak after your break

1. **More lineup coverage** — raise `HIBS_LINEUP_FETCH_MAX_HOURS` to `12` or `24` if quota allows.
2. **Squad depth** — set `HIBS_SKIP_API_SQUAD_DEPTH=0` only if 429s stay low for a week.
3. **Lighter load** — set `HIBS_FETCH_DAYS=5` or `HIBS_DASHBOARD_LITE=1` if home page times out.
4. **World Cup window** — remove `HIBS_TOURNAMENT_FOCUS=0` or set `HIBS_TOURNAMENT_FOCUS=worldcup` from 2026-06-11.
5. **Injury sensitivity** — lower `HIBS_INJURY_LAMBDA_MAX_CUT` (e.g. `0.05`) for a gentler effect.
6. **Cup load** — cups skip full standings fetch automatically; set `HIBS_SKIP_API_STANDINGS=1` if quota is tight (form/last-10 still enrich).
7. **Recent results scorers** — on by default (`HIBS_RESULTS_FETCH_EVENTS=1`, max 12 calls/refresh, 24h per-fixture cache). Set `HIBS_RESULTS_FETCH_EVENTS=0` to disable. Scorelines always come from fixture `goals`; scorers only from real events data.
8. **Shared fixture cache** — dashboard and `/insights` reuse the same `all_fixtures_*` disk cache within TTL; avoid `?refresh=1` unless clearing stale data.

Re-run the apply script after changing baseline keys; it dedupes `HIBS_*` lines and preserves your API keys.

## If data quality (DQ) drops

Stale cache after deploy or env change is the usual cause.

```bash
# On VPS as root
sudo -u www-data rm -rf /opt/hibs-bet/.cache/all_fixtures* /opt/hibs-bet/.cache/league_*
sudo systemctl restart hibs-bet
```

Or use **Settings → Clear cache** in the UI (requires login). Wait one full dashboard load (~2–3 min) before judging DQ.

Check `/api/health` for API quota and enrichment errors.
