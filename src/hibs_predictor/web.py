"""Flask web dashboard for Hibs betting predictor."""

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

# Add src directory to Python path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

from flask import Flask, render_template, jsonify, request
from hibs_predictor.api_clients import ApiSportsFootballClient
from hibs_predictor.config import LEAGUES, HIBS_LEAGUE_FOCUS
from hibs_predictor.cache import Cache
from hibs_predictor.data_aggregator import DataAggregator
from hibs_predictor.betting_engine import BettingEngine, OddsAnalyzer

# Get absolute paths for templates and static files
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
app.config["JSON_SORT_KEYS"] = False

# Global instances
aggregator = DataAggregator()
betting_engine = BettingEngine(aggregator.get_all_clients())


def _is_upcoming(date_obj: datetime, now: datetime, cutoff: datetime) -> bool:
    return now <= date_obj <= cutoff


def _fixture_key(fixture: Dict[str, Any]) -> str:
    home = fixture.get("home", {}).get("name") or fixture.get("teams", {}).get("home", {}).get("name", "")
    away = fixture.get("away", {}).get("name") or fixture.get("teams", {}).get("away", {}).get("name", "")
    date = fixture.get("date", "")
    return f"{home}|{away}|{date}"


def _normalize_api_sports_fixture(fixture: Dict[str, Any], league_code: str) -> Optional[Dict[str, Any]]:
    fixture_meta = fixture.get("fixture", {})
    home = fixture.get("teams", {}).get("home", {})
    away = fixture.get("teams", {}).get("away", {})

    if not fixture_meta or not home or not away:
        return None

    return {
        "fixture": {
            "id": fixture_meta.get("id"),
            "date": fixture_meta.get("date"),
            "status": fixture_meta.get("status", {}),
        },
        "teams": {
            "home": {"id": home.get("id", 0), "name": home.get("name", "?")},
            "away": {"id": away.get("id", 0), "name": away.get("name", "?")},
        },
        "home": {"id": home.get("id", 0), "name": home.get("name", "?")},
        "away": {"id": away.get("id", 0), "name": away.get("name", "?")},
        "date": fixture_meta.get("date"),
        "league": league_code,
        "league_name": LEAGUES.get(league_code, {}).get("name", ""),
    }


