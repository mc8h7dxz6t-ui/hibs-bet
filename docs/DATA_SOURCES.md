# hibs-bet data sources (evaluation)

Planning catalog: `src/hibs_predictor/scrapers/source_registry.py`  
Coverage scoring: `src/hibs_predictor/data_quality.py` (`full_scope` ≥ **85%**; UI default `HIBS_UI_FULL_DATA_MIN_PCT=85`)

## Live probe status (typical)

| Source | Status | Notes |
|--------|--------|-------|
| API-Football, Football-Data.org, Odds API | working | Requires keys in `.env` |
| Understat, FotMob, SoccerStats, StatsBomb open | working | Best-effort HTML/JSON scrapes |
| FBref | working* | Squad HTML + schedule xG; may 403 from datacenter IPs — set `HIBS_FBREF_BLOCKED=1` on VPS; `curl_cffi` rarely fixes datacenter blocks |
| SofaScore | blocked | HTTP 403 common; optional rolling xG only when reachable |
| Transfermarkt, xGStat, BeSoccer | deferred | Probe-only; production uses API-Football injuries/squads + Understat/FotMob/SoccerStats |

\* Run `PYTHONPATH=src python3 -c "from hibs_predictor.health_probe import gather_health; ..."` or open **API status** in the app.

## Wired today

| Source | Role | Env / notes |
|--------|------|-------------|
| API-Football (api-sports) | Fixtures, recent matches, team stats, standings, injuries, squad depth, odds, fixture xG when present | `API_SPORTS_*`; `HIBS_DISABLE_API_SPORTS`, `HIBS_SKIP_API_*`, `HIBS_ENABLE_API_SQUAD_DEPTH=1` |
| Football-Data.org | Fixture + standings fallback | `FOOTBALL_DATA_ORG_KEY`, `HIBS_PREFER_FOOTBALL_DATA_FIXTURES` |
| The Odds API | 1X2 + cross-book lines | `ODDS_API_KEY`; skip via `HIBS_SKIP_ODDS_API` |
| RapidAPI stats (api-football.com host) | Fixture-level xG | `STATS_API_KEY` + `HIBS_MAX_DATA=1` (default skips Rapid xG) |
| Understat | Per-match xG for top leagues via `/getLeagueData` | `HIBS_ENABLE_UNDERSTAT_LIGHT`, `HIBS_SCRAPE_XG` |
| FBref | Squad tables (heavy); schedule xG for Scottish + EFL + top/mid-tier EU + Norway/Finland | `HIBS_ENABLE_FBREF_SCHEDULE_XG` (default on); `HIBS_FBREF_BLOCKED=1` on blocked hosts |
| SoccerStats | Standings when API thin | `HIBS_PREFER_SCRAPED_STANDINGS=1`; Norway, Finland, Scotland L1-L2 |
| FotMob | Fixture calendar fallback; league-table xG (UEFA + domestic cups default-on; all mapped leagues when `HIBS_MAX_DATA=1` or `HIBS_ENABLE_FOTMOB_XG=1`) | `HIBS_ENABLE_FOTMOB_FIXTURES=1`; cup ties fall back to parent league table (e.g. `FA_CUP`→`EPL`, `DFB_POKAL`→`BUNDESLIGA`) |
| StatsBomb Open | Goals proxy → `statsbomb_goals_proxy_xg` | `HIBS_ENABLE_STATSBOMB_LIGHT` or cup default-on; `HIBS_MAX_DATA=1` |
| SofaScore | Rolling team xG (optional) | Often **403** — registry `blocked`; skip unless reachable |

## Deferred / planned

| Source | Status | Notes |
|--------|--------|-------|
| Transfermarkt | deferred | Robots probe only; injuries + squad via API-Football (`HIBS_ENABLE_API_SQUAD_DEPTH`) |
| xGStat | deferred | No public JSON API; xG via Understat/FotMob/API chain |
| BeSoccer | deferred | No documented JSON feed; use SoccerStats/API/FotMob |
| FootyStats, DataMB, UEFA direct, footballdata.io | planned | No stable public API confirmed |
| soccerdata (pip) | planned | Optional fallback if HTML parsers break |

## Env: enrichment breadth

| Variable | Purpose |
|----------|---------|
| `HIBS_MAX_DATA=1` | Prefer maximum safe inputs (Rapid xG, heavy scrapers, StatsBomb, FotMob domestic xG) |
| `HIBS_ENABLE_FOTMOB_XG=1` | Force FotMob league-table xG for all mapped leagues (VPS safe profile sets this with `MAX_DATA`) |
| `HIBS_MEASURED_XG_LAMBDA_BOOST` | Optional 0–0.03 nudge to calibrated λ when xG tier is measured (default `0` = off) |
| `HIBS_MIN_ENRICH_LEAGUES` | Comma list to **prioritize** enrichment (e.g. `SCOTLAND,EPL,UCL`). Empty = all `ALL_LEAGUE_CODES` |
| `HIBS_ENABLE_STATSBOMB_LIGHT=1` | Goals proxy for leagues in open-data + UEFA cups |
| `HIBS_ENABLE_API_SQUAD_DEPTH=1` | API-Football `players/squads` roster (24h cache; default on). Skip with `HIBS_SKIP_API_SQUAD_DEPTH=1` |
| `FOTMOB_TIMEZONE` | FotMob daily matches timezone (default `Europe/London`) |

## Tournament focus (World Cup / internationals)

When active (env or auto window **2026-06-01 → 2026-07-18**), fixture fetch defaults to `WORLD_CUP`, `INTL_FRIENDLIES`, `NATIONS_LEAGUE`, and `EUROS` — reducing domestic league API load on VPS. Dashboard defaults to **International** region (chip shows all four); **All / UK / European** region chips trigger a full domestic fetch (`?domestic=1`).

| Variable | Purpose |
|----------|---------|
| `HIBS_TOURNAMENT_FOCUS=worldcup` | Force focus on (`euros`, `international`, or `1` also work) |
| `HIBS_TOURNAMENT_FOCUS=0` | Disable even during auto window — restores domestic leagues immediately after restart |
| `HIBS_FOCUS_INTERNATIONAL=1` | Shorthand for international focus |
| `HIBS_TOURNAMENT_INCLUDE_FRIENDLIES=1` | Add friendlies when focus is not `worldcup` (auto window includes them) |
| `HIBS_TOURNAMENT_FOCUS_START` / `_END` | Override auto date window (ISO dates) |

`INTL_FRIENDLIES`: API-Football league id **10**; no Football-Data.org code; no FotMob league-table id (use API fixture xG / form paths). FotMob xG: `WORLD_CUP` (77), `EUROS` (50), `NATIONS_LEAGUE` (9806–9809).

## Leagues still typically thin (no free xG table)

Cups without group standings (`FA_CUP`, `SCOTTISH_CUP`), `UECL` (limited StatsBomb open data), `NATIONS_LEAGUE` (no open-data season), lower tiers when APIs omit team IDs. Use `HIBS_ODDS_ONLY_LEAGUES` or accept odds-only previews for those codes.

## Measure coverage

```bash
HIBS_FETCH_DAYS=7 .pytest-venv/bin/python scripts/measure_dq_7d.py
```

Reports count of fixtures with `data_quality.score_pct` ≥ 78 and ≥ 85 in the fetch window.

## Realistic “95% full data”

**85%** per fixture is achievable with APIs + scrapers on supported leagues. **~95% dashboard-wide** across all 26 `ALL_LEAGUE_CODES` is not realistic on free/scrape-only stacks without paid xG feeds.
