# Player & lineup influence on predictions

Audit of what hibs-bet already fetches, what is safe to use, and a phased plan for deeper integration — **real API data only**, no invented player ratings.

## 1. Inventory — fields per fixture today

| Field | Source | When fetched | Used in engine? | Used in UI / insight? |
|-------|--------|--------------|-----------------|----------------------|
| `fixture_injuries[]` | API-Football `injuries?fixture=` | Every enrich (unless `HIBS_SKIP_API_INJURIES=1`) | Indirect via availability | Expand panel table; rationale bullets |
| `attack_availability_home/away` | Derived in `team_news_enrich.py` | After injuries | Optional λ dampen (`HIBS_USE_INJURY_LAMBDA_ADJUST=1`) | Rationale “Squad news” line |
| `team_news_meta` | Derived (`home_absences`, penalties) | After injuries | Debug / display | Rationale |
| `home_top_scorers[]` / `away_top_scorers[]` | API-Football `players/topscorers` (24h league cache) | When `HIBS_ENABLE_PLAYER_INSIGHT=1` | **No** (display only) | `structured_insight.player_insight` |
| `supplemental.fbref_home_squad` | FBref squad table (heavy scraper) | When heavy scrapers run & not blocked | **No** | Supplemental tags only |
| `fixture_lineups` / `lineup_confirmed` | API-Football `fixtures/lineups` (Phase 2) | Pre-KO window only (`HIBS_ENABLE_LINEUP_FETCH`) | **No** (display / confidence only) | Expand panel XI; rationale; assistant |
| Transfermarkt injuries | Deferred (probe-only) | Never in production | — | — |
| WhoScored / SofaScore players | Not wired | — | — | Template note “deferred” |

### API-Football endpoints in use (player-adjacent)

| Endpoint | Client method | Cache | Notes |
|----------|---------------|-------|-------|
| `injuries` | `fetch_injuries(fixture_id)` | 4h (default `_get_json`) | 1 call per enrich per fixture |
| `players/topscorers` | `fetch_top_scorers(league, season)` | **24h per league+season** | Shared across all fixtures in league window |
| `fixtures/statistics` | `fetch_fixture_statistics` | Post-match / live | Team xG only, not per-player |
| `fixtures/lineups` | `fetch_fixture_lineups` | Pre-KO window (per-fixture cache) | Starting XI display + scorer cross-check |
| `teams/statistics` | `fetch_team_statistics` | 12h | Team aggregates, not roster |

**Not called:** `players/squads`, `players?team=`, per-player xG.

### Injury row shape (API-Football)

Typical keys: `player.name`, `team.id`, `type` (Missing / Doubtful / Suspended / …), `reason`.

### Top scorer row shape

`player.name`, `statistics[0].team.id`, `statistics[0].goals.total`.

### Prediction audit log

`prediction_snapshots.enrich_summary_json` stores recent-n, table flags, odds — **not** full injury rows (counts added in this pass). Full prediction JSON retains engine output at capture time.

---

## 2. Gap analysis

| Need | Status | Blocker |
|------|--------|---------|
| **A. Injury / absence count → λ** | **Implemented** (opt-in) | API coverage varies by league; feed is headcount not “key player” |
| **B. Confirmed starting XI** | **Implemented** (Phase 2) | API coverage varies; no guess pre-KO |
| **C. Top scorer / minutes proxy** | **Partial** | Top scorers yes; minutes/assists not fetched |
| **D. Per-player xG** | Not available | API-Football lacks SCOTLAND/Europa per-player xG; Understat is team/league |
| **E. Display vs λ nudge** | **Implemented** | Motivation pattern: display always; λ behind env flags |

### What we cannot do without new scope

- “Star player out” weighting without lineup or explicit API absence for that player
- Formation-based tactical adjustments
- Transfermarkt market-value weighting (deferred / ToS)
- Cross-fixture injury λ without verifying the listed player is in the usual XI

### VPS / API budget

- Injuries: **O(fixtures)** — already paid; deep_enrich backfills thin injury block only
- Top scorers: **O(leagues in window)** — one cached call per league per 24h when `HIBS_ENABLE_PLAYER_INSIGHT=1`
- Lineups (Phase 2): **O(fixtures in pre-KO window)** — one cached call per fixture within `HIBS_LINEUP_FETCH_MAX_HOURS` (default 24h); skipped after kickoff

---

## 3. Recommendation — phased plan

### Phase 1 — **Done / active** (real data today)

1. **Injuries → attack availability** (`team_news_enrich.py`) — capped penalty, doubtful at half weight
2. **Optional λ dampen** — `HIBS_USE_INJURY_LAMBDA_ADJUST=1`, max cut `HIBS_INJURY_LAMBDA_MAX_CUT` (default 0.08), mirrors motivation nudge pattern
3. **Display** — injury table, rationale metrics, squad news bullet
4. **Top scorers (display-only)** — `HIBS_ENABLE_PLAYER_INSIGHT=1`; cross-check when a listed top scorer also appears on injury feed (name match, same team)
5. **Slim cache row** carries team-news + scorer fields so backfilled insights stay consistent

Env (see `.env.example`):

