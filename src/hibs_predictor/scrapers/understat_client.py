"""Understat.com league match xG (public pages + AJAX; respect robots & low rate).

Since late 2025, league rows are served from ``/getLeagueData/{slug}/{season}`` after a
session cookie is set. Legacy HTML ``datesData`` embeds are kept as a fallback only.
"""

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

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-GB,en;q=0.9",
}
_AJAX_HEADERS = {**_HEADERS, "X-Requested-With": "XMLHttpRequest"}

_session: Optional[requests.Session] = None


def _session_get() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(_HEADERS)
    return _session


def _warm_session(slug: str, season_year: int) -> None:
    """Visit league page so PHPSESSID is set before AJAX league data."""
    url = f"https://understat.com/league/{slug}/{season_year}"
    _session_get().get(url, timeout=25)


def _fetch_league_dates_api(slug: str, season_year: int) -> List[Dict[str, Any]]:
    _warm_session(slug, season_year)
    api_url = f"https://understat.com/getLeagueData/{slug}/{season_year}"
    r = _session_get().get(api_url, headers=_AJAX_HEADERS, timeout=25)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        return []
    dates = data.get("dates")
    return dates if isinstance(dates, list) else []


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
    try:
        rows = _fetch_league_dates_api(slug, season_year)
        if rows:
            return rows
    except (requests.RequestException, json.JSONDecodeError, TypeError, ValueError):
        pass
    # Legacy embed fallback (pre-2025 layout)
    url = f"https://understat.com/league/{slug}/{season_year}"
    r = _session_get().get(url, timeout=25)
    r.raise_for_status()
    arr = _extract_json_array(r.text)
    return arr or []


def _norm_match_name(name: str) -> str:
    """Loose match for API-Football / FDO long names vs Understat short titles."""
    s = (name or "").lower().strip()
    for drop in (
        "acf ",
        "ac ",
        "fc ",
        "ss ",
        "us ",
        "ssd ",
        "uc ",
        "as ",
        "1909 ",
        "1913 ",
        "bc ",
    ):
        if s.startswith(drop):
            s = s[len(drop) :].strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _names_match(a: str, b: str) -> bool:
    na, nb = _norm_match_name(a), _norm_match_name(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    pa = [p for p in na.split() if len(p) > 2]
    pb = [p for p in nb.split() if len(p) > 2]
    return bool(pa and pb and pa[0] == pb[0])


def find_fixture_row(
    league_code: str,
    season_year: int,
    home_name: str,
    away_name: str,
) -> Optional[Dict[str, Any]]:
    rows = fetch_league_matches(league_code, season_year)
    for row in rows:
        ho = row.get("h") or {}
        ao = row.get("a") or {}
        rh = ho.get("title") if isinstance(ho, dict) else str(ho)
        ra = ao.get("title") if isinstance(ao, dict) else str(ao)
        if _names_match(home_name, rh) and _names_match(away_name, ra):
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
