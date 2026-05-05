"""Data aggregator that enriches fixtures with multi-API data."""

import os
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta

from dotenv import load_dotenv

from hibs_predictor.api_clients import (
    ApiSportsFootballClient,
    FootballDataOrgClient,
    SportsMonkClient,
    OddsApiClient,
    StatsApiClient,
)
from hibs_predictor.betting_engine import TeamStrengthCalculator, OddsAnalyzer
from hibs_predictor.config import LEAGUES
from hibs_predictor.cache import Cache


class DataAggregator:
    """Aggregates data from multiple APIs to enrich fixture data."""

    def __init__(self) -> None:
        load_dotenv()
        self.cache = Cache()
        self.clients = self._initialize_clients()

    def _initialize_clients(self) -> Dict[str, Any]:
        clients = {}
        
        if os.getenv("API_SPORTS_FOOTBALL_KEY"):
            clients["api_sports"] = ApiSportsFootballClient(os.getenv("API_SPORTS_FOOTBALL_KEY", ""))
        
        if os.getenv("FOOTBALL_DATA_ORG_KEY"):
            clients["football_data_org"] = FootballDataOrgClient(os.getenv("FOOTBALL_DATA_ORG_KEY", ""))
        
        if os.getenv("SPORTSMONK_KEY"):
            clients["sportsmonk"] = SportsMonkClient(os.getenv("SPORTSMONK_KEY", ""))
        
        if os.getenv("ODDS_API_KEY"):
            clients["odds_api"] = OddsApiClient(os.getenv("ODDS_API_KEY", ""))
        
        if os.getenv("STATS_API_KEY"):
            clients["stats_api"] = StatsApiClient(os.getenv("STATS_API_KEY", ""))
        
        return clients

    def enrich_fixture(self, fixture: Dict[str, Any], league_code: str = "EPL") -> Dict[str, Any]:
        """Enrich a fixture with comprehensive data from multiple sources."""
        fixture_id = fixture.get("fixture", {}).get("id") or fixture.get("id", "")
        cache_key = f"enriched_fixture_{fixture_id}_{league_code}"
        cached = self.cache.get(cache_key, ttl_hours=2)
        if cached:
            return cached

        enriched = fixture.copy()
        league = LEAGUES.get(league_code, {})
        league_api_id = league.get("api_sports_id")
        season = datetime.now().year

        home_id = fixture.get("teams", {}).get("home", {}).get("id")
        away_id = fixture.get("teams", {}).get("away", {}).get("id")

        enriched["home_stats"] = self._fetch_team_stats(home_id, league_code, league_api_id, season)
        enriched["away_stats"] = self._fetch_team_stats(away_id, league_code, league_api_id, season)

        enriched["home_recent"] = self._fetch_team_recent_matches(home_id)
        enriched["away_recent"] = self._fetch_team_recent_matches(away_id)

        enriched["home_form"] = TeamStrengthCalculator.calculate_form_strength(enriched["home_recent"])
        enriched["away_form"] = TeamStrengthCalculator.calculate_form_strength(enriched["away_recent"])

        enriched["home_home_factor"] = TeamStrengthCalculator.calculate_home_away_factor(
            home_id, enriched["home_recent"], is_home=True
        )
        enriched["away_away_factor"] = TeamStrengthCalculator.calculate_home_away_factor(
            away_id, enriched["away_recent"], is_home=False
        )

        # League positions
        if league_api_id:
            enriched["home_position"] = self._fetch_team_position(home_id, league_api_id, season)
            enriched["away_position"] = self._fetch_team_position(away_id, league_api_id, season)
        else:
            enriched["home_position"] = {}
            enriched["away_position"] = {}

        enriched["xg_home"], enriched["xg_away"] = self._fetch_expected_goals(fixture_id)
        enriched["odds_home"], enriched["odds_draw"], enriched["odds_away"], enriched["all_bookmaker_odds"] = self._fetch_odds(fixture, league_code)
        enriched["league_factor"] = league.get("strength_factor", 1.0)

        self.cache.set(cache_key, enriched)
        return enriched

    def _fetch_team_stats(self, team_id: Optional[int], league_code: str, league_api_id: Optional[int] = None, season: int = None) -> Dict[str, Any]:
        """Fetch team statistics from available APIs."""
        if not team_id:
            return {"goals_for": 30, "goals_against": 25, "shots_on_target": 100}

        season = season or datetime.now().year
        cache_key = f"team_stats_{team_id}_{league_code}_{season}"
        cached = self.cache.get(cache_key, ttl_hours=12)
        if cached:
            return cached

        stats = {
            "goals_for": 30, "goals_against": 25,
            "shots_on_target": 100, "expected_goals": 28.0,
            "expected_goals_against": 24.0, "shots_on_target_against": 95,
        }

        if "api_sports" in self.clients:
            # Try current season then previous
            for s in [season, season - 1]:
                try:
                    team_stats = self.clients["api_sports"].fetch_team_statistics(team_id, s, league_api_id)
                    if team_stats:
                        goals = team_stats.get("goals", {})
                        shots = team_stats.get("shots", {})
                        fixtures = team_stats.get("fixtures", {})
                        stats.update({
                            "goals_for": goals.get("for", {}).get("total", {}).get("total", 30) or 30,
                            "goals_against": goals.get("against", {}).get("total", {}).get("total", 25) or 25,
                            "shots_on_target": shots.get("on", {}).get("total", 100) or 100,
                            "played": fixtures.get("played", {}).get("total", 0) or 0,
                            "wins": fixtures.get("wins", {}).get("total", 0) or 0,
                            "draws": fixtures.get("draws", {}).get("total", 0) or 0,
                            "losses": fixtures.get("loses", {}).get("total", 0) or 0,
                        })
                        if stats["goals_for"] > 0:
                            break
                except Exception:
                    continue

        self.cache.set(cache_key, stats)
        return stats

    def _fetch_team_position(self, team_id: Optional[int], league_api_id: int, season: int) -> Dict[str, Any]:
        """Fetch team's current league position."""
        if not team_id or not league_api_id:
            return {}
        try:
            if "api_sports" in self.clients:
                return self.clients["api_sports"].fetch_team_position(team_id, league_api_id, season)
        except Exception:
            pass
        return {}

    def _fetch_team_recent_matches(self, team_id: Optional[int], limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch team's last 10 matches from API-Sports."""
        if not team_id:
            return []

        cache_key = f"team_recent_{team_id}"
        cached = self.cache.get(cache_key, ttl_hours=4)
        if cached:
            return cached

        matches = []
        if "api_sports" in self.clients:
            try:
                matches = self.clients["api_sports"].fetch_team_last_matches(team_id, limit=limit)
            except Exception:
                pass

        self.cache.set(cache_key, matches)
        return matches

    def _fetch_expected_goals(self, fixture_id: Optional[int]) -> Tuple[float, float]:
        """Fetch expected goals from available APIs."""
        if not fixture_id:
            return 1.5, 1.2

        cache_key = f"xg_data_{fixture_id}"
        cached = self.cache.get(cache_key, ttl_hours=6)
        if cached:
            return cached

        xg_home, xg_away = 1.5, 1.2

        if "stats_api" in self.clients:
            try:
                xg_data = self.clients["stats_api"].fetch_xg_data(fixture_id)
                if xg_data.get("response"):
                    for stat in xg_data["response"]:
                        if stat.get("team", {}).get("name") == "Home":
                            xg_home = float(stat.get("statistics", [{}])[0].get("value", 1.5))
                        else:
                            xg_away = float(stat.get("statistics", [{}])[0].get("value", 1.2))
            except Exception:
                pass

        if "api_sports" in self.clients:
            try:
                fixture_data = self.clients["api_sports"].fetch_fixture(fixture_id)
                if fixture_data.get("statistics"):
                    stats = fixture_data["statistics"]
                    xg_home = float(stats[0].get("expected_goals", {}).get("value", 1.5)) if len(stats) > 0 else 1.5
                    xg_away = float(stats[1].get("expected_goals", {}).get("value", 1.2)) if len(stats) > 1 else 1.2
            except Exception:
                pass

        result = (xg_home, xg_away)
        self.cache.set(cache_key, result)
        return result

    def _fetch_odds(self, fixture: Dict[str, Any], league_code: str) -> Tuple[float, float, float, List]:
        """Fetch odds from The Odds API and API-Sports, return best odds + all bookmaker data."""
        fixture_id = fixture.get("fixture", {}).get("id")
        home_name = fixture.get("home", {}).get("name", "").lower()
        away_name = fixture.get("away", {}).get("name", "").lower()

        cache_key = f"odds_full_{fixture_id}_{league_code}"
        cached = self.cache.get(cache_key, ttl_hours=1)
        if cached:
            return tuple(cached)

        odds_home, odds_draw, odds_away = 2.0, 3.2, 3.0
        all_bookmakers = []

        # Primary: The Odds API - best real bookmaker odds
        if "odds_api" in self.clients:
            try:
                events = self.clients["odds_api"].fetch_odds_for_league(league_code)
                for event in events:
                    eh = (event.get("home_team") or "").lower()
                    ea = (event.get("away_team") or "").lower()
                    # fuzzy match team names
                    if (home_name[:4] in eh or eh[:4] in home_name) and \
                       (away_name[:4] in ea or ea[:4] in away_name):
                        bookmakers = event.get("bookmakers", [])
                        home_odds_list, draw_odds_list, away_odds_list = [], [], []
                        for bm in bookmakers:
                            bm_name = bm.get("title", "")
                            bm_odds = {"bookmaker": bm_name}
                            for market in bm.get("markets", []):
                                if market.get("key") == "h2h":
                                    outcomes = market.get("outcomes", [])
                                    for o in outcomes:
                                        oname = (o.get("name") or "").lower()
                                        price = float(o.get("price", 0))
                                        if "draw" in oname:
                                            bm_odds["draw"] = price
                                            draw_odds_list.append(price)
                                        elif home_name[:4] in oname or oname[:4] in home_name:
                                            bm_odds["home"] = price
                                            home_odds_list.append(price)
                                        else:
                                            bm_odds["away"] = price
                                            away_odds_list.append(price)
                            if len(bm_odds) > 1:
                                all_bookmakers.append(bm_odds)
                        if home_odds_list:
                            odds_home = max(home_odds_list)  # best available
                        if draw_odds_list:
                            odds_draw = max(draw_odds_list)
                        if away_odds_list:
                            odds_away = max(away_odds_list)
                        break
            except Exception:
                pass

        # Fallback: API-Sports odds
        if odds_home == 2.0 and "api_sports" in self.clients and fixture_id:
            try:
                odds_data = self.clients["api_sports"].fetch_odds(fixture_id)
                if odds_data:
                    bookmakers = odds_data[0].get("bookmakers", [])
                    for bm in bookmakers:
                        bets = bm.get("bets", [])
                        for bet in bets:
                            if bet.get("name") == "Match Winner":
                                values = bet.get("values", [])
                                bm_entry = {"bookmaker": bm.get("name", "")}
                                for v in values:
                                    val = v.get("value", "").lower()
                                    price = float(v.get("odd", 0))
                                    if val == "home":
                                        bm_entry["home"] = price
                                        odds_home = price
                                    elif val == "draw":
                                        bm_entry["draw"] = price
                                        odds_draw = price
                                    elif val == "away":
                                        bm_entry["away"] = price
                                        odds_away = price
                                if len(bm_entry) > 1:
                                    all_bookmakers.append(bm_entry)
            except Exception:
                pass

        result = [odds_home, odds_draw, odds_away, all_bookmakers]
        self.cache.set(cache_key, result)
        return tuple(result)

    def get_all_clients(self) -> Dict[str, Any]:
        """Return all initialized API clients."""
        return self.clients
