"""Flask web dashboard for hibs-bet."""

import os
import sys
from datetime import datetime, timedelta, timezone, date
from typing import Any, Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

from dotenv import load_dotenv

load_dotenv(os.path.join(BASE_DIR, ".env"))
load_dotenv(os.path.join(BASE_DIR, ".env.local"))

try:
    from hibs_predictor.m5_optimization import setup_optimizations

    _optimization_config = setup_optimizations()
    if _optimization_config["platform"]["is_apple_silicon"]:
        print("Apple Silicon (M-series) optimizations enabled")
except Exception as exc:
    print(f"M5 optimizations skipped: {exc}")

from flask import Flask, render_template, jsonify, request, abort, g, has_request_context
from hibs_predictor.config import (
    LEAGUES,
    ALL_LEAGUE_CODES,
    LEAGUE_REGIONS,
    DASHBOARD_LEAGUE_ORDER,
    DASHBOARD_FILTER_REGIONS,
    league_dashboard_region,
)
from hibs_predictor.cache import Cache
from hibs_predictor.data_aggregator import DataAggregator
from hibs_predictor.betting_engine import (
    BettingEngine,
    OddsAnalyzer,
    TeamStrengthCalculator,
    prediction_unavailable_payload,
)
from hibs_predictor.health_probe import gather_health
from hibs_predictor.display_tz import display_tz_label, fixture_window_start_utc, fixture_window_end_utc
from hibs_predictor.fixture_utils import display_competition_title
from hibs_predictor.media_config import (
    SKY_SPORTS_NEWS_WATCH_URL,
    SKY_SPORTS_NEWS_YOUTUBE_EMBED_URL,
)

TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
app.config["JSON_SORT_KEYS"] = False


@app.after_request
def _persist_fetch_days_cookie(response):
    return _set_fetch_days_cookie_if_requested(response)


aggregator = DataAggregator()
betting_engine = BettingEngine(aggregator.get_all_clients())

_health_cache: Dict[str, Any] = {"t": 0.0, "payload": None}
_HEALTH_TTL_SEC = 90.0
_cache_prune_last: float = 0.0
_CACHE_PRUNE_INTERVAL_SEC = 300.0


def _api_football_season_year(now: datetime) -> int:
    """API-Football season id is the year the competition season starts (e.g. 2025 for 2025–26)."""
    return now.year if now.month >= 7 else now.year - 1


_FDO_CALENDAR_COMPS = frozenset({"WC", "EC", "UNL", "CL", "EL", "UECL"})
# UEFA club cups: API-Football season id is Jul-based; FDO often 403/429 on finals week.
_API_FIRST_FIXTURE_LEAGUES = frozenset({"UCL", "EUROPA_LEAGUE", "UECL"})
_FIXTURE_CACHE_VERSION = "v22"
_EMPTY_FIXTURE_CACHE_TTL_HOURS = 0.2  # short negative cache — avoid hour-long empty poison


def _years_touched_by_date_range(date_from_s: str, date_to_s: str) -> List[int]:
    d0 = date.fromisoformat(date_from_s[:10])
    d1 = date.fromisoformat(date_to_s[:10])
    if d1 < d0:
        d0, d1 = d1, d0
    return list(range(d0.year, d1.year + 1))


def _fixture_fetch_season_candidates(
    football_data_comp_id: Optional[str], date_from_s: str, date_to_s: str, now: datetime
) -> List[int]:
    """Season years to try for fixtures. Domestic leagues use Jul-based season id; WC/EC/UNL also use calendar years in the fetch window."""
    primary = _api_football_season_year(now)
    if not football_data_comp_id or football_data_comp_id not in _FDO_CALENDAR_COMPS:
        out = [primary, primary - 1]
        # Calendar-year leagues (Nordics, etc.): API season id is the calendar year (e.g. 2026 in May 2026).
        if now.month < 7 and now.year not in out:
            out.insert(0, now.year)
        return out
    window_years = _years_touched_by_date_range(date_from_s, date_to_s)
    merged = set(window_years) | {primary, primary - 1}
    out: List[int] = []
    seen: set[int] = set()
    # Jul-based API season (e.g. 2025 for 2025–26) before calendar years in the window.
    for y in (primary, primary - 1):
        if y in merged and y not in seen:
            out.append(y)
            seen.add(y)
    for y in sorted(window_years, reverse=True):
        if y in merged and y not in seen:
            out.append(y)
            seen.add(y)
    for y in sorted(merged - seen, reverse=True):
        out.append(y)
    return out


def _env_truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def _fixture_key(fixture: Dict[str, Any]) -> str:
    from hibs_predictor.fixture_utils import fixture_team_name

    home = fixture_team_name(fixture, "home")
    away = fixture_team_name(fixture, "away")
    return f"{home}|{away}|{fixture.get('date', '')}"


_ALLOWED_FETCH_DAYS = (5, 7)
_FETCH_DAYS_COOKIE = "hibs_fetch_days"
_FETCH_DAYS_DEFAULT = 5


def _normalize_fetch_days(raw: Any, *, default: int = _FETCH_DAYS_DEFAULT) -> int:
    """User-selectable fixture window: only 5 or 7 days."""
    try:
        d = int(raw)
    except (TypeError, ValueError):
        return default
    return d if d in _ALLOWED_FETCH_DAYS else default


def _fetch_days_from_env() -> int:
    return _normalize_fetch_days(os.getenv("HIBS_FETCH_DAYS", str(_FETCH_DAYS_DEFAULT)))


def _fetch_window_days() -> int:
    """Resolve fixture window for this request (query ?days=, cookie, env) or scripts (env only)."""
    cached = getattr(g, "fetch_window_days", None) if has_request_context() else None
    if cached is not None:
        return int(cached)

    resolved = _fetch_days_from_env()
    if has_request_context():
        if request.args.get("days") is not None:
            resolved = _normalize_fetch_days(request.args.get("days"), default=resolved)
        elif request.cookies.get(_FETCH_DAYS_COOKIE):
            resolved = _normalize_fetch_days(
                request.cookies.get(_FETCH_DAYS_COOKIE), default=resolved
            )
        g.fetch_window_days = resolved
    return resolved


def _set_fetch_days_cookie_if_requested(response):
    """Persist ?days=5|7 on the dashboard response so API refreshes keep the window."""
    if not has_request_context():
        return response
    raw = request.args.get("days")
    if raw is None:
        return response
    days = _normalize_fetch_days(raw, default=_fetch_window_days())
    response.set_cookie(
        _FETCH_DAYS_COOKIE,
        str(days),
        max_age=60 * 60 * 24 * 365,
        samesite="Lax",
        path="/",
    )
    return response


def _min_league_chip_fixtures() -> int:
    """Leagues with fewer upcoming fixtures in the window are hidden from filter chips (still in All)."""
    try:
        n = int(os.getenv("HIBS_MIN_LEAGUE_CHIP_FIXTURES", "1"))
    except ValueError:
        n = 1
    return max(1, min(20, n))


