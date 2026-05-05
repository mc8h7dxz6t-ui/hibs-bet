"""Flask web dashboard for hibs.bet."""

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

from flask import Flask, render_template, jsonify, request
from hibs_predictor.config import LEAGUES, ALL_LEAGUE_CODES, LEAGUE_REGIONS
from hibs_predictor.cache import Cache
from hibs_predictor.data_aggregator import DataAggregator
from hibs_predictor.betting_engine import BettingEngine, OddsAnalyzer, TeamStrengthCalculator

TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
app.config["JSON_SORT_KEYS"] = False

aggregator = DataAggregator()
betting_engine = BettingEngine(aggregator.get_all_clients())


def _fixture_key(fixture: Dict[str, Any]) -> str:
    home = fixture.get("home", {}).get("name") or fixture.get("teams", {}).get("home", {}).get("name", "")
    away = fixture.get("away", {}).get("name") or fixture.get("teams", {}).get("away", {}).get("name", "")
    return f"{home}|{away}|{fixture.get('date', '')}"


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
    cache = Cache()
    cached = cache.get(f"next_48h_{league_code}", ttl_hours=1)
    if cached:
        return cached

    league = LEAGUES.get(league_code, {})
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=48)
    fetched: Dict[str, Dict] = {}

    def add(candidate: Dict) -> None:
        key = _fixture_key(candidate)
        if key and key not in fetched:
            fetched[key] = candidate

    if "api_sports" in aggregator.clients:
        try:
            for season in [now.year, now.year - 1]:
                raw = aggregator.clients["api_sports"].fetch_fixtures_by_league(
                    league.get("api_sports_id", 39), season
                )
                for f in raw or []:
                    norm = _normalize_api_sports(f, league_code)
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
        except Exception as e:
            print(f"[API-Sports] {league_code}: {e}")

    if not fetched and "football_data_org" in aggregator.clients:
        comp = league.get("football_data_org_id")
        if comp:
            # Only try current season - avoid hammering the rate limit
            for season in [now.year - 1, now.year]:
                try:
                    import time as _time
                    _time.sleep(0.5)  # respect rate limit
                    raw = aggregator.clients["football_data_org"].fetch_fixtures(comp, season, status="SCHEDULED")
                    for m in raw or []:
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
                except Exception:
                    break  # stop retrying on any error to avoid rate limit cascade

    fixtures = []
    for fixture in fetched.values():
        try:
            enriched = aggregator.enrich_fixture(fixture, league_code)
            prediction = betting_engine.predict_with_confidence(enriched)
            home_id = fixture.get("teams", {}).get("home", {}).get("id")
            away_id = fixture.get("teams", {}).get("away", {}).get("id")
            home_last10 = TeamStrengthCalculator.parse_last_10_results(enriched.get("home_recent", []), home_id)
            away_last10 = TeamStrengthCalculator.parse_last_10_results(enriched.get("away_recent", []), away_id)
            fixtures.append({
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
                "has_value_bet": bool(prediction.get("value_bets")),
            })
        except Exception as e:
            print(f"[Enrich] {league_code}: {e}")

    fixtures.sort(key=lambda x: x.get("date") or "")
    cache.set(f"next_48h_{league_code}", fixtures)
    return fixtures


def fetch_all_fixtures() -> Dict:
    cache = Cache()
    cached = cache.get("all_fixtures_grouped", ttl_hours=1)
    if cached:
        return cached

    all_fixtures = []
    by_region: Dict[str, List] = {r: [] for r in LEAGUE_REGIONS}
    value_bets_only = []

    for league_code in ALL_LEAGUE_CODES:
        try:
            fixtures = fetch_next_48h_fixtures(league_code)
            all_fixtures.extend(fixtures)
            for region, codes in LEAGUE_REGIONS.items():
                if league_code in codes:
                    by_region[region].extend(fixtures)
            for f in fixtures:
                if f.get("has_value_bet"):
                    value_bets_only.append(f)
        except Exception as e:
            print(f"[AllFixtures] {league_code}: {e}")

    all_fixtures.sort(key=lambda x: x.get("date") or "")
    value_bets_only.sort(key=lambda x: -(x.get("prediction", {}).get("best_bet_roi") or 0))

    result = {
        "all": all_fixtures,
        "by_region": by_region,
        "value_bets": value_bets_only,
        "total": len(all_fixtures),
        "value_bet_count": len(value_bets_only),
    }
    cache.set("all_fixtures_grouped", result)
    return result


@app.route("/")
def index():
    data = fetch_all_fixtures()
    return render_template(
        "dashboard.html",
        all_fixtures=data["all"],
        by_region=data["by_region"],
        value_bets=data["value_bets"],
        total=data["total"],
        value_bet_count=data["value_bet_count"],
        league_regions=LEAGUE_REGIONS,
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


@app.route("/acca")
def acca_builder():
    data = fetch_all_fixtures()
    return render_template("acca_builder.html", fixtures=data["all"])


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    print("\n\U0001f7e2\U0001f49a hibs.bet \u2014 Starting...")
    print(f"   Open http://127.0.0.1:{port}\n")
    app.run(debug=False, port=port, host="127.0.0.1")
