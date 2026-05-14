"""Sofascore public search API (undocumented; may change)."""

from typing import Any, Dict, List, Optional

import requests

_HEADERS = {
    "User-Agent": "hibs-bet/1.0",
    "Accept": "application/json",
}


def search_all(query: str, limit: int = 8) -> Dict[str, Any]:
    url = "https://api.sofascore.com/api/v1/search/all"
    r = requests.get(url, params={"q": query}, headers=_HEADERS, timeout=15)
    r.raise_for_status()
    return r.json() if r.headers.get("content-type", "").startswith("application/json") else {}


def first_team_hit(query: str) -> Optional[Dict[str, Any]]:
    data = search_all(query, limit=5)
    res = data.get("results") or []
    for block in res:
        if block.get("type") != "team":
            continue
        entity = block.get("entity") or {}
        if entity.get("name"):
            return entity
    return None


def team_last_xg_summary(team_id: int) -> List[Dict[str, Any]]:
    """Recent events for team (includes xG when available in nested structure)."""
    url = f"https://api.sofascore.com/api/v1/team/{team_id}/events/last/0"
    r = requests.get(url, headers=_HEADERS, timeout=15)
    r.raise_for_status()
    data = r.json()
    evs = (data.get("events") or []) if isinstance(data, dict) else []
    out: List[Dict[str, Any]] = []
    for e in evs[:10]:
        home = (e.get("homeTeam", {}) or {}).get("name")
        away = (e.get("awayTeam", {}) or {}).get("name")
        hx = e.get("homeScore", {})
        ax = e.get("awayScore", {})
        out.append(
            {
                "id": e.get("id"),
                "home": home,
                "away": away,
                "homeScore": hx,
                "awayScore": ax,
                "status": (e.get("status") or {}).get("type"),
            }
        )
    return out