def _ui_data_quality_min_pct() -> int:
    try:
        return max(50, min(100, int(os.getenv("HIBS_UI_FULL_DATA_MIN_PCT", "85"))))
    except ValueError:
        return 85


def _all_fixtures_cache_key() -> str:
    return f"all_fixtures_{_fetch_window_days()}d_{_FIXTURE_CACHE_VERSION}"


def _hibs_debug_log(message: str) -> None:
    if _env_truthy("HIBS_DEBUG"):
        print(f"[HIBS_DEBUG] {message}")


def _cache_ttl_hours(default: float = 1.0) -> float:
    try:
        return max(0.01, float(os.getenv("HIBS_CACHE_TTL_HOURS", str(default))))
    except ValueError:
        return default


def _maybe_prune_cache(cache: Cache) -> None:
    """Lightweight stale prune (throttled) when HIBS_CACHE_PRUNE is enabled."""
    global _cache_prune_last
    if (os.getenv("HIBS_CACHE_PRUNE") or "1").strip().lower() in ("0", "false", "no"):
        return
    import time as _time

    now = _time.monotonic()
    if now - _cache_prune_last < _CACHE_PRUNE_INTERVAL_SEC:
        return
    _cache_prune_last = now
    try:
        cache.prune_stale()
    except Exception:
        pass


def _clear_health_cache() -> None:
    _health_cache["t"] = 0.0
    _health_cache["payload"] = None


def clear_application_caches(*, all_disk: bool = False) -> int:
    """Clear in-memory health cache and on-disk fixture caches (or all JSON when all_disk)."""
    _clear_health_cache()
    cache = Cache()
    if all_disk:
        return cache.clear_all()
    removed = 0
    for pattern in ("all_fixtures_", "fixtures_"):
        removed += cache.clear_pattern(pattern, prefix=True)
    return removed


def _safe_enrich(fixture: Dict[str, Any], league_code: str) -> Dict[str, Any]:
    """Prefer full enrichment; on failure list the fixture without inventing xG/form/odds (unless HIBS_ALLOW_DUMMY=1)."""
    try:
        return aggregator.enrich_fixture(fixture, league_code)
    except Exception as exc:
        print(f"[Enrich fallback] {league_code} {_fixture_key(fixture)}: {exc}")
        if _env_truthy("HIBS_ALLOW_DUMMY"):
            league = LEAGUES.get(league_code, {})
            out = dict(fixture)
            out.setdefault("home_recent", [])
            out.setdefault("away_recent", [])
            out.setdefault("home_stats", {})
            out.setdefault("away_stats", {})
            out.setdefault("home_form", 0.5)
            out.setdefault("away_form", 0.5)
            out.setdefault("home_home_factor", 1.0)
            out.setdefault("away_away_factor", 1.0)
            out.setdefault("home_position", {})
            out.setdefault("away_position", {})
            out.setdefault("xg_home", 1.25)
            out.setdefault("xg_away", 1.15)
            out.setdefault("odds_home", None)
            out.setdefault("odds_draw", None)
            out.setdefault("odds_away", None)
            out.setdefault("odds_available", False)
            out.setdefault("all_bookmaker_odds", [])
            out.setdefault("fixture_injuries", [])
            out.setdefault("market_odds", {})
            out.setdefault("odds_secondary", None)
            out.setdefault("odds_cross_max_implied_diff_pct", 0.0)
            out.setdefault("league_factor", league.get("strength_factor", 1.0))
            out.setdefault("xg_source", "goals_proxy")
            out.setdefault("data_quality", {"score_pct": 0.0, "blocks": [], "full_scope": False, "strong_scope": False})
            return out
        out = dict(fixture)
        out.setdefault("home_recent", [])
        out.setdefault("away_recent", [])
        out.setdefault("home_stats", {})
        out.setdefault("away_stats", {})
        out.setdefault("home_position", {})
        out.setdefault("away_position", {})
        out.setdefault("odds_home", None)
        out.setdefault("odds_draw", None)
        out.setdefault("odds_away", None)
        out.setdefault("odds_available", False)
        out.setdefault("all_bookmaker_odds", [])
        out.setdefault("fixture_injuries", [])
        out.setdefault("market_odds", {})
        out.setdefault("odds_secondary", None)
        out.setdefault("odds_cross_max_implied_diff_pct", 0.0)
        out.setdefault("data_quality", {"score_pct": 0.0, "blocks": [], "full_scope": False, "strong_scope": False})
        out["_hibs_prediction_blocked"] = True
        out["_hibs_prediction_block_reason"] = "fixture_enrichment_failed"
        # Enrichment can fail after form/stats work but before odds; odds bundle only needs fixture id + team names.
        try:
            bundle = aggregator._fetch_odds_bundle(out, league_code)
            if isinstance(bundle, dict):
                out["odds_home"] = bundle.get("odds_home")
                out["odds_draw"] = bundle.get("odds_draw")
                out["odds_away"] = bundle.get("odds_away")
                out["odds_available"] = bool(bundle.get("odds_available"))
                out["all_bookmaker_odds"] = bundle.get("all_bookmaker_odds") or []
                out["market_odds"] = bundle.get("market_odds") or {}
                out["odds_secondary"] = bundle.get("odds_secondary")
                out["odds_cross_max_implied_diff_pct"] = bundle.get("odds_cross_max_implied_diff_pct") or 0.0
                out["odds_primary_source"] = bundle.get("odds_primary_source")
        except Exception:
            pass
        return out


def _competition_meta_from_api_sports(raw: Dict[str, Any]) -> Dict[str, Any]:
    lg = raw.get("league")
    if not isinstance(lg, dict):
        return {}
    meta: Dict[str, Any] = {}
    name = (lg.get("name") or "").strip()
    rnd = (lg.get("round") or "").strip()
    if name:
        meta["api_league_name"] = name
    if rnd:
        meta["api_round"] = rnd
    return meta


def _fdo_round_from_match(match: Dict[str, Any]) -> Optional[str]:
    stage = match.get("stage")
    if stage is None or stage == "":
        return None
    s = str(stage).strip().upper().replace("-", "_")
    if s in ("REGULAR_SEASON", "GROUP_STAGE"):
        return None
    labels = {
        "FINAL": "Final",
        "SEMI_FINALS": "Semi-finals",
        "QUARTER_FINALS": "Quarter-finals",
        "LAST_16": "Round of 16",
        "LAST_32": "Round of 32",
        "ROUND_OF_16": "Round of 16",
        "PLAYOFF_ROUND": "Play-offs",
    }
    return labels.get(s, str(stage).replace("_", " ").title())


def _competition_meta_from_fdo(match: Dict[str, Any]) -> Dict[str, Any]:
    comp = match.get("competition")
    meta: Dict[str, Any] = {}
    if isinstance(comp, dict):
        cn = (comp.get("name") or "").strip()
        if cn:
            meta["fdo_competition_name"] = cn
    rnd = _fdo_round_from_match(match)
    if rnd:
        meta["api_round"] = rnd
    return meta


