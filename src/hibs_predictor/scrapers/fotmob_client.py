"""Small FotMob fixture fallback.

FotMob exposes public, unauthenticated JSON used by its website. The endpoint is
undocumented/unversioned, so this adapter is deliberately read-only, cached, and
used only as a fixture gap-filler after primary providers return nothing.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional

import requests

from hibs_predictor.cache import Cache

# Working endpoint (2025+): old ``/api/matches`` returns 404 HTML.
MATCHES_URL = "https://www.fotmob.com/api/data/matches"
DEFAULT_TIMEZONE = "Europe/London"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.fotmob.com/",
}

# Best-effort competition ids (``id`` / ``primaryId`` on league rows).
FOTMOB_LEAGUE_IDS: Dict[str, set[int]] = {
    "EPL": {47},
    "CHAMPIONSHIP": {48},
    "LEAGUE_ONE": {108},
    "LEAGUE_TWO": {109},
    "LA_LIGA": {87},
    "SERIE_A": {55},
    "BUNDESLIGA": {54},
    "LIGUE_1": {53},
    "EREDIVISIE": {57},
    "PRIMEIRA": {61},
    "BELGIUM_FIRST": {40},
    "SCOTLAND": {64},
    "SCOTLAND_CHAMP": {123},
    "NORWAY_ELITESERIEN": {59},
    "FINLAND_VEIKKAUSLIIGA": {51},
    "UCL": {42},
    "EUROPA_LEAGUE": {73},
    "UECL": {10216, 73},
    "WORLD_CUP": {77},
    "EUROS": {50},
}


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _league_ids_from_row(row: Dict[str, Any]) -> set[int]:
    ids: set[int] = set()
    for key in ("id", "primaryId", "parentLeagueId", "leagueId"):
        val = _as_int(row.get(key))
        if val is not None:
            ids.add(val)
    return ids


def _date_range(start: date, end: date) -> Iterable[date]:
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def _matches_timezone() -> str:
    return (os.getenv("FOTMOB_TIMEZONE") or DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE


def fetch_matches_for_date(day: date, *, cache: Optional[Cache] = None) -> Dict[str, Any]:
    """Return the raw FotMob daily matches payload with a short disk cache."""
    cache = cache or Cache()
    key = f"fotmob_matches_{day.strftime('%Y%m%d')}_{_matches_timezone()}"
    cached = cache.get(key, ttl_hours=2)
    if isinstance(cached, dict) and cached.get("leagues") is not None:
        return cached

    resp = requests.get(
        MATCHES_URL,
        params={"date": day.strftime("%Y%m%d"), "timezone": _matches_timezone()},
        headers=_HEADERS,
        timeout=25,
    )
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, dict):
        payload = {}
    cache.set(key, payload, ttl_hours=2)
    return payload


def probe_matches_api(day: Optional[date] = None) -> Dict[str, Any]:
    """Health probe: verify daily matches JSON returns leagues."""
    day = day or date.today()
    try:
        payload = fetch_matches_for_date(day, cache=Cache())
        leagues = payload.get("leagues") or []
        n = len(leagues) if isinstance(leagues, list) else 0
        return {"ok": n >= 5, "league_count": n, "date": day.isoformat()}
    except Exception as exc:
        return {"ok": False, "league_count": 0, "error": str(exc)[:160]}


def fixtures_for_league(league_code: str, start: date, end: date, *, cache: Optional[Cache] = None) -> List[Dict[str, Any]]:
    """Extract FotMob match rows for a configured league over an inclusive date range."""
    wanted = FOTMOB_LEAGUE_IDS.get(league_code) or set()
    if not wanted:
        return []
    cache = cache or Cache()
    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for day in _date_range(start, end):
        payload = fetch_matches_for_date(day, cache=cache)
        for league in payload.get("leagues") or []:
            if not isinstance(league, dict) or not (_league_ids_from_row(league) & wanted):
                continue
            for match in league.get("matches") or []:
                if not isinstance(match, dict):
                    continue
                mid = str(match.get("id") or match.get("matchId") or "")
                key = mid or f"{match.get('home')}|{match.get('away')}|{match.get('status')}"
                if key in seen:
                    continue
                seen.add(key)
                out = dict(match)
                out["_fotmob_league"] = {
                    "id": league.get("id"),
                    "primaryId": league.get("primaryId"),
                    "name": league.get("name"),
                }
                rows.append(out)
    return rows
