"""Flask web dashboard for hibs.bet."""

import os
import sys
from datetime import datetime, timedelta, timezone, date
from typing import Any, Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

from flask import Flask, render_template, jsonify, request, abort
from hibs_predictor.config import LEAGUES, ALL_LEAGUE_CODES, LEAGUE_REGIONS, DASHBOARD_LEAGUE_ORDER
from hibs_predictor.cache import Cache
from hibs_predictor.data_aggregator import DataAggregator
from hibs_predictor.betting_engine import BettingEngine, OddsAnalyzer, TeamStrengthCalculator
from hibs_predictor.health_probe import gather_health

TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
app.config["JSON_SORT_KEYS"] = False

aggregator = DataAggregator()
betting_engine = BettingEngine(aggregator.get_all_clients())

_health_cache: Dict[str, Any] = {"t": 0.0, "payload": None}
_HEALTH_TTL_SEC = 90.0


def _api_football_season_year(now: datetime) -> int:
    """API-Football season id is the year the competition season starts (e.g. 2025 for 2025–26)."""
    return now.year if now.month >= 7 else now.year - 1


def _fixture_key(fixture: Dict[str, Any]) -> str:
    home = fixture.get("home", {}).get("name") or fixture.get("teams", {}).get("home", {}).get("name", "")
    away = fixture.get("away", {}).get("name") or fixture.get("teams", {}).get("away", {}).get("name", "")
    return f"{home}|{away}|{fixture.get('date', '')}"


def _fetch_window_days() -> int:
    try:
        d = int(os.getenv("HIBS_FETCH_DAYS", "4"))
    except ValueError:
        d = 4
    return max(1, min(14, d))


def _min_league_chip_fixtures() -> int:
    """Leagues with fewer upcoming fixtures in the window are hidden from filter chips (still in All)."""
    try:
        n = int(os.getenv("HIBS_MIN_LEAGUE_CHIP_FIXTURES", "2"))
    except ValueError:
        n = 2
    return max(1, min(20, n))


def _ui_data_quality_min_pct() -> int:
    try:
        return max(50, min(100, int(os.getenv("HIBS_UI_FULL_DATA_MIN_PCT", "85"))))
    except ValueError:
        return 85


def _all_fixtures_cache_key() -> str:
    return f"all_fixtures_{_fetch_window_days()}d_v8"


def _safe_enrich(fixture: Dict[str, Any], league_code: str) -> Dict[str, Any]:
    """Prefer full enrichment; on failure return a minimal shape so the fixture still lists."""
    try:
        return aggregator.enrich_fixture(fixture, league_code)
    except Exception as exc:
        print(f"[Enrich fallback] {league_code} {_fixture_key(fixture)}: {exc}")
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
    cache_key = f"fixtures_{days}d_{league_code}"
    cached = cache.get(cache_key, ttl_hours=1)
    if cached:
        return cached

    league = LEAGUES.get(league_code, {})
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days)
    fetched: Dict[str, Dict] = {}
    date_from = now.strftime("%Y-%m-%d")
    date_to = cutoff.strftime("%Y-%m-%d")
    season_primary = _api_football_season_year(now)

    def add(candidate: Dict) -> None:
        key = _fixture_key(candidate)
        if key and key not in fetched:
            fetched[key] = candidate

    league_api_id = league.get("api_sports_id")
    if "api_sports" in aggregator.clients and league_api_id:
        try:
            for season in [season_primary, season_primary - 1]:
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

    if not fetched and "football_data_org" in aggregator.clients:
        comp = league.get("football_data_org_id")
        if comp:
            for season in [season_primary, season_primary - 1]:
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
                    print(f"[Football-Data.org] {league_code} {comp}: {ex!r}")
                    break

    fixtures = []
    for fixture in fetched.values():
        try:
            enriched = _safe_enrich(fixture, league_code)
            prediction = betting_engine.predict_with_confidence(enriched)
            home_id = fixture.get("teams", {}).get("home", {}).get("id")
            away_id = fixture.get("teams", {}).get("away", {}).get("id")
            home_last10 = TeamStrengthCalculator.parse_last_10_results(enriched.get("home_recent", []), home_id)
            away_last10 = TeamStrengthCalculator.parse_last_10_results(enriched.get("away_recent", []), away_id)
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
        except Exception as e:
            print(f"[Fixture build] {league_code}: {e}")

    fixtures.sort(key=lambda x: x.get("date") or "")
    cache.set(cache_key, fixtures, ttl_hours=1)
    return fixtures


