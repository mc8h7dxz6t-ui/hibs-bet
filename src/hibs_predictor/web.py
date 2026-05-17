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

from flask import Flask, render_template, jsonify, request, abort
from hibs_predictor.config import LEAGUES, ALL_LEAGUE_CODES, LEAGUE_REGIONS, DASHBOARD_LEAGUE_ORDER
from hibs_predictor.cache import Cache
from hibs_predictor.data_aggregator import DataAggregator
from hibs_predictor.betting_engine import (
    BettingEngine,
    OddsAnalyzer,
    TeamStrengthCalculator,
    prediction_unavailable_payload,
)
from hibs_predictor.health_probe import gather_health
from hibs_predictor.display_tz import display_tz_label

TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
app.config["JSON_SORT_KEYS"] = False

aggregator = DataAggregator()
betting_engine = BettingEngine(aggregator.get_all_clients())

_health_cache: Dict[str, Any] = {"t": 0.0, "payload": None}
_HEALTH_TTL_SEC = 90.0
_cache_prune_last: float = 0.0
_CACHE_PRUNE_INTERVAL_SEC = 300.0


def _api_football_season_year(now: datetime) -> int:
    """API-Football season id is the year the competition season starts (e.g. 2025 for 2025–26)."""
    return now.year if now.month >= 7 else now.year - 1


_FDO_CALENDAR_COMPS = frozenset({"WC", "EC", "UNL"})


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
        return [primary, primary - 1]
    window_years = _years_touched_by_date_range(date_from_s, date_to_s)
    merged = set(window_years) | {primary, primary - 1}
    out: List[int] = []
    seen: set[int] = set()
    for y in sorted(window_years, reverse=True):
        if y in merged and y not in seen:
            out.append(y)
            seen.add(y)
    for y in (primary, primary - 1):
        if y in merged and y not in seen:
            out.append(y)
            seen.add(y)
    for y in sorted(merged - seen, reverse=True):
        out.append(y)
    return out


def _env_truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def _fixture_key(fixture: Dict[str, Any]) -> str:
    home = fixture.get("home", {}).get("name") or fixture.get("teams", {}).get("home", {}).get("name", "")
    away = fixture.get("away", {}).get("name") or fixture.get("teams", {}).get("away", {}).get("name", "")
    return f"{home}|{away}|{fixture.get('date', '')}"


def _fetch_window_days() -> int:
    try:
        d = int(os.getenv("HIBS_FETCH_DAYS", "5"))
    except ValueError:
        d = 5
    return max(1, min(14, d))


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
    return f"all_fixtures_{_fetch_window_days()}d_v14"


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


def _normalize_api_sports(fixture: Dict, league_code: str) -> Optional[Dict]:
    fm = fixture.get("fixture", {})
    home = fixture.get("teams", {}).get("home", {})
    away = fixture.get("teams", {}).get("away", {})
    if not fm or not home or not away:
        return None
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
        "league_name": LEAGUES.get(league_code, {}).get("name", ""),
    }


def _normalize_fdo(match: Dict, league_code: str) -> Optional[Dict]:
    if not match:
        return None
    home = match.get("homeTeam", {}) or {}
    away = match.get("awayTeam", {}) or {}
    date = match.get("utcDate")
    if not date or not home or not away:
        return None
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
        "league_name": LEAGUES.get(league_code, {}).get("name", ""),
    }


def fetch_next_48h_fixtures(league_code: str) -> List[Dict]:
    days = _fetch_window_days()
    cache = Cache()
    prefer_fdo = _env_truthy("HIBS_PREFER_FOOTBALL_DATA_FIXTURES")
    skip_as_fx = _env_truthy("HIBS_SKIP_API_SPORTS_FIXTURES")
    ttl = _cache_ttl_hours(1.0)
    cache_key = f"fixtures_{days}d_{league_code}_v14_{int(prefer_fdo)}{int(skip_as_fx)}"
    cached = cache.get(cache_key, ttl_hours=ttl)
    if cached:
        return cached

    league = LEAGUES.get(league_code, {})
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days)
    fetched: Dict[str, Dict] = {}
    date_from = now.strftime("%Y-%m-%d")
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
                        if now <= fd <= cutoff:
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
                    if st in ("FINISHED", "AWARDED", "CANCELLED", "POSTPONED", "ABANDONED", "SUSPENDED"):
                        continue
                    norm = _normalize_fdo(m, league_code)
                    if not norm:
                        continue
                    try:
                        fd = datetime.fromisoformat(norm["date"].replace("Z", "+00:00"))
                        if now <= fd <= cutoff:
                            norm["date"] = fd.isoformat()
                            add(norm)
                    except Exception:
                        continue
                if fetched:
                    break
            except Exception as ex:
                print(f"[Football-Data.org] {league_code} {comp} season={season}: {ex!r}")
                continue

    if prefer_fdo:
        try_football_data()
        if not fetched:
            try_api_sports()
    else:
        try_api_sports()
        if not fetched:
            try_football_data()

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

        fixtures.append(
            {
                "id": fixture.get("fixture", {}).get("id"),
                "home": fixture.get("home", {}).get("name", "?"),
                "away": fixture.get("away", {}).get("name", "?"),
                "home_id": home_id,
                "away_id": away_id,
                "date": fixture.get("date"),
                "league": league_code,
                "league_name": LEAGUES.get(league_code, {}).get("name", ""),
                "league_flag": LEAGUES.get(league_code, {}).get("flag", ""),
                "prediction": prediction,
                "home_last10": home_last10,
                "away_last10": away_last10,
                "home_position": enriched.get("home_position", {}),
                "away_position": enriched.get("away_position", {}),
                "all_bookmaker_odds": enriched.get("all_bookmaker_odds", []),
                "fixture_injuries": enriched.get("fixture_injuries", []),
                "data_quality": enriched.get("data_quality", {}),
                "xg_source": enriched.get("xg_source", "unknown"),
                "has_value_bet": bool(prediction.get("has_any_value", prediction.get("value_bets"))),
            }
        )

    fixtures.sort(key=lambda x: x.get("date") or "")
    cache.set(cache_key, fixtures, ttl_hours=ttl)
    return fixtures


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


def _finalize_fixture_bundle(all_fixtures: List[Dict[str, Any]]) -> Dict[str, Any]:
    from hibs_predictor.display_tz import enrich_fixtures_kickoff

    all_fixtures = enrich_fixtures_kickoff(all_fixtures)
    _ensure_fixture_pick_menus(all_fixtures)
    all_fixtures.sort(key=lambda x: x.get("kickoff_sort") or x.get("date") or "")
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
        return cached

    all_fixtures: List[Dict] = []

    for league_code in ALL_LEAGUE_CODES:
        try:
            all_fixtures.extend(fetch_next_48h_fixtures(league_code))
        except Exception as e:
            print(f"[AllFixtures] {league_code}: {e}")

    result = _finalize_fixture_bundle(all_fixtures)
    cache.set(ck, result, ttl_hours=ttl)
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
                "kickoff_time": f.get("kickoff_time") or "—",
                "kickoff_day_local": f.get("kickoff_day_local") or "",
            }
        )
        if len(rows) >= limit:
            break
    return rows


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
                    "name": LEAGUES.get(lc, {}).get("name", lc),
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
    return render_template(
        "dashboard.html",
        all_fixtures=data["all"],
        by_region=data["by_region"],
        by_league=data["by_league"],
        dashboard_days=data["dashboard_days"],
        value_bets=data["value_bets"],
        total=data["total"],
        value_bet_count=data["value_bet_count"],
        league_regions=LEAGUE_REGIONS,
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