def _competition_meta_from_fotmob(match: Dict[str, Any]) -> Dict[str, Any]:
    fm = match.get("_fotmob_league")
    if not isinstance(fm, dict):
        return {}
    nm = (fm.get("name") or "").strip()
    return {"fotmob_league_name": nm} if nm else {}


def _normalize_api_sports(fixture: Dict, league_code: str) -> Optional[Dict]:
    fm = fixture.get("fixture", {})
    home = fixture.get("teams", {}).get("home", {})
    away = fixture.get("teams", {}).get("away", {})
    if not fm or not home or not away:
        return None
    comp_meta = _competition_meta_from_api_sports(fixture)
    return {
        "fixture": {"id": fm.get("id"), "date": fm.get("date"), "status": fm.get("status", {})},
        "teams": {
            "home": {"id": home.get("id", 0), "name": home.get("name", "?")},
            "away": {"id": away.get("id", 0), "name": away.get("name", "?")},
        },
        "home": {"id": home.get("id", 0), "name": home.get("name", "?")},
        "away": {"id": away.get("id", 0), "name": away.get("name", "?")},
        "date": fm.get("date"),
        "league": league_code,
        "competition_meta": comp_meta,
    }


def _normalize_fdo(match: Dict, league_code: str) -> Optional[Dict]:
    if not match:
        return None
    home = match.get("homeTeam", {}) or {}
    away = match.get("awayTeam", {}) or {}
    date = match.get("utcDate")
    if not date or not home or not away:
        return None
    comp_meta = _competition_meta_from_fdo(match)
    return {
        "fixture": {"id": match.get("id"), "date": date, "status": {"short": match.get("status", "")}},
        "teams": {
            "home": {"id": home.get("id", 0), "name": home.get("name", "?")},
            "away": {"id": away.get("id", 0), "name": away.get("name", "?")},
        },
        "home": {"id": home.get("id", 0), "name": home.get("name", "?")},
        "away": {"id": away.get("id", 0), "name": away.get("name", "?")},
        "date": date,
        "league": league_code,
        "competition_meta": comp_meta,
    }


def _normalize_fotmob(match: Dict, league_code: str) -> Optional[Dict]:
    """Normalize a FotMob public daily-match row into the app fixture shape."""
    if not match:
        return None
    home = match.get("home") or {}
    away = match.get("away") or {}
    home_name = home.get("name") if isinstance(home, dict) else None
    away_name = away.get("name") if isinstance(away, dict) else None
    date_s = match.get("utcTime") or match.get("time") or match.get("date")
    mid = match.get("id") or match.get("matchId")
    if not home_name or not away_name or not date_s:
        return None
    comp_meta = _competition_meta_from_fotmob(match)
    return {
        "fixture": {"id": f"fotmob_{mid}" if mid else None, "date": date_s, "status": {"short": match.get("status", {}).get("short") if isinstance(match.get("status"), dict) else match.get("status")}},
        "teams": {
            "home": {"id": home.get("id", 0) if isinstance(home, dict) else 0, "name": home_name},
            "away": {"id": away.get("id", 0) if isinstance(away, dict) else 0, "name": away_name},
        },
        "home": {"id": home.get("id", 0) if isinstance(home, dict) else 0, "name": home_name},
        "away": {"id": away.get("id", 0) if isinstance(away, dict) else 0, "name": away_name},
        "date": date_s,
        "league": league_code,
        "competition_meta": comp_meta,
        "source": "fotmob_public",
    }


