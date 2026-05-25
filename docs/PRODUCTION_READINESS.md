# Production readiness — hibs-bet

**Audit date:** 2026-05-25  
**Repo:** `/Users/philipmacleod/Applications`  
**Production VPS:** `77.68.89.73` (`/opt/hibs-bet`, `hibs-bet.co.uk`)

Legend: **GREEN** = OK for next few weeks · **AMBER** = works but needs attention · **RED** = broken or blocks reliability

---

## Summary table

| Area | Status | Notes |
|------|--------|-------|
| Unit tests (`pytest tests/`) | **GREEN** | 224 passed (0 failed) after enriched-cache test fixture fix |
| VPS service (`hibs-bet`) | **GREEN** | `systemctl is-active` → active |
| VPS login | **GREEN** | `:8000/login` 200; nginx/HTTPS login 200 |
| VPS env baseline | **GREEN** | Auth, pred log, CLV, FotMob xG, tournament focus date-auto (unset), API limit 400, squad depth skipped |
| VPS cron (`pred-log-sync`) | **GREEN** | `www-data` crontab: daily 06:30 UTC + Sun calibration-fit |
| Prediction audit DB | **AMBER** | `prediction_audit.sqlite` exists; **0** snapshots — load dashboard while logged in to seed |
| `/api/health` unauthenticated | **AMBER** | Returns `login_required` (auth on); use session or `HIBS_AUTH_PUBLIC_HEALTH=1` if needed |
| International / WC window | **GREEN** | Auto 2026-06-01 → 2026-07-18 (no env switch); `HIBS_TOURNAMENT_FOCUS=0` opt-out only; `?domestic=1` escape |
| Season codes (May 2026) | **GREEN** | Jul-based `2025` + Nordic calendar-year `2026` candidates in `season.py` |
| Fixture cache version | **GREEN** | `v25` in `web.py`; clear after deploy if enrich fields stale |
| Partial enrich cache bust | **GREEN** | Thin rows (missing recent/stats) bypass stale enriched cache |
| xG chain | **GREEN** | API → Understat light → FotMob → recent API xG → season team; FBref blocked on VPS |
| Rate limiter / 429 guards | **GREEN** | Hourly cap 400, enrich semaphore, squad depth off, partial bust |
| Feature: dashboard `/` | **GREEN** | Deployed |
| Feature: insights + monitor | **GREEN** | Kickoff + scored day slices; acca highlight on main |
| Feature: accas `/acca` | **GREEN** | API + builder route present |
| Feature: recent results | **GREEN** | Events fetch on (max 12/refresh) |
| Feature: lineups / injury λ | **GREEN** | Enabled; lineup window 6h |
| Feature: auth | **GREEN** | `HIBS_AUTH_ENABLED=1`; secret key set on VPS (name only verified) |
| Launch overlay / Streamlit | **AMBER** | `launch/` exists locally; not part of VPS gunicorn deploy (by design) |
| Docs / ops runbook | **GREEN** | `RELIABILITY_BASELINE.md` updated with WC switch date + cron note |

---

## 1. Tests

```bash
cd /Users/philipmacleod/Applications
.pytest-venv/bin/pytest tests/ -q
```

| Result | Count |
|--------|-------|
| Passed | **224** |
| Failed | **0** |

**Fix applied:** `tests/test_betting_strategy.py` — enriched-cache tests now include minimal `home_stats` / `away_stats` to match `_enriched_needs_recent_refetch` (stats + recent required before cache is “fresh”).

Focused suites also green: `test_tournament_focus`, `test_prediction_log_monitor`, `test_xg_priority_chain`.

---

## 2. International / World Cup readiness

| Check | Status |
|-------|--------|
| `tournament_focus.py` auto window 1 Jun – 18 Jul 2026 | **GREEN** |
| `INTL_FRIENDLIES` in focus when WC mode | **GREEN** |
| `HIBS_TOURNAMENT_FOCUS` unset on VPS (date-driven auto) | **GREEN** |
| Domestic escape: `?domestic=1` / region All | **GREEN** |
| FotMob ids documented for WC / Euros / Nations | **GREEN** |
| `docs/RELIABILITY_BASELINE.md` auto-window note | **GREEN** |

**No user action on 1 Jun 2026** — international focus turns on automatically when UTC date enters the window (first dashboard load). Set `HIBS_TOURNAMENT_FOCUS=0` only to force domestic during the window.

---

## 3. Data pipeline