def _normalize_football_data_org_match(match: Dict[str, Any], league_code: str) -> Optional[Dict[str, Any]]:
    if not match:
        return None

    home = match.get("homeTeam", {}) or {}
    away = match.get("awayTeam", {}) or {}
    date = match.get("utcDate")
    status = match.get("status", "")

    if not date or not home or not away:
        return None

    return {
        "fixture": {
            "id": match.get("id"),
            "date": date,
            "status": {"short": status},
        },
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


def _normalize_sportsmonk_fixture(fixture: Dict[str, Any], league_code: str) -> Optional[Dict[str, Any]]:
    if not fixture:
        return None

    date = fixture.get("time") or fixture.get("date")
    local_team = fixture.get("localTeam", {}).get("data", {})
    visitor_team = fixture.get("visitorTeam", {}).get("data", {})

    if not date or not local_team or not visitor_team:
        return None

    return {
        "fixture": {
            "id": fixture.get("id"),
            "date": date,
            "status": {"short": fixture.get("time_status", "NS")},
        },
        "teams": {
            "home": {"id": local_team.get("id", 0), "name": local_team.get("name", "?")},
            "away": {"id": visitor_team.get("id", 0), "name": visitor_team.get("name", "?")},
        },
        "home": {"id": local_team.get("id", 0), "name": local_team.get("name", "?")},
        "away": {"id": visitor_team.get("id", 0), "name": visitor_team.get("name", "?")},
        "date": date,
        "league": league_code,
        "league_name": LEAGUES.get(league_code, {}).get("name", ""),
    }


def fetch_next_48h_fixtures(league_code: str = "EPL") -> List[Dict[str, Any]]:
    cache = Cache()
    cache_key = f"next_48h_fixtures_{league_code}"
    cached = cache.get(cache_key, ttl_hours=1)
    if cached:
        return cached

    league = LEAGUES.get(league_code, {})
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=48)
    fetched: Dict[str, Dict[str, Any]] = {}

    def add_fixture(candidate: Dict[str, Any]) -> None:
        key = _fixture_key(candidate)
        if key and key not in fetched:
            fetched[key] = candidate

    if "api_sports" in aggregator.clients:
        try:
            season_candidates = [now.year, now.year + 1, now.year - 1, now.year - 2]
            for season in season_candidates:
                raw_fixtures = aggregator.clients["api_sports"].fetch_fixtures_by_league(
                    league.get("api_sports_id", 39), season, status=None
                )
                if not raw_fixtures:
                    continue

                for fixture in raw_fixtures:
                    normalized = _normalize_api_sports_fixture(fixture, league_code)
                    if not normalized:
                        continue

                    fixture_date_str = normalized.get("date")
                    try:
                        fixture_date = datetime.fromisoformat(fixture_date_str.replace("Z", "+00:00"))
                        if _is_upcoming(fixture_date, now, cutoff):
                            normalized["date"] = fixture_date.isoformat()
                            add_fixture(normalized)
                    except Exception:
                        continue
        except Exception as e:
            print(f"API-Sports error for {league_code}: {e}")
            pass

    if "football_data_org" in aggregator.clients:
        seasons_to_try = [now.year - 1, now.year, now.year + 1]
        competition_code = league.get("football_data_org_id")
        for season in seasons_to_try:
            if not competition_code:
                continue
            try:
                raw_matches = aggregator.clients["football_data_org"].fetch_fixtures(
                    competition_code,
                    season,
                    status="SCHEDULED",
                )
            except Exception as e:
                print(f"Football Data Org season {season} failed for {league_code}: {e}")
                continue

            if not raw_matches:
                continue

            for match in raw_matches:
                normalized = _normalize_football_data_org_match(match, league_code)
                if not normalized:
                    continue

                fixture_date_str = normalized.get("date")
                try:
                    fixture_date = datetime.fromisoformat(fixture_date_str.replace("Z", "+00:00"))
                    if _is_upcoming(fixture_date, now, cutoff):
                        normalized["date"] = fixture_date.isoformat()
                        add_fixture(normalized)
                except Exception:
                    continue
            if fetched:
                break

    if "sportsmonk" in aggregator.clients:
        league_id = league.get("sportsmonk_id")
        seasons_to_try = [now.year - 1, now.year, now.year + 1]
        for season in seasons_to_try:
            if not league_id:
                continue
            try:
                raw_fixtures = aggregator.clients["sportsmonk"].fetch_fixtures(league_id, season)
            except Exception as e:
                print(f"SportsMonk season {season} failed for {league_code}: {e}")
                continue

            if not raw_fixtures:
                continue

            for fixture in raw_fixtures:
                normalized = _normalize_sportsmonk_fixture(fixture, league_code)
                if not normalized:
                    continue

                fixture_date_str = normalized.get("date")
                try:
                    fixture_date = datetime.fromisoformat(fixture_date_str.replace("Z", "+00:00"))
                    if _is_upcoming(fixture_date, now, cutoff):
                        normalized["date"] = fixture_date.isoformat()
                        add_fixture(normalized)
                except Exception:
                    continue
            if fetched:
                break

    fixtures: List[Dict[str, Any]] = []
    if not fetched:
        print(f"No fixtures found for {league_code}, creating sample fixtures...")
        fixtures = create_sample_fixtures(league_code)
    else:
        for fixture in fetched.values():
            enriched = aggregator.enrich_fixture(fixture, league_code)
            prediction = betting_engine.predict_with_confidence(enriched)
            fixtures.append({
                "id": fixture.get("fixture", {}).get("id") or fixture.get("id"),
                "home": fixture.get("home", {}).get("name", "?"),
                "away": fixture.get("away", {}).get("name", "?"),
                "date": fixture.get("date"),
                "league": league_code,
                "league_name": fixture.get("league_name", league.get("name", "")),
                "prediction": prediction,
            })

    fixtures.sort(key=lambda x: x["date"])
    cache.set(cache_key, fixtures)
    return fixtures


def create_sample_fixtures(league_code: str) -> List[Dict[str, Any]]:
    """Create sample fixtures for demo purposes when API has no data."""
    league = LEAGUES.get(league_code, {})
    now = datetime.now()
    
    # Create fixtures for next few days
    sample_teams = {
        "EPL": [
            ("Arsenal", "Chelsea"), ("Liverpool", "Manchester City"), ("Manchester United", "Tottenham"),
            ("Newcastle", "Brighton"), ("Aston Villa", "West Ham"), ("Fulham", "Crystal Palace")
        ],
        "SCOTLAND": [
            ("Rangers", "Celtic"), ("Hibernian", "Hearts"), ("Aberdeen", "Dundee United"),
            ("St Johnstone", "Ross County"), ("Livingston", "St Mirren")
        ],
        "CHAMPIONSHIP": [
            ("Leeds", "Ipswich"), ("Leicester", "Southampton"), ("Norwich", "Watford"),
            ("Middlesbrough", "Coventry"), ("Sunderland", "Blackburn")
        ]
    }
    
    teams = sample_teams.get(league_code, sample_teams["EPL"])
    fixtures = []
    
    for i, (home, away) in enumerate(teams):
        fixture_date = now + timedelta(hours=6 + i * 12)  # Spread over next 48 hours
        
        # Create mock enriched data
        enriched = {
            "fixture_id": f"sample_{i}",
            "home_team": home,
            "away_team": away,
            "league": league_code,
            "home_strength": 0.6 + (i % 3) * 0.1,
            "away_strength": 0.5 + ((i + 1) % 3) * 0.1,
            "home_form": 0.55 + (i % 2) * 0.1,
            "away_form": 0.52 + ((i + 1) % 2) * 0.1,
            "odds_home": 2.1 + (i % 2) * 0.3,
            "odds_draw": 3.4 + (i % 2) * 0.2,
            "odds_away": 3.2 + ((i + 1) % 2) * 0.3,
        }
        
        prediction = betting_engine.predict_with_confidence(enriched)
        
        fixtures.append({
            "id": f"sample_{league_code}_{i}",
            "home": home,
            "away": away,
            "date": fixture_date.isoformat(),
            "league": league_code,
            "league_name": league.get("name", league_code),
            "prediction": prediction,
            "is_sample": True  # Mark as sample data
        })
    
    return fixtures


