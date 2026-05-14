import os
from typing import Any, Dict, List, Optional

import requests

from hibs_predictor.cache import Cache
from hibs_predictor.rate_limiter import RateLimiter


_API_SPORTS_MISSING_KEY_WARNED = False


def _api_sports_errors_indicate_missing_or_invalid_key(errors: Any) -> bool:
    text = str(errors).lower()
    if "application key" in text:
        return True
    if "missing" in text and "key" in text:
        return True
    if "invalid" in text and "key" in text:
        return True
    return False


def _api_football_errors_truthy(errors: Any) -> bool:
    if errors is None:
        return False
    if isinstance(errors, str):
        return bool(errors.strip())
    if isinstance(errors, list):
        return len(errors) > 0
    if isinstance(errors, dict):
        return len(errors) > 0
    return bool(errors)


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
        response = requests.get(url, headers=self._get_headers(), params=params, timeout=20)
        response.raise_for_status()
        try:
            data = response.json()
        except ValueError as exc:
            raise ValueError(f"Invalid JSON from {self.service_name} {endpoint}: {exc}") from exc
        self.rate_limiter.record_request(self.service_name)
        self.cache.set(cache_key, data, ttl_hours=4)
        return data


class FootballDataOrgClient(BaseApiClient):
    def __init__(self, api_key: str) -> None:
        super().__init__(api_key, "https://api.football-data.org/v4", "X-Auth-Token", "football_data_org")

    def fetch_fixtures(
        self,
        competition_code: str,
        season: int,
        status: Optional[str] = "SCHEDULED",
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        endpoint = f"competitions/{competition_code}/matches"
        params: Dict[str, Any] = {"season": season}
        if status:
            params["status"] = status
        if date_from:
            params["dateFrom"] = date_from
        if date_to:
            params["dateTo"] = date_to
        data = self._get_json(endpoint, params=params)
        if not isinstance(data, dict):
            return []
        if data.get("errorCode") or data.get("message"):
            print(f"[Football-Data.org] {competition_code}: {data.get('message', data)}")
            return []
        return data.get("matches", []) or []

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

    def _get_json(self, endpoint: str, params: Optional[Dict[str, Any]] = None, use_cache: bool = True) -> Dict[str, Any]:
        """API-Football: validate body, avoid caching hard errors, surface rate/token issues."""
        cache_key = f"{self.service_name}_{endpoint}_{str(params)}"
        if use_cache:
            cached = self.cache.get(cache_key, ttl_hours=4)
            if cached is not None:
                return cached

        if not self.rate_limiter.check_rate_limit(self.service_name):
            return {"response": [], "errors": {"rate_limit": "local guard"}}

        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        try:
            response = requests.get(url, headers=self._get_headers(), params=params or {}, timeout=25)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            print(f"[API-Sports HTTP] {endpoint}: {exc}")
            return {"response": [], "errors": {"http": str(exc)}}
        except ValueError as exc:
            print(f"[API-Sports JSON] {endpoint}: {exc}")
            return {"response": [], "errors": {"json": str(exc)}}

        if not isinstance(data, dict):
            print(f"[API-Sports] {endpoint}: unexpected payload type {type(data)}")
            return {"response": [], "errors": {"shape": "non-object JSON"}}

        if _api_football_errors_truthy(data.get("errors")):
            global _API_SPORTS_MISSING_KEY_WARNED
            errs = data.get("errors")
            if _api_sports_errors_indicate_missing_or_invalid_key(errs):
                if not _API_SPORTS_MISSING_KEY_WARNED:
                    _API_SPORTS_MISSING_KEY_WARNED = True
                    print(
                        "[API-Sports] Missing or invalid API key (header x-apisports-key). "
                        "Set API_SPORTS_FOOTBALL_KEY, API_SPORTS_KEY, or APISPORTS_KEY in .env. "
                        f"First error: {errs!r}"
                    )
            else:
                print(f"[API-Sports errors] {endpoint} params={params}: {errs}")
            self.rate_limiter.record_request(self.service_name)
            return {"response": [], "errors": errs, "results": data.get("results", 0)}

        self.rate_limiter.record_request(self.service_name)
        self.cache.set(cache_key, data, ttl_hours=4)
        return data

    def fetch_injuries(self, fixture_id: int) -> List[Dict[str, Any]]:
        """Injuries / absences for a fixture (API-Football)."""
        endpoint = "injuries"
        params = {"fixture": fixture_id}
        data = self._get_json(endpoint, params=params)
        return data.get("response", []) if isinstance(data.get("response"), list) else []

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

    def fetch_fixtures_by_league(
        self,
        league_id: int,
        season: int,
        status: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        endpoint = "fixtures"
        params: Dict[str, Any] = {"league": league_id, "season": season}
        if status:
            params["status"] = status
        if date_from:
            params["from"] = date_from
        if date_to:
            params["to"] = date_to
        data = self._get_json(endpoint, params=params)
        resp = data.get("response", [])
        return resp if isinstance(resp, list) else []

    def fetch_team_last_matches(self, team_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Last *finished* league/cup matches for this team (scores present)."""
        endpoint = "fixtures"
        params = {"team": team_id, "last": limit, "status": "FT"}
        data = self._get_json(endpoint, params=params)
        return data.get("response", [])

    def fetch_team_statistics(self, team_id: int, season: int, league_id: int = None) -> Dict[str, Any]:
        endpoint = "teams/statistics"
        params = {"team": team_id, "season": season}
        if league_id:
            params["league"] = league_id
        data = self._get_json(endpoint, params=params)
        return data.get("response", {})

    def fetch_standings(self, league_id: int, season: int) -> List[Dict[str, Any]]:
        endpoint = "standings"
        params = {"league": league_id, "season": season}
        data = self._get_json(endpoint, params=params)
        standings = data.get("response", [])
        return standings[0].get("league", {}).get("standings", [[]]) if standings else [[]]

    def fetch_team_position(self, team_id: int, league_id: int, season: int) -> Dict[str, Any]:
        """Get a team's current league position and stats."""
        cache_key = f"team_position_{team_id}_{league_id}_{season}"
        cached = self.cache.get(cache_key, ttl_hours=6)
        if cached:
            return cached
        try:
            all_standings = self.fetch_standings(league_id, season)
            for group in all_standings:
                for entry in group:
                    if entry.get("team", {}).get("id") == team_id:
                        result = {
                            "position": entry.get("rank", "?"),
                            "played": entry.get("all", {}).get("played", 0),
                            "won": entry.get("all", {}).get("win", 0),
                            "drawn": entry.get("all", {}).get("draw", 0),
                            "lost": entry.get("all", {}).get("lose", 0),
                            "goals_for": entry.get("all", {}).get("goals", {}).get("for", 0),
                            "goals_against": entry.get("all", {}).get("goals", {}).get("against", 0),
                            "goal_diff": entry.get("goalsDiff", 0),
                            "points": entry.get("points", 0),
                            "form": entry.get("form", ""),
                        }
                        self.cache.set(cache_key, result, ttl_hours=6)
                        return result
        except Exception:
            pass
        return {}


class OddsApiClient(BaseApiClient):
    # Map our league codes to The Odds API v4 sport keys (see https://the-odds-api.com/liveapi/guides/v4/)
    SPORT_KEYS = {
        "EPL": "soccer_epl",
        "CHAMPIONSHIP": "soccer_england_efl_championship",
        "LEAGUE_ONE": "soccer_england_league1",
        "LEAGUE_TWO": "soccer_england_league2",
        "FA_CUP": "soccer_fa_cup",
        "SCOTLAND": "soccer_scotland_premiership",
        "SCOTLAND_CHAMP": "soccer_scotland_championship",
        "UCL": "soccer_uefa_champs_league",
        "EUROPA_LEAGUE": "soccer_uefa_europa_league",
        "UECL": "soccer_uefa_europa_conference_league",
        "LA_LIGA": "soccer_spain_la_liga",
        "SERIE_A": "soccer_italy_serie_a",
        "BUNDESLIGA": "soccer_germany_bundesliga",
        "LIGUE_1": "soccer_france_ligue_one",
        "EREDIVISIE": "soccer_netherlands_eredivisie",
        "PRIMEIRA": "soccer_portugal_primeira_liga",
        "BELGIUM_FIRST": "soccer_belgium_first_div",
        "DENMARK_SL": "soccer_denmark_superliga",
        "GREECE_SL": "soccer_greece_super_league",
        "AUSTRIA_BL": "soccer_austria_bundesliga",
        "WORLD_CUP": "soccer_fifa_world_cup",
        "EUROS": "soccer_uefa_european_championship",
        "NATIONS_LEAGUE": "soccer_uefa_nations_league",
    }

    def __init__(self, api_key: str) -> None:
        super().__init__(api_key, "https://api.the-odds-api.com/v4", "Authorization", "odds_api")

    def _get_headers(self) -> Dict[str, str]:
        return {}  # OddsAPI uses apiKey as query param

    def fetch_odds_for_league(self, league_code: str) -> List[Dict[str, Any]]:
        """Fetch all upcoming odds for a league. Returns list of events with bookmaker odds."""
        sport_key = self.SPORT_KEYS.get(league_code)
        if not sport_key:
            return []
        cache_key = f"odds_api_league_{league_code}"
        cached = self.cache.get(cache_key, ttl_hours=1)
        if cached is not None:
            return cached
        try:
            url = f"{self.base_url}/sports/{sport_key}/odds"
            params = {
                "apiKey": self.api_key,
                "regions": "uk",
                "markets": "h2h,totals",
                "oddsFormat": "decimal",
                "dateFormat": "iso",
            }
            import requests as _req
            resp = _req.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            self.cache.set(cache_key, data, ttl_hours=1)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def fetch_live_odds(self, league_key: str = "soccer_epl") -> List[Dict[str, Any]]:
        endpoint = f"sports/{league_key}/odds"
        params = {
            "apiKey": self.api_key,
            "regions": "uk,eu",
            "markets": "h2h,totals",
            "oddsFormat": "decimal",
        }
        try:
            url = f"{self.base_url}/{endpoint}"
            import requests as _req
            resp = _req.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception:
            return []


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
