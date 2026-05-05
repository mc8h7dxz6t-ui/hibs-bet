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
        cache_key = f"enriched_fixture_{fixture.get('id', '')}_{league_code}"
        cached = self.cache.get(cache_key, ttl_hours=2)
        if cached:
            return cached

        enriched = fixture.copy()
        league = LEAGUES.get(league_code, {})

        home_id = fixture.get("teams", {}).get("home", {}).get("id")
        away_id = fixture.get("teams", {}).get("away", {}).get("id")

        enriched["home_stats"] = self._fetch_team_stats(home_id, league_code)
        enriched["away_stats"] = self._fetch_team_stats(away_id, league_code)

        enriched["home_recent"] = self._fetch_team_recent_matches(home_id, league_code)
        enriched["away_recent"] = self._fetch_team_recent_matches(away_id, league_code)

        enriched["home_form"] = TeamStrengthCalculator.calculate_form_strength(enriched["home_recent"])
        enriched["away_form"] = TeamStrengthCalculator.calculate_form_strength(enriched["away_recent"])

        enriched["home_home_factor"] = TeamStrengthCalculator.calculate_home_away_factor(
            home_id, enriched["home_recent"], is_home=True
        )
        enriched["away_away_factor"] = TeamStrengthCalculator.calculate_home_away_factor(
            away_id, enriched["away_recent"], is_home=False
        )

        enriched["xg_home"], enriched["xg_away"] = self._fetch_expected_goals(fixture.get("fixture", {}).get("id"))

        enriched["odds_home"], enriched["odds_draw"], enriched["odds_away"] = self._fetch_odds(fixture, league_code)

        enriched["league_factor"] = league.get("strength_factor", 1.0)

        self.cache.set(cache_key, enriched)
        return enriched

    def _fetch_team_stats(self, team_id: Optional[int], league_code: str) -> Dict[str, Any]:
        """Fetch team statistics from available APIs."""
        if not team_id:
            return {"goals_for": 30, "goals_against": 25, "shots_on_target": 100}

        cache_key = f"team_stats_{team_id}_{league_code}"
        cached = self.cache.get(cache_key, ttl_hours=12)
        if cached:
            return cached

        stats = {
            "goals_for": 30,
            "goals_against": 25,
            "shots_on_target": 100,
            "expected_goals": 28.0,
            "expected_goals_against": 24.0,
            "shots_on_target_against": 95,
        }

        if "api_sports" in self.clients:
            try:
                league = LEAGUES.get(league_code, {})
                season = datetime.now().year
                team_stats = self.clients["api_sports"].fetch_team_statistics(team_id, season)
                
                if team_stats.get("statistics"):
                    stat_data = team_stats["statistics"]
                    stats.update({
                        "goals_for": stat_data.get("goals", {}).get("for", 30),
                        "goals_against": stat_data.get("goals", {}).get("against", 25),
                        "shots_on_target": stat_data.get("shots", {}).get("on", 100),
                        "expected_goals": stat_data.get("expected_goals", {}).get("for", 28.0),
                    })
            except Exception:
                pass

        if "stats_api" in self.clients:
            try:
                season = datetime.now().year
                stats_data = self.clients["stats_api"].fetch_team_stats(team_id, season)
                if stats_data.get("response", {}).get("statistics"):
                    stat_entries = stats_data["response"]["statistics"]
                    for stat in stat_entries:
                        if stat.get("type") == "Shots on Target":
                            stats["shots_on_target"] = stat.get("value", 100)
                        elif stat.get("type") == "Goals":
                            stats["goals_for"] = stat.get("value", 30)
            except Exception:
                pass

        self.cache.set(cache_key, stats)
        return stats

    def _fetch_team_recent_matches(self, team_id: Optional[int], league_code: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch team's recent matches from available APIs."""
        if not team_id:
            return []

        cache_key = f"team_recent_{team_id}_{league_code}"
        cached = self.cache.get(cache_key, ttl_hours=4)
        if cached:
            return cached

        matches = []

        if "api_sports" in self.clients:
            try:
                api_matches = self.clients["api_sports"].fetch_team_last_matches(team_id, limit=limit)
                matches.extend(api_matches[:limit])
            except Exception:
                pass

        if not matches and "football_data_org" in self.clients:
            try:
                league = LEAGUES.get(league_code, {})
                team = self.clients["football_data_org"].fetch_team(team_id)
                if team.get("_links", {}).get("matches"):
                    # Fetch from team's match endpoint
                    pass
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

    def _fetch_odds(self, fixture: Dict[str, Any], league_code: str) -> Tuple[float, float, float]:
        """Fetch odds from multiple bookmakers."""
        fixture_id = fixture.get("fixture", {}).get("id")
        
        cache_key = f"odds_{fixture_id}_{league_code}"
        cached = self.cache.get(cache_key, ttl_hours=2)
        if cached:
            return cached

        odds_home, odds_draw, odds_away = 2.0, 3.2, 3.0

        if "api_sports" in self.clients:
            try:
                odds_data = self.clients["api_sports"].fetch_odds(fixture_id)
                if odds_data:
                    bookmakers = odds_data[0].get("bookmakers", [])
                    if bookmakers:
                        bets = bookmakers[0].get("bets", [])
                        for bet in bets:
                            if bet.get("name") == "Winner":
                                values = bet.get("values", [])
                                if len(values) >= 3:
                                    odds_home = float(values[0].get("odd", 2.0))
                                    odds_away = float(values[1].get("odd", 3.0))
                                    odds_draw = float(values[2].get("odd", 3.2))
            except Exception:
                pass

        result = (odds_home, odds_draw, odds_away)
        self.cache.set(cache_key, result)
        return result

    def get_all_clients(self) -> Dict[str, Any]:
        """Return all initialized API clients."""
        return self.clients