@app.route("/")
def index() -> str:
    fixtures_by_league = {}
    for league_code in HIBS_LEAGUE_FOCUS:
        fixtures_by_league[league_code] = fetch_next_48h_fixtures(league_code)
    
    all_fixtures = []
    for league_code, fixtures in fixtures_by_league.items():
        all_fixtures.extend(fixtures)
    
    all_fixtures.sort(key=lambda x: x["date"])
    return render_template("dashboard.html", fixtures=all_fixtures)


@app.route("/api/fixtures")
def api_fixtures() -> Dict[str, Any]:
    league_code = request.args.get("league", "EPL")
    fixtures = fetch_next_48h_fixtures(league_code)
    return {"fixtures": fixtures}


@app.route("/api/prediction/<int:fixture_id>")
def api_prediction(fixture_id: int) -> Dict[str, Any]:
    try:
        if "api_sports" not in aggregator.clients:
            return {"error": "API client not available"}, 400
        
        fixture = aggregator.clients["api_sports"].fetch_fixture(fixture_id)
        enriched = aggregator.enrich_fixture(fixture)
        prediction = betting_engine.predict_with_confidence(enriched)
        return prediction
    except Exception as e:
        return {"error": str(e)}, 500


@app.route("/acca")
def acca_builder() -> str:
    """Dedicated acca builder page with quick-add interface."""
    all_fixtures = []
    for league_code in HIBS_LEAGUE_FOCUS:
        all_fixtures.extend(fetch_next_48h_fixtures(league_code))
    
    all_fixtures.sort(key=lambda x: x["date"])
    return render_template("acca_builder.html", fixtures=all_fixtures)


@app.route("/api/place-bet", methods=["POST"])
def place_bet() -> Dict[str, Any]:
    """Handle bet placement via API.
    
    Expected JSON payload:
    {
        "selections": [
            {"fixture_id": 123, "outcome": "home", "odds": 1.50},
            ...
        ],
        "stake": 10.00,
        "affiliate": "william_hill" or "ladbrokes"
    }
    """
    try:
        data = request.get_json()
        
        if not data or "selections" not in data:
            return {"error": "Missing selections"}, 400
        
        selections = data.get("selections", [])
        stake = float(data.get("stake", 0))
        affiliate = data.get("affiliate", "william_hill")
        
        if not selections or stake <= 0:
            return {"error": "Invalid bet data"}, 400
        
        # Calculate total odds
        total_odds = 1.0
        for sel in selections:
            total_odds *= float(sel.get("odds", 1.0))
        
        potential_returns = stake * total_odds
        
        # Generate affiliate URL
        affiliate_url = _generate_affiliate_url(
            affiliate, 
            selections, 
            stake, 
            total_odds, 
            potential_returns
        )
        
        return {
            "status": "success",
            "bet_id": f"BET_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "selections": selections,
            "stake": stake,
            "total_odds": total_odds,
            "potential_returns": potential_returns,
            "affiliate_url": affiliate_url,
            "timestamp": datetime.now().isoformat(),
        }, 200
    
    except Exception as e:
        return {"error": str(e)}, 500


def _generate_affiliate_url(
    affiliate: str, 
    selections: List[Dict],
    stake: float,
    total_odds: float,
    returns: float
) -> str:
    """Generate affiliate URL for William Hill or Ladbrokes."""
    import base64
    import urllib.parse
    
    # Build bet slip data
    bet_data = {
        "selections": len(selections),
        "stake": f"£{stake:.2f}",
        "odds": f"{total_odds:.2f}",
        "returns": f"£{returns:.2f}",
        "type": "acca",
    }
    
    if affiliate == "ladbrokes":
        # Ladbrokes affiliate URL
        base_url = "https://www.ladbrokes.com"
        bet_slip = urllib.parse.urlencode(bet_data)
        return f"{base_url}/?affiliate=hibsbetting&{bet_slip}"
    else:
        # William Hill affiliate URL (default)
        base_url = "https://www.williamhill.com"
        bet_slip = urllib.parse.urlencode(bet_data)
        return f"{base_url}/?ref=hibsbetting&{bet_slip}"


if __name__ == "__main__":
    app.run(debug=True, port=int(os.getenv("PORT", "5000")))
