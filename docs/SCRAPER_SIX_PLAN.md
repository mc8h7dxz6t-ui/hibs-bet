# Six-scraper production plan (85%+ DQ)

Path to **full data** (`data_quality.score_pct` ≥ **85%**, `full_scope`) on configured leagues without VPS meltdown. Implemented in `src/hibs_predictor/scrapers/scraper_six.py`; supplemental annotates per-fixture status in `supplemental.scraper_six`.

## The six (wired)

| # | Source | Role | Unique signal | Env | API budget / refresh |
|---|--------|------|---------------|-----|----------------------|
| 1 | **API-Football** | Core API | Fixtures, team IDs, season stats, standings, injuries, 1X2 odds, fixture payload xG | Keys in `.env`; skip via `HIBS_DISABLE_API_SPORTS` | Primary quota; `HIBS_API_SPORTS_HOURLY_LIMIT` (400/h VPS); `HIBS_ENRICH_API_SEM` |
| 2 | **API statistics xG** | Measured xG backfill | `fixtures/statistics` Expected Goals when fixture xG empty | `HIBS_FETCH_FIXTURE_STATISTICS_XG=1` | **24 calls max** per dashboard refresh (`HIBS_FETCH_FIXTURE_STATISTICS_XG_MAX`); 12h cache |
| 3 | **FotMob xG** | League-table xG | UEFA cups default-on; domestic when `HIBS_MAX_DATA=1` or `HIBS_ENABLE_FOTMOB_XG=1` | `HIBS_ENABLE_FOTMOB_XG`, `FOTMOB_TIMEZONE` | **0** API-Sports calls (public JSON) |
| 4 | **Understat** | Shot-level xG | Match row or team rolling for mapped top leagues | `HIBS_ENABLE_UNDERSTAT_LIGHT=1`, `HIBS_SCRAPE_XG=1` | **0** API calls; low-rate AJAX; 6h supplemental cache |
| 5 | **SoccerStats** | Standings fallback | Table positions when API/FDO thin (Norway, Finland, Scotland L1–L2) | `HIBS_PREFER_SCRAPED_STANDINGS=1` | **0** API calls; one HTML table/league/cache |
| 6 | **StatsBomb open** | Cups goals proxy | UCL/Europa/World Cup/Euros team GF/GA proxy → `statsbomb_goals_proxy_xg` | Cups default-on; `HIBS_ENABLE_STATSBOMB_LIGHT=1` or `HIBS_MAX_DATA=1` | **0** API calls (GitHub raw JSON) |

**Slot six** uses API statistics xG instead of SofaScore (often HTTP 403). SofaScore remains optional overflow — see below.

### DQ contribution (per fixture, approximate)

| Block | Max pts | Primary six sources |
|-------|---------|---------------------|
| Team IDs + fixture id | 10 | API-Football |
| Recent form | 16 | API-Football recent matches |
| Season stats | 18 | API-Football team stats |
| League table | 10 | API-Football / FDO; **SoccerStats** fills gaps (+5 each side) |
| xG | 18 | **API statistics** / fixture xG (18) > Understat (14–16) > FotMob (13–14) > StatsBomb proxy (**11 only**) |
| 1X2 odds | 19 | Odds API + API-Football |
| Side markets | 4 | Odds API |
| Supplemental context | 3 | Any high-value scrape hit (`scraper_six.hits` ≥ 3 → full 3 pts) |
| Injuries | 3 | API-Football |

**85% threshold** needs strong xG (measured, not proxy-only), book 1X2, and most core blocks. Proxy-only xG (`goals_proxy`, `statsbomb_goals_proxy_xg`) caps the xG block at 6–11 pts — the six-plan prioritises measured tiers first.

### VPS safe profile

`deploy/apply-vps-safe-production.sh` sets:

- `HIBS_MAX_DATA=1`, `HIBS_ENABLE_FOTMOB_XG=1`
- `HIBS_FETCH_FIXTURE_STATISTICS_XG=1`, `HIBS_FETCH_FIXTURE_STATISTICS_XG_MAX=24`
- `HIBS_FBREF_BLOCKED=1` (FBref **not** in the six — too heavy / 403)
- `HIBS_SKIP_HEAVY_WHEN_API_STRONG=1`, `HIBS_ALWAYS_DEEP_SCRAPE=0` (skip FBref/full Understat when APIs already strong)

## Optional overflow (not in the six)

| Source | Status | Notes |
|--------|--------|-------|
| **SofaScore** | blocked | `HIBS_ENABLE_SOFASCORE_XG=1` when reachable; DQ xG tier 13.5 |
| **FBref** | wired, VPS off | Schedule/squad xG when not blocked; heavy path |
| **Football-Data.org** | wired | Fixture/standings fallback (API slot, not scrape) |
| **RapidAPI stats xG** | optional | `HIBS_MAX_DATA=1` + `STATS_API_KEY` |

## Deferred / planned (not wired)

From `source_registry.py` — **no stable public API or ToS block**:

| Source | Reason |
|--------|--------|
| FootyStats | Login walls; no confirmed JSON API |
| DataMB | Chart-heavy SPA |
| UEFA direct | Coverage via API-Football / FDO |
| footballdata.io | Endpoint not verified |
| soccerdata (pip) | Fallback if custom DNS breaks |
| worldfootballR | R toolchain |
| Transfermarkt, xGStat, BeSoccer | Probe-only; API-Football covers injuries/squad/xG |

## Measure coverage

```bash
HIBS_FETCH_DAYS=7 .pytest-venv/bin/python scripts/measure_dq_7d.py
```

Compare baseline vs `HIBS_MAX_DATA=1` + `HIBS_ENABLE_STATSBOMB_LIGHT=1`.

## Implementation hooks

- `collect_supplemental()` → `annotate_scraper_six()` → `supplemental.scraper_six`
- `data_quality._supplemental_pts()` credits `api_statistics_xg` and ≥3 six-plan hits
- `/api/health` → `scraper_six_plan` summary
- Catalog: `docs/DATA_SOURCES.md`

## Estimated DQ lift (configured leagues, 7-day window)

With VPS safe profile on EPL/Scotland/UCL sample:

- **Baseline** (API only, no MAX_DATA): ~60–75% avg; many fixtures on `goals_proxy`
- **Six-plan enabled**: +8–15 pts avg from measured xG + standings + supplemental context
- **85%+ fixture share**: target **70–85%** of fixtures in mapped leagues with keys; cups/internationals lower without FotMob/StatsBomb hits

Realistic ceiling remains **~85% per fixture** on supported leagues; **~95% dashboard-wide** across all 26 `ALL_LEAGUE_CODES` is not achievable on free stacks alone.