def fetch_all_fixtures() -> Dict:
    cache = Cache()
    ck = _all_fixtures_cache_key()
    cached = cache.get(ck, ttl_hours=1)
    if cached:
        return cached

    all_fixtures: List[Dict] = []
    by_region: Dict[str, List] = {r: [] for r in LEAGUE_REGIONS}
    value_bets_only: List[Dict] = []
    fixtures_by_league: Dict[str, List] = {c: [] for c in DASHBOARD_LEAGUE_ORDER}

    for league_code in ALL_LEAGUE_CODES:
        try:
            fixtures = fetch_next_48h_fixtures(league_code)
            all_fixtures.extend(fixtures)
            if league_code in fixtures_by_league:
                fixtures_by_league[league_code].extend(fixtures)
            for region, codes in LEAGUE_REGIONS.items():
                if league_code in codes:
                    by_region[region].extend(fixtures)
            for f in fixtures:
                if f.get("has_value_bet"):
                    value_bets_only.append(f)
        except Exception as e:
            print(f"[AllFixtures] {league_code}: {e}")

    for c in fixtures_by_league:
        fixtures_by_league[c].sort(key=lambda x: x.get("date") or "")

    all_fixtures.sort(key=lambda x: x.get("date") or "")
    value_bets_only.sort(key=lambda x: -(x.get("prediction", {}).get("best_bet_roi") or 0))

    result = {
        "all": all_fixtures,
        "by_region": by_region,
        "by_league": fixtures_by_league,
        "dashboard_days": _dashboard_days_groups(all_fixtures),
        "value_bets": value_bets_only,
        "total": len(all_fixtures),
        "value_bet_count": len(value_bets_only),
        "fetch_days": _fetch_window_days(),
        "has_api_clients": bool(aggregator.clients),
    }
    cache.set(ck, result, ttl_hours=1)
    return result


def _dashboard_days_groups(all_fixtures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group fixtures by calendar day, then by league (dashboard order)."""
    from collections import defaultdict

    by_day: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for f in all_fixtures:
        raw = f.get("date") or ""
        if len(raw) < 10:
            continue
        day_iso = raw[:10]
        lc = f.get("league") or ""
        if lc:
            by_day[day_iso][lc].append(f)
    today_utc = datetime.now(timezone.utc).date()
    out: List[Dict[str, Any]] = []
    for day_iso in sorted(by_day.keys()):
        leagues_block: List[Dict[str, Any]] = []
        for lc in DASHBOARD_LEAGUE_ORDER:
            fl = by_day[day_iso].get(lc, [])
            if fl:
                fl.sort(key=lambda x: x.get("date") or "")
                leagues_block.append(
                    {
                        "code": lc,
                        "name": LEAGUES.get(lc, {}).get("name", lc),
                        "fixtures": fl,
                    }
                )
        if not leagues_block:
            continue
        try:
            d = date.fromisoformat(day_iso)
        except ValueError:
            heading = day_iso
        else:
            day_mon = f"{d.day} {d.strftime('%b')}"
            if d == today_utc:
                heading = f"Today • {day_mon}"
            elif d == today_utc + timedelta(days=1):
                heading = f"Tomorrow • {day_mon}"
            else:
                heading = f"{d.strftime('%a')} • {day_mon}"
        out.append({"date_iso": day_iso, "heading": heading, "leagues": leagues_block})
    return out


def _leagues_for_filter(by_league: Dict[str, List]) -> List[tuple]:
    """League chips only for competitions with enough upcoming games for stable model inputs."""
    order_index = {c: i for i, c in enumerate(DASHBOARD_LEAGUE_ORDER)}
    min_n = _min_league_chip_fixtures()
    codes = [
        c
        for c in ALL_LEAGUE_CODES
        if c in LEAGUES and len(by_league.get(c) or []) >= min_n
    ]
    pairs = [(c, LEAGUES[c].get("name", c)) for c in codes]
    return sorted(pairs, key=lambda x: (order_index.get(x[0], 999), x[1].lower()))


@app.route("/")
def index():
    data = fetch_all_fixtures()
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
        has_api_clients=data.get("has_api_clients", bool(aggregator.clients)),
        leagues=LEAGUES,
        data_quality_ui_min=_ui_data_quality_min_pct(),
    )


@app.route("/api/audit/summary")
def api_audit_summary():
    """Calibration / audit metrics from the prediction log SQLite (optional)."""
    tok = (os.getenv("HIBS_AUDIT_API_TOKEN") or "").strip()
    if not tok or request.args.get("token", "") != tok:
        abort(404)
    from hibs_predictor.prediction_log import report_summary_dict

    return jsonify(report_summary_dict())


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
    print("\n\U0001f7e2\U0001f49a hibs.bet \u2014 Starting...")
    print(f"   Open http://127.0.0.1:{port}\n")
    app.run(debug=False, port=port, host="127.0.0.1")
