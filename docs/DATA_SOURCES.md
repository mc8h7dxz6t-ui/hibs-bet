# hibs-bet data sources (evaluation)

Planning catalog: `src/hibs_predictor/scrapers/source_registry.py`  
Coverage scoring: `src/hibs_predictor/data_quality.py` (`full_scope` ≥ **85%**; UI default `HIBS_UI_FULL_DATA_MIN_PCT=85`)

## Wired today

| Source | Role | Env / notes |
|--------|------|-------------|
| API-Football (api-sports) | Fixtures, recent matches, team stats, standings, injuries, odds, fixture xG when present | `API_SPORTS_*`; `HIBS_DISABLE_API_SPORTS`, `HIBS_SKIP_API_*` |
| Football-Data.org | Fixture + standings fallback | `FOOTBALL_DATA_ORG_KEY`, `HIBS_PREFER_FOOTBALL_DATA_FIXTURES` |
| The Odds API | 1X2 + cross-book lines | `ODDS_API_KEY`; skip via `HIBS_SKIP_ODDS_API` |
| RapidAPI stats (api-football.com host) | Fixture-level xG | `STATS_API_KEY` + `HIBS_MAX_DATA=1` (default skips Rapid xG) |
| Understat | Match xG (12 league codes) | `HIBS_ENABLE_UNDERSTAT_LIGHT`, `HIBS_SCRAPE_XG` |
| FBref | Top-5 squad tables (heavy); SPFL schedule xG (Scottish) | `HIBS_ENABLE_HEAVY_SCRAPERS`, `HIBS_ENABLE_SCOTTISH_FBREF_XG` |
| Wikipedia | Standings when API thin | `HIBS_PREFER_SCRAPED_STANDINGS` |
| SofaScore | Rolling team xG averages → `sofascore_xg` when API reachable | `HIBS_ENABLE_SOFASCORE_XG` or `HIBS_MAX_DATA=1`; optional `pip install curl_cffi` |
| FotMob | Experimental fixture calendar only | `HIBS_ENABLE_FOTMOB_FIXTURES` |
| StatsBomb Open | Opt-in goals proxy | `HIBS_ENABLE_STATSBOMB_OPEN_MATCHES` |

## Backlog (metadata in registry)

Transfermarkt, xGStat, BeSoccer, FootyStats, SoccerStats, DataMB, UEFA direct, footballdata.io — **planned**, not production parsers.

## Recommended implementation order (impact / effort)

1. **Ops: `HIBS_MAX_DATA=1` + real keys** — enable Rapid stats xG, stop skipping heavy scrapers on “API strong” fixtures; largest xG uplift for top leagues with low code risk.
2. **SofaScore → `scraped_xg`** — **wired** (`sofascore_client.team_xg_profile` + `scraped_xg`); enable with `HIBS_MAX_DATA=1` or `HIBS_ENABLE_SOFASCORE_XG=1`. Install `curl_cffi` if endpoints return 403.
3. **Expand Understat `LEAGUE_SLUG`** — only where Understat actually publishes (verify slugs); low effort per league.
4. **FBref schedule xG pattern for more comps** — replicate `fbref_scottish_xg` for Championship / League One where Opta xG exists on schedule pages; medium effort, HTML fragility.
5. **Defer Selenium stacks** (FotMob lineups, WhoScored, full SofaScore UI) — high maintenance; prefer APIs (Sportmonks xG add-on, API-Football premium) for production xG.

## Library wrappers (soccerdata / worldfootballR)

**Not recommended as a near-term swap** for custom `understat_client` / `fbref_*`: same scrape surfaces and ToS constraints, extra dependency/version risk, and you already have league-code mapping, caching, and policy windows. Revisit if FBref/Understat HTML breaks repeatedly — then pilot **soccerdata** for Understat+FBref only behind feature flags.

## Realistic “95% full data”

Per-fixture score is weighted (xG block = 18 pts; `goals_proxy` earns ~4). **85%** on a fixture is achievable with APIs + scrapers on supported leagues. **~95% dashboard-wide** across all 26 `ALL_LEAGUE_CODES` (cups, internationals, Scottish lower tiers) is **not realistic** on free/scrape-only stacks without paid xG feeds or accepting thin cups as odds-only (`HIBS_ODDS_ONLY_LEAGUES`).
