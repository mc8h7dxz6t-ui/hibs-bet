"""StatsBomb open-data JSON (CC-BY-NC-SA) — https://github.com/statsbomb/open-data"""

from functools import lru_cache
from typing import Any, Dict, List

import requests

OPEN_BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"


@lru_cache(maxsize=1)
def load_competitions() -> List[Dict[str, Any]]:
    r = requests.get(f"{OPEN_BASE}/competitions.json", timeout=25)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def load_matches(competition_id: int, season_id: int) -> List[Dict[str, Any]]:
    r = requests.get(f"{OPEN_BASE}/matches/{competition_id}/{season_id}.json", timeout=35)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def find_match_by_team_names(
    matches: List[Dict[str, Any]],
    home_name: str,
    away_name: str,
) -> Dict[str, Any]:
    """Return first StatsBomb match where home/away team names match (case-insensitive substring)."""
    h = (home_name or "").lower().strip()
    a = (away_name or "").lower().strip()
    for m in matches:
        ht_obj = m.get("home_team") or {}
        at_obj = m.get("away_team") or {}
        ht = (ht_obj.get("home_team_name") or ht_obj.get("name") or "").lower()
        at = (at_obj.get("away_team_name") or at_obj.get("name") or "").lower()
        if not ht or not at:
            continue
        if (h in ht or ht in h) and (a in at or at in a):
            return m
    return {}
