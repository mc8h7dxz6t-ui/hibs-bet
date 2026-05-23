# hibs-bet data sources (evaluation)

Planning catalog: `src/hibs_predictor/scrapers/source_registry.py`  
Coverage scoring: `src/hibs_predictor/data_quality.py` (`full_scope` ≥ **85%**; UI default `HIBS_UI_FULL_DATA_MIN_PCT=85`)

## Live probe status (typical)

| Source | Status | Notes |
|--------|--------|-------|
| API-Football, Football-Data.org, Odds API | working | Requires keys in `.env` |
| Understat, FotMob, SoccerStats, StatsBomb open | working | Best-effort HTML/JSON scrapes |
| FBref | working* | Squad HTML + schedule xG; may 403 from datacenter IPs — set `HIBS_FBREF_BLOCKED=1` on VPS |
| SofaScore | blocked | HTTP 403 common; optional rolling xG only when reachable |
| Transfermarkt, xGStat, BeSoccer | deferred | Probe-only; not in enrichment pipeline |

\* Run `PYTHONPATH=src python3 -c "from hibs_predictor.health_probe import gather_health; ..."` or open **API status** in the app.

## Wired today

| Source | Role | Env / notes |
|--------|------|-------------|
| API-Football (api-sports) | Fixtures, recent matches, team stats, standings, injuries, odds, fixture xG when present | `API_SPORTS_*`; `HIBS_DISABLE_API_SPORTS`, `HIBS_SKIP_API_*` |
| Football-Data.org | Fixture + standings fallback | `FOOTBALL_DATA_ORG_KEY`, `HIBS_PREFER_FOOTBALL_DATA_FIXTURES` |
| The Odds API | 1X2 + cross-book lines | `ODDS_API_KEY`; skip via `HIBS_SKIP_ODDS_API` |
| RapidAPI stats (api-football.com host) | Fixture-level xG | `STATS_API_KEY` + `HIBS_MAX_DATA=1` (default skips Rapid xG) |
| Understat | Per-match xG for top leagues via `/getLeagueData` | `HIBS_ENABLE_UNDERSTAT_LIGHT`, `HIBS_SCRAPE_XG` |
| FBref | Squad tables (heavy); schedule xG for Scottish + EFL + top/mid-tier EU + Norway/Finland | `HIBS_ENABLE_FBREF_SCHEDULE_XG` (default on); `HIBS_FBREF_BLOCKED=1` on blocked hosts |
| SoccerStats | Standings when API thin | `HIBS_PREFER_SCRAPED_STANDINGS=1`; Norway, Finland, Scotland L1-L2 |
| FotMob | Fixture calendar fallback; league-table xG (UEFA cups default-on) | `HIBS_ENABLE_FOTMOB_FIXTURES=1`; `HIBS_ENABLE_FOTMOB_XG` / cups / `HIBS_MAX_DATA=1` |
| StatsBomb Open | Goals proxy → `statsbomb_goals_proxy_xg` | `HIBS_ENABLE_STATSBOMB_LIGHT` or cup default-on; `HIBS_MAX_DATA=1` |
| SofaScore | Rolling team xG (optional) | Often **403** — registry `blocked`; skip unless reachable |

## Deferred / planned

| Source | Status | Notes |
|--------|--------|-------|
| Transfermarkt | deferred | Robots probe only; injuries via API-Football |
| xGStat | deferred | No public JSON API found |
| BeSoccer | deferred | No documented JSON feed |
| FootyStats, DataMB, UEFA direct, footballdata.io | planned | No stable public API confirmed |
| soccerdata (pip) | planned | Optional fallback if HTML parsers break |

## Env: enrichment breadth

| Variable | Purpose |
|----------|---------|
| `HIBS_MAX_DATA=1` | Prefer maximum safe inputs (Rapid xG, heavy scrapers, StatsBomb) |
| `HIBS_MIN_ENRICH_LEAGUES` | Comma list to **prioritize** enrichment (e.g. `SCOTLAND,EPL,UCL`). Empty = all `ALL_LEAGUE_CODES` |
| `HIBS_ENABLE_STATSBOMB_LIGHT=1` | Goals proxy for leagues in open-data + UEFA cups |
| `FOTMOB_TIMEZONE` | FotMob daily matches timezone (default `Europe/London`) |

## Tournament focus (World Cup / internationals)

When active (env or auto window **2026-05-15 → 2026-07-31**), fixture fetch is limited to `WORLD_CUP`, `NATIONS_LEAGUE`, and `EUROS` — reducing domestic league API load on VPS. Dashboard defaults to **International** region; users can switch to All/UK/European.

| Variable | Purpose |
|----------|---------|
| `HIBS_TOURNAMENT_FOCUS=worldcup` | Force focus on (`euros`, `international`, or `1` also work) |
| `HIBS_TOURNAMENT_FOCUS=0` | Disable even during auto window |
| `HIBS_FOCUS_INTERNATIONAL=1` | Shorthand for international focus |
| `HIBS_TOURNAMENT_FOCUS_START` / `_END` | Override auto date window (ISO dates) |

FotMob xG: `WORLD_CUP` (77), `EUROS` (50), `NATIONS_LEAGUE` (9806–9809). API-Football / Football-Data.org / Odds API mappings already include the three international codes.

## Leagues still typically thin (no free xG table)

Cups without group standings (`FA_CUP`, `SCOTTISH_CUP`), `UECL` (limited StatsBomb open data), `NATIONS_LEAGUE` (no open-data season), lower tiers when APIs omit team IDs. Use `HIBS_ODDS_ONLY_LEAGUES` or accept odds-only previews for those codes.

## Measure coverage

```bash
HIBS_FETCH_DAYS=7 .pytest-venv/bin/python scripts/measure_dq_7d.py
```

Reports count of fixtures with `data_quality.score_pct` ≥ 78 and ≥ 85 in the fetch window.

## Realistic “95% full data”

**85%** per fixture is achievable with APIs + scrapers on supported leagues. **~95% dashboard-wide** across all 26 `ALL_LEAGUE_CODES` is not realistic on free/scrape-only stacks without paid xG feeds.
