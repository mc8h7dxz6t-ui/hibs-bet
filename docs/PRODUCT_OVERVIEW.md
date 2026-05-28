# hibs-bet — product overview

What the application is, how data flows, and how reliability and data quality are handled. For engine detail see [BETTING_ENGINE.md](BETTING_ENGINE.md); for VPS flags see [RELIABILITY_BASELINE.md](RELIABILITY_BASELINE.md).

---

## Purpose

**hibs-bet** is a pre-match football betting intelligence application. It ingests fixtures from API-Football and Football-Data.org (plus selective scrapers), enriches each match with form, expected goals, odds, injuries, and lineups, scores **data quality (DQ)** transparently, runs a **Poisson + Dixon–Coles** prediction engine, and surfaces value bets and insights on a web dashboard deployed at **hibs-bet.co.uk** (`/opt/hibs-bet` on VPS).

Development lives in `~/Applications`; deploy is **rsync** from the Mac, not git pull on the server.

---

## User-facing surfaces

| Surface | Role |
|---------|------|
| **Dashboard** | Fixture cards by day/league; region/league/DQ filters; expandable rows (form, odds, xG, predictions, value) |
| **Players dock** | Fixed right panel (desktop): lineups, injuries, top scorers, form context; collapsible |
| **`/players`** | Full players page with league-grouped cards |
| **Insights** | Model and market reads from the current fixture set |
| **Acca Builder** | Multi-leg suggestions (legs treated as independent in combined probability) |
| **Tables** | Standings from feeds with fixture-row fallback |
| **Performance / Guide** | Track record and plain-English help |
| **Settings** | Theme, **Hibs Home / Away UI**, 5/7-day window, odds format — browser localStorage only |
| **API status** | Health probes for APIs and scrapers |
| **Assistant / betslip** | Structured insight packets and add-to-slip drawer |

**UI modes:** default forest green; **Hibs Away UI** adds a brighter glass style via `uiMode` in settings. Visual only — no change to server maths or DQ.

---

## Technical stack

- **Backend:** Python, Flask (`src/hibs_predictor/web.py`), gunicorn on port 8000
- **Frontend:** Jinja templates, vanilla JavaScript (filters, progressive load, dock state)
- **Deploy:** `scripts/deploy_to_vps.sh`, `deploy/apply-vps-safe-production.sh`, systemd `hibs-bet`
- **Git:** GitHub `origin` (canonical `main`); GitLab mirror for CI when synced
- **Cache:** Disk under `.cache/` — fixture bundles, enriched rows, API responses, rate-limit state

---

## Data pipeline

### Fetch

- Leagues in `config.py` (`LEAGUES`, `ALL_LEAGUE_CODES`): EPL, SPL, Nordics, UCL, cups, **INTL_FRIENDLIES**, World Cup path, etc.
- **Summer / pre–World Cup:** default fetch emphasises friendlies, Nordics, and cup finals; finished European league calendars are de-emphasised until season restart.
- **User window:** **5 or 7 days** (Settings, cookie, `?days=`). The dashboard **displays** only fixtures inside that window.
- **Friendlies internal horizon:** up to **14 days** for fetch and deep enrich (`HIBS_FRIENDLIES_FETCH_DAYS`) — used for max-data/DQ, not shown as “14 days” in hero copy.

### Enrich

Per fixture, roughly in order:

1. **API-Sports / Football-Data.org** — fixtures, form, team stats, standings, injuries, lineups, top scorers, odds
2. **Supplemental scrapers** — FotMob (league xG; friendlies national-team path), thin-data rescue, StatsBomb goals proxy, optional Understat light
3. **xG chain** — API fixture/season xG → scrapers → goals proxy (`fixture_statistics_xg.py`, budget caps)
4. **Calibrated λ** — rank→Elo proxy + home-advantage (`calibrated_lambdas.py`)
5. **Deep enrich** — second pass toward 90%+ where data allows; **friendlies max-data** runs across the friendlies window until World Cup focus (~11 Jun 2026)

**Max data on VPS:** `HIBS_MAX_DATA=1` prevents skipping first-pass heavy scrapers; `HIBS_DEEP_ENRICH_WINDOW_DAYS=5` for non-friendlies; `HIBS_FRIENDLIES_MAX_DATA=1` for international friendlies.

**Not on VPS production:** FBref HTML (`HIBS_FBREF_BLOCKED=1`); Transfermarkt / WhoScored / DataMB (ToS, blocking, or SPA fragility).

### Data quality

- **Earned floors** in `data_quality.py` — not artificial inflation
- Examples: domestic rich **88%+**; friendlies **85%+** without odds, **90%+** with odds and measured xG; UCL/showpiece paths up to **95%+** when premium blocks are present
- Weak fields listed honestly (e.g. Expected goals, Odds markets)
- `_ensure_fixture_data_quality` does **not downgrade** an existing high score on partial re-enrich
- Abstain on very thin coverage rather than fabricate probabilities

See [PLAYER_LINEUP_INTEGRATION.md](PLAYER_LINEUP_INTEGRATION.md) for player-field sources.

---

## Betting engine