```bash
HIBS_SKIP_API_INJURIES=0
HIBS_USE_INJURY_LAMBDA_ADJUST=1
HIBS_INJURY_LAMBDA_MAX_CUT=0.08
HIBS_ENABLE_PLAYER_INSIGHT=1
HIBS_SKIP_API_PLAYER_STATS=0
```

VPS safe profile (`deploy/apply-vps-safe-production.sh`) enables player insight + injury λ.

### Phase 2 — **Done** (API lineups, display-first)

1. **`fetch_fixture_lineups(fixture_id)`** → API-Football `fixtures/lineups` when within pre-KO window (`HIBS_ENABLE_LINEUP_FETCH=1`, default on when API key loaded)
2. **`lineup_enrich.apply_lineup_fields`** — parse starting XI; compare to league top scorers + injury feed; flag scorers not in XI (only when both sides have ≥11 starters)
3. **Confidence penalty (display only)** — when `lineup_confirmed=false` and kickoff &lt; 2h, scale structured pick / model confidence by `HIBS_LINEUP_CONFIDENCE_FLOOR` (default 0.94); **does not alter λ**
4. Audit log stores `lineup_confirmed`, `lineup_xi_n`, `lineup_scorers_out` counts
5. No HTML scrape fallback (Transfermarkt deferred / ToS); no live polling

Env (see `.env.example`):

```bash
HIBS_ENABLE_LINEUP_FETCH=1
HIBS_SKIP_API_LINEUPS=0
HIBS_LINEUP_FETCH_MAX_HOURS=24
HIBS_LINEUP_CONFIDENCE_PENALTY=1
HIBS_LINEUP_CONFIDENCE_FLOOR=0.94
HIBS_LINEUP_CONFIDENCE_WINDOW_MIN=120
```

Cache: dedicated `lineups_fixture_{id}` key; TTL 15min when &lt;90min to KO, up to 4h when far out. Skips fetch once fixture is &gt;15min past kickoff.

### Phase 3 — **Heavy / deferred**

- FBref squad minutes blend (heavy scraper, VPS often blocked)
- Transfermarkt (ToS)
- Per-player xG where Understat/API expose it

---

## 4. Architecture options (ranked by feasibility)

| Rank | Option | Feasibility | Recommendation |
|------|--------|-------------|----------------|
| 1 | Injury count → availability → optional λ | **High** | **Shipped** — env-gated |
| 2 | Top scorers display + injury name cross-ref | **High** | **Shipped** — no engine impact |
| 3 | Confirmed lineup display only | **High** | **Shipped** — API + pre-KO cache |
| 4 | Lineup-based λ nudge | Low | Only when XI confirmed + scorer/minutes data |
| 5 | Per-player xG | Very low | Skip for Scottish / most cups |
| 6 | Display badges vs λ | **Done** | Follow `derive_motivation_context` / `_motivation_lambda_nudge` split |

---

## 5. Example — missing striker surfaces

**Data sources**

1. API-Football `players/topscorers` → home side includes `{name: "John Smith", goals: 14}`
2. API-Football `injuries?fixture=` → row `{player: {name: "John Smith"}, team: {id: …}, type: "Missing"}`

**UI (expand panel / structured insight)**

- Injuries table lists John Smith · Missing
- Top scorers block shows John Smith (14g) with badge **Listed absent (API injuries)**
- Rationale bullet: `Squad news: home 1 out (78% attack avail).`
- If top scorer absent: `Top scorer John Smith (14g) on API absence feed.`

**Engine (when `HIBS_USE_INJURY_LAMBDA_ADJUST=1`)**

- `attack_availability_home` ≈ 0.78 → `xg_home *= max(0.92, 0.78)` capped by `HIBS_INJURY_LAMBDA_MAX_CUT`
- No extra penalty for “striker” vs defender — feed does not expose position importance; headcount only

**Phase 2 lineup (when API returns both XIs)**

- Expand panel shows confirmed starting XI + formation
- If top scorer not in XI: rationale bullet + `lineup_meta.home_scorers_out_of_xi` with optional `on_injury_feed`
- If XI unconfirmed within 2h of KO: displayed confidence scaled by ~6% (`HIBS_LINEUP_CONFIDENCE_FLOOR`); λ unchanged

**Assistant**

- `assistant_facts` exposes `injuries_n`, `attack_availability_*`, `player_insight` when present — refuses to invent absences

---

## 6. Code map

| Module | Role |
|--------|------|
| `team_news_enrich.py` | Availability math + scorer/injury cross-ref |
| `lineup_enrich.py` | Phase 2 — API lineups parse, scorer/XI cross-check, confidence multiplier |
| `data_aggregator.py` | Fetch injuries, top scorers, apply enrichers |
| `betting_engine.py` | Optional injury λ (pre-calibration xG) |
| `match_insight.py` | Rationale, `player_insight`, motivation pattern |
| `api_clients.py` | `fetch_injuries`, `fetch_top_scorers`, `fetch_fixture_lineups` |
| `deep_enrich.py` | Backfill empty injury list in 75–90% DQ band |
| `prediction_log.py` | Audit summary counts |
| `templates/_fixture_expand_panel.html` | Injuries table, scorers, availability strip |
