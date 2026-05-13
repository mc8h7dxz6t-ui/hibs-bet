"""Understat.com embedded league JSON (public pages; respect robots & low rate)."""

import json
import re
from typing import Any, Dict, List, Optional

import requests

# Our league_code → Understat league path slug (season year is calendar end year used on site)
LEAGUE_SLUG = {
    "EPL": "EPL",
    "LA_LIGA": "La_liga",
    "SERIE_A": "Serie_A",
    "BUNDESLIGA": "Bundesliga",
    "LIGUE_1": "Ligue_1",
    "EREDIVISIE": "Eredivisie",
    "PRIMEIRA": "PRL",
    "CHAMPIONSHIP": "E_championship",
    "BELGIUM_FIRST": "Belgian_First_Division",
    "DENMARK_SL": "Denmark_Superliga",
    "GREECE_SL": "Greek_Super_League",
    "AUSTRIA_BL": "Austrian_Bundesliga",
}

_HEADERS = {"User-Agent": "hibs.bet/1.0 (stats enrichment; contact: local)"}


def _extract_json_array(html: str) -> Optional[List[Dict[str, Any]]]:
    """Understat embeds matches JSON in escaped form inside scripts."""
    patterns = [
        r"datesData\s*=\s*JSON\.parse\(\s*'([^']+)'\s*\)",
        r"var\s+datesData\s*=\s*JSON\.parse\(\s*decodeURIComponent\(\s*'([^']+)'\s*\)\s*\)",
        r"matchesData\s*=\s*JSON\.parse\(\s*'([^']+)'\s*\)",
    ]
    for pat in patterns:
        m = re.search(pat, html, re.I)
        if not m:
            continue
        raw = m.group(1).encode("utf-8").decode("unicode_escape", errors="ignore")
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            continue
    return None


def fetch_league_matches(league_code: str, season_year: int) -> List[Dict[str, Any]]:
    slug = LEAGUE_SLUG.get(league_code)
    if not slug:
        return []
    url = f"https://understat.com/league/{slug}/{season_year}"
    r = requests.get(url, headers=_HEADERS, timeout=25)
    r.raise_for_status()
    arr = _extract_json_array(r.text)
    return arr or []


def find_fixture_row(
    league_code: str,
    season_year: int,
    home_name: str,
    away_name: str,
) -> Optional[Dict[str, Any]]:
    rows = fetch_league_matches(league_code, season_year)
    h = (home_name or "").lower()
    a = (away_name or "").lower()
    for row in rows:
        ho = row.get("h") or {}
        ao = row.get("a") or {}
        rh = ho.get("title") if isinstance(ho, dict) else str(ho)
        ra = ao.get("title") if isinstance(ao, dict) else str(ao)
        rh, ra = str(rh).lower(), str(ra).lower()
        if (h in rh or rh in h) and (a in ra or ra in a):
            return row
    return None


def extract_xg_from_row(row: Dict[str, Any]) -> Dict[str, float]:
    """Return xG fields when present on a league row."""
    out: Dict[str, float] = {}
    xg = row.get("xG")
    if isinstance(xg, dict):
        for side, key in (("h", "xg_home"), ("a", "xg_away")):
            try:
                out[key] = float(xg.get(side))
            except (TypeError, ValueError):
                pass
    for key in ("forecast", "pps"):
        if key in row:
            try:
                out[key] = float(row[key])
            except (TypeError, ValueError):
                pass
    return out
