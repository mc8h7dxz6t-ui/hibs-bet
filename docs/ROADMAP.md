# hibs-bet roadmap (backlog)

Items completed in the latest backlog pass are listed under **Done**; remaining work stays honest below.

## Done (2026-05 backlog pass)

- **Player / lineup Phase 1** — injuries → `attack_availability_*`, optional λ dampen (`HIBS_USE_INJURY_LAMBDA_ADJUST`), league top scorers display (`HIBS_ENABLE_PLAYER_INSIGHT`), scorer/injury name cross-ref, Phase 2 `lineup_enrich` hooks. See `docs/PLAYER_LINEUP_INTEGRATION.md`.
- **Prediction audit log + post-match xG join** — `pred-log-sync` writes `result_xg_home` / `result_xg_away` from API-Football `fixtures/statistics` when Expected Goals exist; schema migration for existing SQLite DBs.
- **xG priority chain on `/status`** — documented step order + per-league notes (UECL, Primeira, Nordics); reflects `HIBS_FBREF_BLOCKED=1` VPS profile.
- **Motivation λ-nudge in engine** — same flags as match insight; applied to calibrated Poisson λ (and raw λ for ensemble side markets).
- **Poisson top-3 scorelines** — `poisson_top_scores` on prediction payload + expand panel.
- **League table UX** — `[H]` / `[A]` markers in compact dropdown; collapsible highlighted full table in expand panel (dropdown retained).
- **VPS deploy** — `HIBS_PREDICTION_LOG_ENABLED=1` in `apply-vps-safe-production.sh`.
- **API squad depth (Transfermarkt alternative)** — API-Football `players/squads` → `home_squad_depth` / `away_squad_depth`, absence % in `team_news_meta`, supplemental `api_squad_depth` mirror, DQ high-value tag. Default on; VPS safe profile sets `HIBS_SKIP_API_SQUAD_DEPTH=1` (extra API calls per fixture).
- **Stat acca recommender** — `acca_recommender.py` on `/insights` + `GET /api/acca/recommendations`; 2/3-fold and acca-of-the-day from enriched packets only (`HIBS_ACCA_RECOMMENDER`, `HIBS_ACCA_MAX_LEGS`).

## Modeling
- **Confirmed lineups (Phase 2)** — **Done.** API-Football `fixtures/lineups` pre-KO only; display + optional confidence penalty when XI unknown near kickoff (see `docs/PLAYER_LINEUP_INTEGRATION.md`).
- Historic xG backfill from Understat/FotMob league tables for cups without API xG (needs live cup window to validate).

## Coverage
- **World Cup focus window** — auto-limits fetch to internationals **2026-06-11 → 2026-07-18** only; domestic leagues normal outside that window. `HIBS_TOURNAMENT_FOCUS=0` disables on VPS; region chips load domestic via `?domestic=1`.
- Conference League final / Primera play-off at kickoff: FotMob primary ids documented; verify API round labels when finals are live (no fake fixtures in tests).

## UI
- Section sidebar by confidence tier (High / Medium / Low) instead of flat sort.
- Fixture list probability-first alignment (partial — structured insight exists; full row reorder deferred).

## Data persistence
- Periodic `pred-log-sync` cron on VPS (ops; code path wired).
- CLV beat-close reporting when `HIBS_CLV_LOG_ENABLED=1` accumulates enough rows.

## Assistant
- Incremental fixture-context answers (guardrails in `assistant_facts`; deeper wiring deferred).

## Deferred (external / ToS)
- Transfermarkt, xGStat, BeSoccer — probe-only; no production scrape.