| Layer | Detail |
|-------|--------|
| **1X2** | Poisson score grid + **Dixon–Coles ρ** on low-score cells (0-0, 1-1, 1-0, 0-1); `HIBS_DIXON_COLES_RHO` default −0.10 |
| **Side markets** | BTTS, O/U from same λ; joint score+BTTS |
| **Market blend** | De-vig implied odds (`HIBS_CALIB_MARKET_BLEND`); stronger when DQ &lt; 75% |
| **Value** | Edge vs book + optional sharp consensus; DQ, confidence, and cup/longshot gates |
| **Kelly** | Fractional Kelly per leg, capped per bet |
| **Portfolio scaler** | Same kickoff window: `stake / sqrt(N)`, cap `HIBS_PORTFOLIO_STAKE_CAP_PCT` (default 10%) |
| **Calibration** | League Brier shrink, `prediction_log`, optional `calibration_fit` cron |

Full architecture and backlog: [BETTING_ENGINE.md](BETTING_ENGINE.md).

---

## Reliability (structural guards)

These are permanent behaviours, not one-off fixes:

| Problem | Guard |
|---------|--------|
| **502 / worker exhaustion** | HTTP uses cache → stale → cold shell; single background refresh lock; DQ reboost only in background |
| **Refresh empty dashboard** | `?refresh=1` keeps stale disk bundle visible while warming |
| **Thin cache poisoning** | Do not persist empty or thin `all_fixtures` bundles |
| **API 429 / daily limit** | Local rate guard + stale reuse; daily-quota tripwire |
| **Deploy cache wipe** | `vps_restart_test.sh` default `CLEAR_CACHE=0` |
| **Cold-start 500s** | Progressive load on dashboard, players, insights, tables |
| **Stale UI filters** | Reset region/league/DQ chips if all cards hidden |

Details: [reliability_hardening_notes.md](reliability_hardening_notes.md).

---

## Players experience

- **Primary:** API-Sports injuries, lineups, top scorers, squad depth (when not skipped on VPS)
- **Right dock** + **`/players`** page; main-column duplicate removed
- **League ordering:** EPL → SPL → Europe → lower tiers (`players_panel_league_order`)
- Display only from loaded enrichment — no synthetic player stats

Supplemental scrapers (FBref player pages, Transfermarkt, SofaScore lineups) are assessed as **backlog** — API-first on production VPS.

---

## Production environment (summary)

Applied by `deploy/apply-vps-safe-production.sh`:

| Flag | Typical value | Notes |
|------|---------------|--------|
| `HIBS_DEV_FULL_DQ` | `0` | Never full dev burst on VPS |
| `HIBS_PROGRESSIVE_LOAD` | `1` | Fast HTML, background warm |
| `HIBS_API_SPORTS_HOURLY_LIMIT` | `400` | Client-side hourly cap |
| `HIBS_MAX_DATA` | `1` | Full safe scrape profile |
| `HIBS_FRIENDLIES_MAX_DATA` | `1` | Window-wide deep enrich for friendlies |
| `HIBS_FRIENDLIES_FETCH_DAYS` | `14` | Internal fetch horizon (display still 5/7) |
| `HIBS_DEEP_ENRICH_WINDOW_DAYS` | `5` | Deep pass for non-friendlies |
| `HIBS_ENABLE_PLAYER_INSIGHT` | `1` | Top scorers in insight |
| `HIBS_FBREF_BLOCKED` | `1` | FBref off on datacenter IP |
| `HIBS_SKIP_API_SQUAD_DEPTH` | `1` | Saves quota; injuries + lineups kept |

Full table: [RELIABILITY_BASELINE.md](RELIABILITY_BASELINE.md).

---

## Deploy workflow

```bash
cd ~/Applications
./scripts/deploy_to_vps.sh          # rsync code
./scripts/vps_restart_test.sh       # restart; cache preserved by default
# Intentional cache bust only:
CLEAR_CACHE=1 ./scripts/vps_restart_test.sh
```

GitHub push: `./scripts/push_all_remotes.sh` (GitLab may need protected-branch admin for force-with-lease after history rewrites).

---

## No-compromise principles

| Keep | How |
|------|-----|
| **All sources** | API + scrapers; supplemental paths add depth, never replace API |
| **DQ semantics** | Floors in `data_quality.py`; regression tests pin constants |
| **Features** | Dashboard, insights, acca, players, engine, value, assistant |
| **Honesty** | Low DQ when API is truly thin; 90%+ only when odds, xG, and form are earned |

**VPS tradeoffs:** hourly API cap, FBref off, background deep enrich, optional squad depth skip — stability and earned scores over synchronous full scrape on every request.

---

## Sensible next layers

- League-specific **Dixon–Coles ρ** from audit DB
- **API gap logging** when topscorers/injuries empty per league
- **SofaScore lineups** supplemental when probe succeeds
- GitLab **main** synced with GitHub
- **Prediction log + calibration cron** enabled on VPS for long-run CLV tuning

Roadmap: [ROADMAP.md](ROADMAP.md).

---

## Elevator pitch

> hibs-bet ingests football fixtures from API-Football and Football-Data (plus selective scrapers), enriches each match with form, xG, odds, injuries, and lineups, scores transparent data quality, runs a Dixon–Coles Poisson engine with market blending and value detection, and presents everything on a progressive dashboard with a players dock and insights/acca tools — deployed on a VPS with caching, rate-limit guards, and background enrichment so the site stays responsive while data depth rebuilds after deploys.