def fetch_next_48h_fixtures(league_code: str) -> List[Dict]:
    days = _fetch_window_days()
    cache = Cache()
    prefer_fdo = _env_truthy("HIBS_PREFER_FOOTBALL_DATA_FIXTURES")
    skip_as_fx = _env_truthy("HIBS_SKIP_API_SPORTS_FIXTURES")
    ttl = _cache_ttl_hours(1.0)
    cache_key = f"fixtures_{days}d_{league_code}_{_FIXTURE_CACHE_VERSION}_{int(prefer_fdo)}{int(skip_as_fx)}"
    cached = cache.get(cache_key, ttl_hours=ttl)
    if cached:
        if cached:
            return cached
        _hibs_debug_log(f"skip empty per-league cache {league_code} key={cache_key}")

    league = LEAGUES.get(league_code, {})
    now = datetime.now(timezone.utc)
    window_start = fixture_window_start_utc(now)
    cutoff = fixture_window_end_utc(now, days)
    fetched: Dict[str, Dict] = {}
    date_from = window_start.strftime("%Y-%m-%d")
    date_to = cutoff.strftime("%Y-%m-%d")
    fdo_comp = league.get("football_data_org_id")
    season_candidates = _fixture_fetch_season_candidates(fdo_comp, date_from, date_to, now)

    def add(candidate: Dict) -> None:
        key = _fixture_key(candidate)
        if key and key not in fetched:
            fetched[key] = candidate

    league_api_id = league.get("api_sports_id")

    def try_api_sports() -> None:
        if skip_as_fx or "api_sports" not in aggregator.clients or not league_api_id:
            return
        try:
            for season in season_candidates:
                raw = aggregator.clients["api_sports"].fetch_fixtures_by_league(
                    int(league_api_id),
                    int(season),
                    date_from=date_from,
                    date_to=date_to,
                )
                for f in raw or []:
                    norm = _normalize_api_sports(f, league_code)
                    if not norm:
                        continue
                    try:
                        raw_date = norm.get("date") or ""
                        fd = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                        if window_start <= fd <= cutoff:
                            norm["date"] = fd.isoformat()
                            add(norm)
                    except (TypeError, ValueError, OSError) as parse_err:
                        print(f"[API-Sports date] {league_code}: {parse_err} raw={norm.get('date')!r}")
                        continue
                if fetched:
                    break
        except Exception as e:
            print(f"[API-Sports] {league_code}: {e!r}")

    def try_football_data() -> None:
        if "football_data_org" not in aggregator.clients:
            return
        comp = league.get("football_data_org_id")
        if not comp:
            return
        for season in season_candidates:
            try:
                import time as _time

                _time.sleep(0.5)
                raw = aggregator.clients["football_data_org"].fetch_fixtures(
                    comp,
                    season,
                    status=None,
                    date_from=date_from,
                    date_to=date_to,
                )
                for m in raw or []:
                    st = str(m.get("status") or "").upper()
                    norm = _normalize_fdo(m, league_code)
                    if not norm:
                        continue
                    try:
                        fd = datetime.fromisoformat(norm["date"].replace("Z", "+00:00"))
                    except Exception:
                        continue
                    if st in ("CANCELLED", "POSTPONED", "ABANDONED", "SUSPENDED"):
                        continue
                    if st in ("FINISHED", "AWARDED") and fd < window_start:
                        continue
                    if window_start <= fd <= cutoff:
                        norm["date"] = fd.isoformat()
                        add(norm)
                if fetched:
                    break
            except Exception as ex:
                print(f"[Football-Data.org] {league_code} {comp} season={season}: {ex!r}")
                continue

    def try_fotmob() -> None:
        if os.getenv("HIBS_ENABLE_FOTMOB_FIXTURES", "1").strip().lower() in ("0", "false", "no", "off"):
            return
        try:
            from hibs_predictor.scrapers import fotmob_client

            raw = fotmob_client.fixtures_for_league(league_code, now.date(), cutoff.date(), cache=cache)
            for m in raw or []:
                norm = _normalize_fotmob(m, league_code)
                if not norm:
                    continue
                try:
                    fd = datetime.fromisoformat(str(norm["date"]).replace("Z", "+00:00"))
                    if window_start <= fd <= cutoff:
                        norm["date"] = fd.isoformat()
                        add(norm)
                except Exception:
                    continue
        except Exception as ex:
            print(f"[FotMob] {league_code}: {ex!r}")

    api_first = league_code in _API_FIRST_FIXTURE_LEAGUES
    if api_first or not prefer_fdo:
        try_api_sports()
        if not fetched:
            try_football_data()
    else:
        try_football_data()
        if not fetched:
            try_api_sports()
    if not fetched:
        try_fotmob()

    _hibs_debug_log(
        f"fixtures {league_code} days={days} count={len(fetched)} api_first={api_first} prefer_fdo={prefer_fdo}"
    )

    fixtures = []
    for fixture in fetched.values():
        enriched = _safe_enrich(fixture, league_code)
        try:
            prediction = betting_engine.predict_with_confidence(enriched)
        except Exception as e:
            print(f"[Prediction] {league_code} {_fixture_key(fixture)}: {e!r}")
            prediction = prediction_unavailable_payload(enriched, "model_error")

        home_id = fixture.get("teams", {}).get("home", {}).get("id")
        away_id = fixture.get("teams", {}).get("away", {}).get("id")
        try:
            home_last10 = TeamStrengthCalculator.parse_last_10_results(enriched.get("home_recent", []), home_id)
            away_last10 = TeamStrengthCalculator.parse_last_10_results(enriched.get("away_recent", []), away_id)
        except Exception as e:
            print(f"[Fixture last10] {league_code} {_fixture_key(fixture)}: {e!r}")
            home_last10, away_last10 = [], []

        comp_meta = enriched.get("competition_meta") if isinstance(enriched.get("competition_meta"), dict) else {}
        if not comp_meta and isinstance(fixture.get("competition_meta"), dict):
            comp_meta = fixture.get("competition_meta") or {}
        fb_name = LEAGUES.get(league_code, {}).get("name", league_code)
        title = display_competition_title(
            fallback_name=fb_name,
            api_league_name=comp_meta.get("api_league_name"),
            api_round=comp_meta.get("api_round"),
            fotmob_league_name=comp_meta.get("fotmob_league_name"),
            fdo_competition_name=comp_meta.get("fdo_competition_name"),
        )

        row = {
            "id": fixture.get("fixture", {}).get("id"),
            "home": fixture.get("home", {}).get("name", "?"),
            "away": fixture.get("away", {}).get("name", "?"),
            "home_id": home_id,
            "away_id": away_id,
            "date": fixture.get("date"),
            "league": league_code,
            "league_name": title,
            "competition_meta": comp_meta,
            "league_flag": LEAGUES.get(league_code, {}).get("flag", ""),
            "prediction": prediction,
            "home_last10": home_last10,
            "away_last10": away_last10,
            "home_position": enriched.get("home_position", {}),
            "away_position": enriched.get("away_position", {}),
            "home_stats": enriched.get("home_stats"),
            "away_stats": enriched.get("away_stats"),
            "all_bookmaker_odds": enriched.get("all_bookmaker_odds", []),
            "fixture_injuries": enriched.get("fixture_injuries", []),
            "market_odds": enriched.get("market_odds", {}),
            "supplemental": enriched.get("supplemental", {}),
            "xg_source": enriched.get("xg_source", "unknown"),
            "has_value_bet": bool(prediction.get("has_any_value", prediction.get("value_bets"))),
        }
        row["data_quality"] = _data_quality_for_enriched(enriched, prediction)
        fixtures.append(row)

    fixtures.sort(key=lambda x: x.get("date") or "")
    cache.set(
        cache_key,
        fixtures,
        ttl_hours=ttl if fixtures else _EMPTY_FIXTURE_CACHE_TTL_HOURS,
    )
    return fixtures


def _data_quality_for_enriched(enriched: Dict[str, Any], prediction: Dict[str, Any]) -> Dict[str, Any]:
    """Score coverage after prediction so line_odds and book prices count toward the bar."""
    from hibs_predictor.data_quality import compute_fixture_data_quality

    scoring = dict(enriched)
    scoring["prediction"] = prediction
    lo = prediction.get("line_odds") or {}
    if lo:
        scoring["line_odds"] = lo
    bo = prediction.get("bookmaker_odds") or {}
    if bo and not scoring.get("odds_available"):
        try:
            scoring["odds_available"] = all(float(bo.get(k) or 0) > 1.0 for k in ("home", "draw", "away"))
        except (TypeError, ValueError):
            pass
        scoring.setdefault("odds_home", bo.get("home"))
        scoring.setdefault("odds_draw", bo.get("draw"))
        scoring.setdefault("odds_away", bo.get("away"))
    return compute_fixture_data_quality(scoring)


def _ensure_fixture_data_quality(all_fixtures: List[Dict[str, Any]]) -> None:
    """Re-score slim cached rows so xG/form/line-odds fallbacks apply without full re-enrich."""
    from hibs_predictor.data_quality import compute_fixture_data_quality_from_row

    for f in all_fixtures:
        try:
            new_dq = compute_fixture_data_quality_from_row(f)
            old_pct = float((f.get("data_quality") or {}).get("score_pct") or 0)
            if float(new_dq.get("score_pct") or 0) >= old_pct:
                f["data_quality"] = new_dq
        except Exception as exc:
            print(f"[Data quality] {f.get('home')} v {f.get('away')}: {exc!r}")


def _ensure_fixture_pick_menus(all_fixtures: List[Dict[str, Any]]) -> None:
    """Backfill pick_menu / structured_insight on cached rows from older bundle versions."""
    from hibs_predictor.match_insight import attach_structured_insight

    for f in all_fixtures:
        p = f.get("prediction")
        if not isinstance(p, dict):
            continue
        if p.get("pick_menu"):
            continue
        try:
            attach_structured_insight(f, p)
        except Exception as exc:
            print(f"[Pick menu] {f.get('home')} v {f.get('away')}: {exc!r}")