| Component | Status | Detail |
|-----------|--------|--------|
| `rate_limiter.py` | **GREEN** | `HIBS_API_SPORTS_HOURLY_LIMIT=400` on VPS |
| Partial cache bust (`web.py`) | **GREEN** | Busts when enriched row thin after 429 |
| `season.py` Nordic / cups | **GREEN** | `NORWAY_ELITESERIEN`, `FINLAND_VEIKKAUSLIIGA` calendar-year; UEFA cup season note in `web.py` |
| xG: `scraped_xg`, `fotmob`, priority chain | **GREEN** | Tests pass; VPS `HIBS_ENABLE_FOTMOB_XG=1`, `HIBS_FBREF_BLOCKED=1` |
| Prediction log + monitor | **AMBER** | Enabled; DB empty until dashboard captures snapshots |
| Monitor yesterday/today | **GREEN** | Kickoff + scored slices (`prediction_log.py`) |

---

## 4. Foreseeable issues (next few weeks)

| Risk | Status | Mitigation |
|------|--------|------------|
| May 2026 season id (Jul leagues still 2025) | **GREEN** | `api_football_season_year()`; override `HIBS_CURRENT_SEASON` if API lags |
| API 429 bursts | **GREEN** | Limit 400/h, workers 2, enrich sem, skip squad depth, partial bust |
| Empty audit DB | **AMBER** | Log in and load `/` once per match day before kickoff |
| Auth blocks health curl | **AMBER** | Expected with `HIBS_AUTH_ENABLED=1` |
| VPS env duplicate keys | **GREEN** | `apply-vps-safe-production.sh` dedupes `HIBS_*` |
| Stale fixture cache post-deploy | **GREEN** | Cache **v25**; clear via UI or `rm .cache/all_fixtures*` |
| `deploy_to_vps.sh` default host `.75` | **AMBER** | Production is **`.73`** — use `DEPLOY_HOST=77.68.89.73` |

---

## 5. VPS checks (77.68.89.73)

| Check | Result |
|-------|--------|
| `systemctl is-active hibs-bet` | **active** |
| `curl http://127.0.0.1:8000/login` | **200** |
| `curl https://127.0.0.1/login` (Host: hibs-bet.co.uk) | **200** |
| `HIBS_*` keys in `.env` (names only) | Present: auth, pred log, CLV, tournament focus, FotMob, lineup, injury, API limit, etc. |
| `www-data` crontab | **pred-log-sync** 06:30 UTC daily; **calibration-fit** Sun 07:00 UTC |
| `prediction_audit.sqlite` row count | **0** (schema exists) |
| `/api/health` without session | `{"error":"login_required"}` |

---

## 6. Feature matrix

| Feature | Route / surface | Deploy status |
|---------|-----------------|---------------|
| Dashboard | `/` | **GREEN** |
| Insights | `/insights`, `/api/insights` | **GREEN** |
| Acca builder | `/acca`, `/api/acca/recommendations` | **GREEN** |
| Model monitor (W/L, highlights) | Insights + `/api/monitor/summary` | **GREEN** |
| Recent results | Dashboard section | **GREEN** |
| Lineups | Enrich near KO | **GREEN** |
| Auth | `/login`, `HIBS_AUTH_ENABLED` | **GREEN** |
| API status | `/status` | **GREEN** |
| Launch overlay | `launch/` Streamlit | **AMBER** local only |
| Assistant widget | `/api/assistant/*` | **GREEN** |

No features removed for speed; `HIBS_SKIP_API_SQUAD_DEPTH=1` is quota protection only.

---

## Fixes applied (this audit)

1. **Tests:** `test_betting_strategy.py` — stats fixtures for enriched-cache helpers.  
2. **Docs:** `RELIABILITY_BASELINE.md` — pre-WC / switch-date paragraph.  
3. **Deploy:** `apply-vps-safe-production.sh` — cron install + login curl hints in completion message.  
4. **This file:** `docs/PRODUCTION_READINESS.md`.

---

## User actions — next few weeks

1. **Seed audit DB:** Log in to https://hibs-bet.co.uk/ and let the dashboard finish one full load on days with fixtures (creates `prediction_snapshots`).  
2. **After matches:** Cron runs `pred-log-sync` at 06:30 UTC; confirm `/var/log/hibs-bet/pred-log-sync.log` if monitor stays empty.  
3. **World Cup window:** No env change on 1 Jun — auto international focus when unset. Optional cache clear if DQ looks stale after the switch.  
4. **After code deploy:** If xG/DQ columns look wrong, clear fixture cache once (Settings or `rm .cache/all_fixtures*`).  
5. **Deploy from Mac:** `DEPLOY_HOST=77.68.89.73 ./scripts/deploy_to_vps.sh` (script default `.75` is not production).

---

## Re-run audit

```bash
.pytest-venv/bin/pytest tests/ -q
ssh root@77.68.89.73 'systemctl is-active hibs-bet; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/login; crontab -u www-data -l | grep pred-log'
```

See also: [RELIABILITY_BASELINE.md](./RELIABILITY_BASELINE.md), [DATA_SOURCES.md](./DATA_SOURCES.md), [deploy/README.md](../deploy/README.md).
