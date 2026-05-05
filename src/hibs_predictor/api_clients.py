import os
from typing import Any, Dict, List, Optional

import requests

from hibs_predictor.cache import Cache
from hibs_predictor.rate_limiter import RateLimiter


class BaseApiClient:
    def __init__(self, api_key: str, base_url: str, header_name: str, service_name: str) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.header_name = header_name
        self.service_name = service_name
        self.cache = Cache()
        self.rate_limiter = RateLimiter()

    def _get_headers(self) -> Dict[str, str]:
        return {self.header_name: self.api_key}

    def _get_json(self, endpoint: str, params: Optional[Dict[str, Any]] = None, use_cache: bool = True) -> Dict[str, Any]:
        cache_key = f"{self.service_name}_{endpoint}_{str(params)}"

        if use_cache:
            cached = self.cache.get(cache_key, ttl_hours=4)
            if cached:
                return cached

        if not self.rate_limiter.check_rate_limit(self.service_name):
            return {"error": "Rate limit exceeded. Try again later."}

        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        response = requests.get(url, headers=self._get_headers(), params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        self.rate_limiter.record_request(self.service_name)
        self.cache.set(cache_key, data)
        return data


class FootballDataOrgClient(BaseApiClient):
    def __init__(self, api_key: str) -> None:
        super().__init__(api_key, "https://api.football-data.org/v4", "X-Auth-Token", "football_data_org")

    def fetch_fixtures(self, competition_code: str, season: int, status: str = "SCHEDULED") -> List[Dict[str, Any]]:
        endpoint = f"competitions/{competition_code}/matches"
        params = {"season": season, "status": status}
        data = self._get_json(endpoint, params=params)
        return data.get("matches", [])

    def fetch_team(self, team_id: int) -> Dict[str, Any]:
        endpoint = f"teams/{team_id}"
        return self._get_json(endpoint)

    def fetch_team_matches(self, team_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        endpoint = f"teams/{team_id}/matches"
        params = {"limit": limit, "status": "FINISHED"}
        data = self._get_json(endpoint, params=params)
        return data.get("matches", [])

    def parse_form_from_matches(self, matches: List[Dict[str, Any]]) -> Dict[str, Any]:
        form = []
        wins = 0
        draws = 0
        losses = 0
        goals_for = 0
        goals_against = 0
        btts_count = 0

        for match in matches[:10]:
            score = match.get("score", {})
            full_time = score.get("fullTime", {})
            home_goals = full_time.get("home", 0)
            away_goals = full_time.get("away", 0)

            if home_goals > away_goals:
                form.append("W")
                wins += 1
            elif home_goals < away_goals:
                form.append("L")
                losses += 1
            else:
                form.append("D")
                draws += 1

            if home_goals > 0 and away_goals > 0:
                btts_count += 1

            goals_for += home_goals
            goals_against += away_goals

        return {
            "form": "".join(reversed(form)),
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "goals_for": goals_for,
            "goals_against": goals_against,
            "btts_count": btts_count,
        }


class SportsMonkClient(BaseApiClient):
    def __init__(self, api_key: str) -> None:
        super().__init__(api_key, "https://soccer.sportmonks.com/api/v2.0", "Authorization", "sportsmonk")

    def fetch_fixtures(self, league_id: int, season_id: int) -> List[Dict[str, Any]]:
        endpoint = "fixtures"
        params = {
            "api_token": self.api_key,
            "leagues": league_id,
            "season_id": season_id,
            "include": "localTeam,visitorTeam,odds",
        }
        data = self._get_json(endpoint, params=params)
        return data.get("data", [])

    def fetch_team_stats(self, team_id: int) -> Dict[str, Any]:
        endpoint = f"teams/{team_id}"
        params = {"api_token": self.api_key}
        return self._get_json(endpoint, params=params)

    def fetch_team_matches(self, team_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        endpoint = "fixtures"
        params = {
            "api_token": self.api_key,
            "teams": team_id,
            "limit": limit,
            "sort": "-id",
        }
        data = self._get_json(endpoint, params=params)
        return data.get("data", [])


class ApiSportsFootballClient(BaseApiClient):
    def __init__(self, api_key: str) -> None:
        super().__init__(api_key, "https://v3.football.api-sports.io", "x-apisports-key", "api_sports")

    def fetch_odds(self, fixture_id: int) -> List[Dict[str, Any]]:
        endpoint = "odds"
        params = {"fixture": fixture_id}
        data = self._get_json(endpoint, params=params)
        return data.get("response", [])

    def fetch_fixture(self, fixture_id: int) -> Dict[str, Any]:
        endpoint = "fixtures"
        params = {"id": fixture_id}
        data = self._get_json(endpoint, params=params)
        return data.get("response", [{}])[0] if data.get("response") else {}

    def fetch_fixtures_by_league(self, league_id: int, season: int, status: Optional[str] = None) -> List[Dict[str, Any]]:
        endpoint = "fixtures"
        params = {"league": league_id, "season": season}
        if status:
            params["status"] = status
        data = self._get_json(endpoint, params=params)
        return data.get("response", [])

    def fetch_team_last_matches(self, team_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        endpoint = "fixtures"
        params = {"team": team_id, "last": limit}
        data = self._get_json(endpoint, params=params)
        return data.get("response", [])

    def fetch_team_statistics(self, team_id: int, season: int) -> Dict[str, Any]:
        endpoint = "teams/statistics"
        params = {"team": team_id, "season": season}
        data = self._get_json(endpoint, params=params)
        return data.get("response", {})

    def fetch_standings(self, league_id: int, season: int) -> List[Dict[str, Any]]:
        endpoint = "standings"
        params = {"league": league_id, "season": season}
        data = self._get_json(endpoint, params=params)
        standings = data.get("response", [])
        return standings[0].get("league", {}).get("standings", [[]]) if standings else [[]]


class OddsApiClient(BaseApiClient):
    def __init__(self, api_key: str) -> None:
        super().__init__(api_key, "https://api.the-odds-api.com/v4", "Authorization", "odds_api")

    def fetch_odds_by_event(self, event_id: str, bookmakers: str = "all") -> Dict[str, Any]:
        endpoint = f"sports/soccer_epl/events/{event_id}/odds"
        params = {
            "apiKey": self.api_key,
            "regions": "uk",
            "markets": "h2h",
            "oddsFormat": "decimal",
            "bookmakers": bookmakers,
        }
        return self._get_json(endpoint, params=params)

    def fetch_live_odds(self, league_key: str = "soccer_epl") -> List[Dict[str, Any]]:
        endpoint = f"sports/{league_key}/odds"
        params = {
            "apiKey": self.api_key,
            "regions": "uk,eu",
            "markets": "h2h,totals,spreads",
            "oddsFormat": "decimal",
        }
        data = self._get_json(endpoint, params=params)
        return data.get("events", [])


class StatsApiClient(BaseApiClient):
    def __init__(self, api_key: str) -> None:
        super().__init__(api_key, "https://v1.api-football.com", "x-rapidapi-key", "stats_api")

    def fetch_team_stats(self, team_id: int, season: int) -> Dict[str, Any]:
        endpoint = "teams/statistics"
        params = {"team": team_id, "season": season}
        return self._get_json(endpoint, params=params)

    def fetch_team_form(self, team_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        endpoint = "fixtures"
        params = {"team": team_id, "last": limit, "status": "FT"}
        data = self._get_json(endpoint, params=params)
        return data.get("response", [])

    def fetch_xg_data(self, fixture_id: int) -> Dict[str, Any]:
        endpoint = f"fixtures/statistics/{fixture_id}"
        return self._get_json(endpoint)