def _safe_int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _team_key(name: Any) -> str:
    import re

    text = re.sub(r"[^a-z0-9]+", " ", str(name or "").lower()).strip()
    for suffix in (" fc", " afc", " cf", " sc"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    return text


def _table_row_from_position(team: str, position: Dict[str, Any], source: str = "fixture") -> Optional[Dict[str, Any]]:
    if not isinstance(position, dict):
        return None
    rank = position.get("position", position.get("rank"))
    if rank in (None, "", "?"):
        return None
    row = {
        "position": _safe_int_value(rank, 999),
        "team": team or position.get("team") or "Unknown",
        "played": _safe_int_value(position.get("played")),
        "won": _safe_int_value(position.get("won")),
        "drawn": _safe_int_value(position.get("drawn")),
        "lost": _safe_int_value(position.get("lost")),
        "goals_for": _safe_int_value(position.get("goals_for")),
        "goals_against": _safe_int_value(position.get("goals_against")),
        "goal_diff": _safe_int_value(position.get("goal_diff")),
        "points": _safe_int_value(position.get("points")),
        "form": position.get("form") or "",
        "source": position.get("source") or source,
    }
    if row["position"] == 999:
        return None
    return row


def _table_row_from_api_entry(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    team = ((entry.get("team") or {}).get("name")) or entry.get("team_name") or entry.get("team")
    all_stats = entry.get("all") or {}
    goals = all_stats.get("goals") or {}
    return _table_row_from_position(
        str(team or ""),
        {
            "position": entry.get("rank"),
            "played": all_stats.get("played"),
            "won": all_stats.get("win"),
            "drawn": all_stats.get("draw"),
            "lost": all_stats.get("lose"),
            "goals_for": goals.get("for"),
            "goals_against": goals.get("against"),
            "goal_diff": entry.get("goalsDiff"),
            "points": entry.get("points"),
            "form": entry.get("form"),
            "source": "api_sports",
        },
    )


def _table_row_from_fdo_entry(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    team = ((entry.get("team") or {}).get("name")) or entry.get("team_name") or entry.get("team")
    return _table_row_from_position(
        str(team or ""),
        {
            "position": entry.get("position"),
            "played": entry.get("playedGames"),
            "won": entry.get("won"),
            "drawn": entry.get("draw"),
            "lost": entry.get("lost"),
            "goals_for": entry.get("goalsFor"),
            "goals_against": entry.get("goalsAgainst"),
            "goal_diff": entry.get("goalDifference"),
            "points": entry.get("points"),
            "form": entry.get("form"),
            "source": "football_data_org",
        },
    )


def _season_status_for_rows(rows: List[Dict[str, Any]], season: int, primary_season: int) -> List[Dict[str, Any]]:
    if season == primary_season:
        return rows
    out = []
    for row in rows:
        r = dict(row)
        r.setdefault("season_status", "last_completed")
        out.append(r)
    return out


def _fetch_full_table_rows(league_code: str, *, live_fetch: Optional[bool] = None) -> List[Dict[str, Any]]:
    """Best-effort full standings for the tables page; callers fall back to fixture rows.

    Dashboard snapshots read existing cache only; /tables can live-fetch from
    configured documented API clients and falls back to previous season rows
    when the current/ended competition has no table in the active season id.
    """
    league = LEAGUES.get(league_code) or {}
    league_api_id = league.get("api_sports_id")
    fdo_comp = league.get("football_data_org_id")
    now = datetime.now(timezone.utc)
    primary_season = _api_football_season_year(now)
    allow_live = _env_truthy("HIBS_TABLES_LIVE_FETCH") if live_fetch is None else (bool(live_fetch) or _env_truthy("HIBS_TABLES_LIVE_FETCH"))
    if league_api_id and "api_sports" in aggregator.clients and not _env_truthy("HIBS_SKIP_API_STANDINGS"):
        for season in (primary_season, primary_season - 1):
            try:
                params = {"league": int(league_api_id), "season": int(season)}
                groups_payload = aggregator.clients["api_sports"].cache.get(
                    f"api_sports_standings_{str(params)}", ttl_hours=24
                )
                if groups_payload:
                    response = groups_payload.get("response", []) if isinstance(groups_payload, dict) else []
                    groups = response[0].get("league", {}).get("standings", [[]]) if response else [[]]
                elif allow_live:
                    groups = aggregator.clients["api_sports"].fetch_standings(int(league_api_id), int(season))
                else:
                    groups = []
                rows = [
                    row
                    for group in (groups or [])
                    for entry in (group or [])
                    for row in [_table_row_from_api_entry(entry)]
                    if row
                ]
                if rows:
                    return _season_status_for_rows(rows, season, primary_season)
            except Exception as exc:
                print(f"[Tables api_sports] {league_code}: {exc!r}")
                continue
    if fdo_comp and "football_data_org" in aggregator.clients:
        for season in (primary_season, primary_season - 1):
            try:
                params = {"season": int(season)}
                payload = aggregator.clients["football_data_org"].cache.get(
                    f"football_data_org_competitions/{fdo_comp}/standings_{str(params)}", ttl_hours=24
                )
                if isinstance(payload, dict):
                    groups = payload.get("standings", []) or []
                elif allow_live:
                    groups = aggregator.clients["football_data_org"].fetch_standings(str(fdo_comp), int(season))
                else:
                    groups = []
                rows = [
                    row
                    for group in (groups or [])
                    if str(group.get("type") or "").upper() in ("TOTAL", "")
                    for entry in (group.get("table") or [])
                    for row in [_table_row_from_fdo_entry(entry)]
                    if row
                ]
                if rows:
                    return _season_status_for_rows(rows, season, primary_season)
            except Exception as exc:
                print(f"[Tables football_data] {league_code}: {exc!r}")
                continue
    try:
        from hibs_predictor.scrapers import wikipedia_standings as wiki_standings

        sk = wiki_standings._season_wiki_title_part()
        cached = aggregator.cache.get(f"wiki_stand_{league_code}_{sk}", ttl_hours=12)
        if cached is None and allow_live:
            cached = aggregator._cached_wikipedia_league_table(league_code)
        rows = [
            _table_row_from_position(str(r.get("team") or ""), wiki_standings.row_to_position_shape(r), "wikipedia")
            for r in (cached or [])
        ]
        return [r for r in rows if r]
    except Exception as exc:
        print(f"[Tables wikipedia] {league_code}: {exc!r}")
    return []


def _fixture_position_rows(fixtures: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    by_league: Dict[str, List[Dict[str, Any]]] = {}
    for fixture in fixtures:
        league_code = fixture.get("league") or ""
        if not league_code:
            continue
        for team_key, pos_key in (("home", "home_position"), ("away", "away_position")):
            row = _table_row_from_position(str(fixture.get(team_key) or ""), fixture.get(pos_key) or {})
            if row:
                by_league.setdefault(league_code, []).append(row)
    return by_league


def _dedupe_table_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_team: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = _team_key(row.get("team"))
        if not key:
            continue
        existing = by_team.get(key)
        if existing is None or (
            existing.get("source") == "fixture" and row.get("source") != "fixture"
        ):
            by_team[key] = row
    return sorted(by_team.values(), key=lambda r: (_safe_int_value(r.get("position"), 999), str(r.get("team") or "")))


def _build_league_tables(fixtures: List[Dict[str, Any]], *, include_live: bool = False) -> List[Dict[str, Any]]:
    fixture_rows = _fixture_position_rows(fixtures)
    league_codes = set(fixture_rows)
    league_codes.update(str(f.get("league") or "") for f in fixtures if f.get("league"))
    if include_live:
        league_codes.update(DASHBOARD_LEAGUE_ORDER)
    order_index = {c: i for i, c in enumerate(DASHBOARD_LEAGUE_ORDER)}
    tables: List[Dict[str, Any]] = []
    for league_code in sorted(league_codes, key=lambda c: (order_index.get(c, 999), c)):
        rows: List[Dict[str, Any]] = []
        full_rows = _fetch_full_table_rows(league_code, live_fetch=include_live)
        rows.extend(full_rows)
        rows.extend(fixture_rows.get(league_code, []))
        rows = _dedupe_table_rows(rows)
        used_last_completed = any(row.get("season_status") == "last_completed" for row in rows)
        tables.append(
            {
                "code": league_code,
                "name": LEAGUES.get(league_code, {}).get("name", league_code),
                "rows": rows,
                "source": rows[0].get("source") if rows else "",
                "is_partial": len(rows) < 8,
                "season_status": "last_completed" if used_last_completed else "current",
                "status_note": (
                    "Latest completed-season standings used because current fixtures/tables are thin."
                    if used_last_completed
                    else ""
                ),
            }
        )
    return tables


def _snapshot_for_team(rows: List[Dict[str, Any]], team: str) -> List[Dict[str, Any]]:
    key = _team_key(team)
    if not key:
        return []
    idx = next((i for i, row in enumerate(rows) if _team_key(row.get("team")) == key), None)
    if idx is None:
        return []
    start = max(0, idx - 1)
    end = min(len(rows), idx + 2)
    snapshot = []
    for i, row in enumerate(rows[start:end], start=start):
        out = dict(row)
        out["is_focus"] = i == idx
        snapshot.append(out)
    return snapshot


def _attach_table_snapshots(fixtures: List[Dict[str, Any]], tables: List[Dict[str, Any]]) -> None:
    by_code = {t["code"]: t.get("rows") or [] for t in tables}
    for fixture in fixtures:
        rows = by_code.get(fixture.get("league") or "", [])
        fixture["home_table_snapshot"] = _snapshot_for_team(rows, str(fixture.get("home") or ""))
        fixture["away_table_snapshot"] = _snapshot_for_team(rows, str(fixture.get("away") or ""))


def _finalize_fixture_bundle(all_fixtures: List[Dict[str, Any]]) -> Dict[str, Any]:
    from hibs_predictor.display_tz import enrich_fixtures_kickoff
    from hibs_predictor.live_scores import attach_live_to_fixtures

    all_fixtures = enrich_fixtures_kickoff(all_fixtures)
    for row in all_fixtures:
        row["dashboard_region"] = league_dashboard_region(str(row.get("league") or ""))
    try:
        attach_live_to_fixtures(all_fixtures, aggregator, include_events=True, include_stats=True)
    except Exception as exc:
        print(f"[Live scores] attach failed: {exc!r}")
    _ensure_fixture_data_quality(all_fixtures)
    _ensure_fixture_pick_menus(all_fixtures)
    all_fixtures.sort(key=lambda x: x.get("kickoff_sort") or x.get("date") or "")
    league_tables = _build_league_tables(all_fixtures, include_live=False)
    _attach_table_snapshots(all_fixtures, league_tables)
    value_bets_only = [f for f in all_fixtures if f.get("has_value_bet")]
    value_bets_only.sort(key=lambda x: -(x.get("prediction", {}).get("best_bet_roi") or 0))
    fixtures_by_league: Dict[str, List] = {c: [] for c in DASHBOARD_LEAGUE_ORDER}
    for f in all_fixtures:
        lc = f.get("league")
        if lc in fixtures_by_league:
            fixtures_by_league[lc].append(f)
    for c in fixtures_by_league:
        fixtures_by_league[c].sort(key=lambda x: x.get("kickoff_sort") or x.get("date") or "")
    by_region: Dict[str, List] = {r: [] for r in LEAGUE_REGIONS}
    for f in all_fixtures:
        for region, codes in LEAGUE_REGIONS.items():
            if f.get("league") in codes:
                by_region[region].append(f)
    coverage_summary = _fixture_coverage_summary(fixtures_by_league, len(all_fixtures))
    return {
        "all": all_fixtures,
        "by_region": by_region,
        "by_league": fixtures_by_league,
        "dashboard_days": _dashboard_days_groups(all_fixtures),
        "value_bets": value_bets_only,
        "total": len(all_fixtures),
        "value_bet_count": len(value_bets_only),
        "fetch_days": _fetch_window_days(),
        "has_api_clients": ("api_sports" in aggregator.clients or "football_data_org" in aggregator.clients),
        "sidebar_upcoming": _sidebar_upcoming(all_fixtures),
        "league_tables": league_tables,
        "fixture_coverage": coverage_summary,
    }


def _fixture_coverage_summary(by_league: Dict[str, List], total: int) -> Dict[str, Any]:
    """User-facing note explaining why filter chips only show leagues with returned fixtures."""
    loaded: List[Dict[str, Any]] = []
    empty: List[Dict[str, Any]] = []
    for code in DASHBOARD_LEAGUE_ORDER:
        if code not in LEAGUES:
            continue
        league = LEAGUES[code]
        count = len(by_league.get(code) or [])
        row = {
            "code": code,
            "name": league.get("name", code),
            "count": count,
            "api_sports_id": league.get("api_sports_id"),
            "football_data_org_id": league.get("football_data_org_id"),
        }
        if count:
            loaded.append(row)
        else:
            empty.append(row)
    days = _fetch_window_days()
    return {
        "total_configured": len(loaded) + len(empty),
        "loaded": loaded,
        "empty": empty,
        "loaded_count": len(loaded),
        "empty_count": len(empty),
        "empty_sample": empty[:8],
        "window_days": days,
        "summary": (
            f"{len(loaded)} of {len(loaded) + len(empty)} configured leagues returned fixtures "
            f"in the next {days} days."
        ),
        "reason": (
            "Filter chips are built only from leagues with fixtures in the current window. "
            "Empty leagues usually have no published matches in this date range, are outside the active season/cup window, "
            "have completed their season, or depend on a provider/plan that did not return fixtures."
        ),
        "detail": (
            "Football-Data.org and API-Football/API-Sports standings can still populate table snapshots and the Tables page "
            "when upcoming fixtures are thin. Scrapers enrich fixtures after they exist, but they are not fixture calendars."
        ),
        "has_any_fixtures": total > 0,
    }


def _dashboard_info_box(fixture_coverage: Dict[str, Any], total: int) -> Dict[str, Any]:
    """Small user-facing dashboard summary; feed/provider detail belongs on /status."""
    loaded = fixture_coverage.get("loaded") or []
    loaded_names = [str(row.get("name") or row.get("code")) for row in loaded if row]
    return {
        "loaded_count": len(loaded_names),
        "loaded_names": loaded_names,
        "loaded_names_text": ", ".join(loaded_names),
        "total_fixtures": total,
        "description": (
            "hibs-bet turns upcoming fixtures into probability-led match reads: form, odds, table context, "
            "data quality and value signals are combined to help compare bets and spot stronger angles."
        ),
    }


def fetch_all_fixtures() -> Dict:
    cache = Cache()
    _maybe_prune_cache(cache)
    ttl = _cache_ttl_hours(1.0)
    ck = _all_fixtures_cache_key()
    cached = cache.get(ck, ttl_hours=ttl)
    if cached:
        all_f = cached.get("all") or []
        if all_f:
            return _finalize_fixture_bundle(all_f)
        _hibs_debug_log(f"skip empty all_fixtures cache key={ck}")

    all_fixtures: List[Dict] = []

    for league_code in ALL_LEAGUE_CODES:
        try:
            all_fixtures.extend(fetch_next_48h_fixtures(league_code))
        except Exception as e:
            print(f"[AllFixtures] {league_code}: {e}")

    result = _finalize_fixture_bundle(all_fixtures)
    if result.get("total"):
        cache.set(ck, result, ttl_hours=ttl)
    else:
        _hibs_debug_log(f"not caching empty all_fixtures bundle key={ck}")
    return result


def _fixture_ko_sort_key(fixture: Dict[str, Any]) -> str:
    """Sort key: kick-off datetime (UTC ISO, empty last)."""
    return str(fixture.get("kickoff_sort") or fixture.get("date") or "9999")


def _sidebar_upcoming(all_fixtures: List[Dict[str, Any]], limit: int = 80) -> List[Dict[str, Any]]:
    """Compact upcoming list for the left rail (navigation only)."""
    rows: List[Dict[str, Any]] = []
    for f in sorted(all_fixtures, key=_fixture_ko_sort_key):
        fid = f.get("id")
        if fid is None:
            continue
        rows.append(
            {
                "id": fid,
                "home": f.get("home", "?"),
                "away": f.get("away", "?"),
                "league": f.get("league", ""),
                "league_name": f.get("league_name", ""),
                "dashboard_region": f.get("dashboard_region")
                or league_dashboard_region(str(f.get("league") or "")),
                "kickoff_time": f.get("kickoff_time") or "—",
                "kickoff_day_local": f.get("kickoff_day_local") or "",
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _league_block_display_name(league_code: str, fixtures: List[Dict[str, Any]]) -> str:
    """Section heading: shared per-fixture league_name when uniform, else configured league label."""
    names = [(f.get("league_name") or "").strip() for f in fixtures]
    names = [n for n in names if n]
    if len(set(names)) == 1:
        return names[0]
    return LEAGUES.get(league_code, {}).get("name", league_code)


def _dashboard_days_groups(all_fixtures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group fixtures by local calendar day, leagues in DASHBOARD_LEAGUE_ORDER, each league by KO time."""
    from collections import defaultdict
    from hibs_predictor.display_tz import day_heading_for_local_date, local_today

    by_day: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for f in all_fixtures:
        day_iso = (f.get("kickoff_day_local") or "").strip()
        if not day_iso:
            raw = f.get("date") or ""
            if len(raw) < 10:
                continue
            day_iso = raw[:10]
        lc = f.get("league") or ""
        if lc:
            by_day[day_iso][lc].append(f)
    today_local = local_today()
    order_index = {c: i for i, c in enumerate(DASHBOARD_LEAGUE_ORDER)}
    out: List[Dict[str, Any]] = []
    for day_iso in sorted(by_day.keys()):
        leagues_block: List[Dict[str, Any]] = []
        seen_lc = set()

        def _append_league(lc: str) -> None:
            fl = by_day[day_iso].get(lc, [])
            if not fl:
                return
            fl.sort(key=_fixture_ko_sort_key)
            leagues_block.append(
                {
                    "code": lc,
                    "name": _league_block_display_name(lc, fl),
                    "fixtures": fl,
                }
            )
            seen_lc.add(lc)

        for lc in DASHBOARD_LEAGUE_ORDER:
            _append_league(lc)
        for lc in sorted(by_day[day_iso].keys(), key=lambda c: (order_index.get(c, 999), c)):
            if lc not in seen_lc and by_day[day_iso][lc]:
                _append_league(lc)
        if not leagues_block:
            continue
        day_count = sum(len(lb["fixtures"]) for lb in leagues_block)
        heading = day_heading_for_local_date(day_iso, day_count, today_local)
        out.append({"date_iso": day_iso, "heading": heading, "fixture_count": day_count, "leagues": leagues_block})
    return out


def _leagues_for_filter(by_league: Dict[str, List]) -> List[tuple]:
    """League filter chips in dashboard order — every competition with fixtures in the window."""
    order_index = {c: i for i, c in enumerate(DASHBOARD_LEAGUE_ORDER)}
    min_n = _min_league_chip_fixtures()
    codes: List[str] = []
    seen: set = set()
    for c in DASHBOARD_LEAGUE_ORDER:
        if c in LEAGUES and len(by_league.get(c) or []) >= min_n:
            codes.append(c)
            seen.add(c)
    for c in sorted(by_league.keys(), key=lambda x: (order_index.get(x, 999), x)):
        if c in LEAGUES and c not in seen and len(by_league.get(c) or []) >= min_n:
            codes.append(c)
    return [(c, LEAGUES[c].get("name", c)) for c in codes]


def _assistant_packets_from_fixtures(fixtures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from hibs_predictor.match_insight import build_assistant_packet

    return [build_assistant_packet(f) for f in fixtures]


def _assistant_bundle(fixtures: List[Dict[str, Any]]) -> Dict[str, Any]:
    from hibs_predictor.assistant_recommendations import build_assistant_recommendations

    packets = _assistant_packets_from_fixtures(fixtures)
    return {
        "packets": packets,
        "recommendations": build_assistant_recommendations(packets),
        "count": len(packets),
    }


@app.route("/")
def index():
    if request.args.get("refresh") == "1":
        clear_application_caches(all_disk=request.args.get("all") == "1")
    data = fetch_all_fixtures()
    assistant_bundle = _assistant_bundle(data["all"])
    assistant_packets = assistant_bundle["packets"]
    fixture_coverage = data.get("fixture_coverage", {})
    return render_template(
        "dashboard.html",
        all_fixtures=data["all"],
        by_region=data["by_region"],
        by_league=data["by_league"],
        dashboard_days=data["dashboard_days"],
        value_bets=data["value_bets"],
        total=data["total"],
        value_bet_count=data["value_bet_count"],
        fixture_coverage=fixture_coverage,
        dashboard_info=_dashboard_info_box(fixture_coverage, data["total"]),
        league_regions=LEAGUE_REGIONS,
        dashboard_filter_regions=DASHBOARD_FILTER_REGIONS,
        leagues_for_filter=_leagues_for_filter(data["by_league"]),
        min_league_chip_fixtures=_min_league_chip_fixtures(),
        dashboard_league_order=DASHBOARD_LEAGUE_ORDER,
        fetch_days=data.get("fetch_days", _fetch_window_days()),
        has_api_clients=data.get(
            "has_api_clients",
            ("api_sports" in aggregator.clients or "football_data_org" in aggregator.clients),
        ),
        leagues=LEAGUES,
        data_quality_ui_min=_ui_data_quality_min_pct(),
        assistant_packets=assistant_packets,
        sky_sports_news_embed_url=SKY_SPORTS_NEWS_YOUTUBE_EMBED_URL,
        sky_sports_news_watch_url=SKY_SPORTS_NEWS_WATCH_URL,
        assistant_recommendations=assistant_bundle.get("recommendations"),
        sidebar_upcoming=data.get("sidebar_upcoming", []),
        display_tz_label=display_tz_label(),
    )


@app.route("/api/assistant/snapshot")
def api_assistant_snapshot():
    """Structured insight packets + acca/market recommendations for the Betting Assistant."""
    data = fetch_all_fixtures()
    bundle = _assistant_bundle(data["all"])
    return jsonify(bundle)


@app.route("/api/assistant/recommendations")
def api_assistant_recommendations():
    """Acca and market recommendations only (packets omitted for lighter payload)."""
    data = fetch_all_fixtures()
    bundle = _assistant_bundle(data["all"])
    return jsonify(
        {
            "recommendations": bundle.get("recommendations"),
            "count": bundle.get("count", 0),
        }
    )


@app.route("/api/assistant/chat", methods=["POST"])
def api_assistant_chat():
    """Natural-language assistant: stats, accas, best bets (data-gated)."""
    from hibs_predictor.assistant_chat import handle_chat

    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or payload.get("q") or "").strip()
    if not question:
        return jsonify({"error": "question required"}), 400
    fixture_id = payload.get("fixture_id")
    data = fetch_all_fixtures()
    bundle = _assistant_bundle(data["all"])
    reply = handle_chat(
        question,
        bundle.get("packets") or [],
        recommendations=bundle.get("recommendations"),
        fixture_id=fixture_id,
    )
    return jsonify(reply)


@app.route("/api/audit/summary")
def api_audit_summary():
    """Calibration / audit metrics from the prediction log SQLite (optional)."""
    tok = (os.getenv("HIBS_AUDIT_API_TOKEN") or "").strip()
    if not tok or request.args.get("token", "") != tok:
        abort(404)
    from hibs_predictor.prediction_log import report_summary_dict

    return jsonify(report_summary_dict())


@app.route("/api/cache/clear", methods=["POST", "GET"])
def api_cache_clear():
    """Clear fixture disk cache and in-memory /api/health cache. GET is for local dev only."""
    all_disk = request.args.get("all") == "1"
    if request.method == "POST" and request.is_json:
        body = request.get_json(silent=True) or {}
        if isinstance(body, dict) and body.get("all"):
            all_disk = True
    cleared = clear_application_caches(all_disk=all_disk)
    return jsonify({"cleared": cleared, "all_disk": all_disk})


@app.route("/api/health")
def api_health():
    """API + scraper probes for dashboard status panel (short TTL cache)."""
    import time as _time

    now = _time.monotonic()
    if _health_cache["payload"] is not None and (now - float(_health_cache["t"])) < _HEALTH_TTL_SEC:
        return jsonify(_health_cache["payload"])
    from hibs_predictor.health_quality_narrative import augment_health_for_ui

    payload = augment_health_for_ui(gather_health())
    _health_cache["t"] = now
    _health_cache["payload"] = payload
    return jsonify(payload)


@app.route("/api/fixtures/live")
def api_fixtures_live():
    """Lightweight in-play score poll for dashboard rows (cached live=all + optional events)."""
    from hibs_predictor.live_scores import live_payload_for_ids

    raw_ids = (request.args.get("ids") or "").strip()
    fixture_ids: List[int] = []
    for part in raw_ids.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            fixture_ids.append(int(part))
        except ValueError:
            continue
    if not fixture_ids:
        data = fetch_all_fixtures()
        from hibs_predictor.live_scores import fixture_ids_likely_in_play

        fixture_ids = fixture_ids_likely_in_play(data.get("all") or [])
    include_stats = request.args.get("stats", "1") != "0"
    return jsonify(
        live_payload_for_ids(
            aggregator,
            fixture_ids,
            include_events=True,
            include_stats=include_stats,
        )
    )


@app.route("/api/fixtures")
def api_fixtures():
    league_code = request.args.get("league", "EPL")
    fixtures = fetch_next_48h_fixtures(league_code)
    return jsonify({"fixtures": fixtures, "count": len(fixtures)})


@app.route("/api/value-bets")
def api_value_bets():
    data = fetch_all_fixtures()
    return jsonify({"value_bets": data["value_bets"], "count": data["value_bet_count"]})


@app.route("/api/insights")
def api_insights():
    """Handicapper-style insight digest for the current fixture window."""
    from hibs_predictor.insights import build_insights

    data = fetch_all_fixtures()
    return jsonify(build_insights(data["all"]))


@app.route("/insights")
def insights_page():
    """Actionable model/data/market insights built from the current fixture packets."""
    from hibs_predictor.insights import build_insights

    data = fetch_all_fixtures()
    insights = build_insights(data["all"])
    assistant_bundle = _assistant_bundle(data["all"])
    return render_template(
        "insights.html",
        insights=insights,
        total=data["total"],
        fetch_days=data.get("fetch_days", _fetch_window_days()),
        value_bet_count=data["value_bet_count"],
        data_quality_ui_min=_ui_data_quality_min_pct(),
        assistant_packets=assistant_bundle["packets"],
        assistant_recommendations=assistant_bundle.get("recommendations"),
        display_tz_label=display_tz_label(),
    )


@app.route("/tables")
def tables_page():
    """League tables from available standings feeds, with fixture-row fallback."""
    data = fetch_all_fixtures()
    tables = _build_league_tables(data["all"], include_live=True)
    return render_template(
        "tables.html",
        tables=tables,
        total=data["total"],
        fetch_days=data.get("fetch_days", _fetch_window_days()),
        display_tz_label=display_tz_label(),
    )


@app.route("/guide")
def guide_page():
    """Standalone betting guide so the nav has no dead Guide item."""
    return render_template("guide.html")


@app.route("/settings")
def settings_page():
    """Front-end preferences persisted in localStorage by the settings template."""
    return render_template(
        "settings.html",
        data_quality_ui_min=_ui_data_quality_min_pct(),
        fetch_days=_fetch_window_days(),
        allowed_fetch_days=_ALLOWED_FETCH_DAYS,
    )


@app.route("/acca")
def acca_builder():
    data = fetch_all_fixtures()
    return render_template("acca_builder.html", fixtures=data["all"])


@app.route("/status")
def api_status_page():
    """Dedicated API + scraper status (same probes as /api/health)."""
    return render_template("api_status.html")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    print("\n\U0001f7e2\U0001f49a hibs-bet \u2014 Starting...")
    print(f"   Open http://127.0.0.1:{port}\n")
    # threaded=True: first dashboard load can take a long time (fixtures + enrichment);
    # without threads the dev server would ignore other tabs/requests until that finishes.
    app.run(debug=False, port=port, host="127.0.0.1", threaded=True, use_reloader=False)
