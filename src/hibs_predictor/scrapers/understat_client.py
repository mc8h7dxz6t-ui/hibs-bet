"""Understat.com league match xG (public pages + AJAX; respect robots & low rate).

Since late 2025, league rows are served from ``/getLeagueData/{slug}/{season}`` after a
session cookie is set. Legacy HTML ``datesData`` embeds are kept as a fallback only.
"""

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

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
    """Loose match without conflating e.g. Manchester United vs Manchester City."""
    na, nb = _norm_match_name(a), _norm_match_name(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    pa = [p for p in na.split() if len(p) > 2]
    pb = [p for p in nb.split() if len(p) > 2]
    if not pa or not pb:
        return False
    overlap = set(pa) & set(pb)
    if len(overlap) >= 2:
        return True
    if len(overlap) == 1 and (len(pa) == 1 or len(pb) == 1):
        return True
    if len(pa) >= 2 and len(pb) >= 2 and pa[-1] == pb[-1] and pa[0] == pb[0]:
        return True
    return False


def _row_datetime_utc(row: Dict[str, Any]) -> Optional[datetime]:
    raw = row.get("datetime")
    if not raw or not isinstance(raw, str):
        return None
    try:
        dt = datetime.strptime(raw.strip(), "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _fixture_kickoff_utc(fixture: Optional[Dict[str, Any]]) -> Optional[datetime]:
    if not fixture:
        return None
    from hibs_predictor.data_source_policy import parse_fixture_datetime_utc

    return parse_fixture_datetime_utc(fixture)


def find_fixture_row(
    league_code: str,
    season_year: int,
    home_name: str,
    away_name: str,
    fixture: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Best Understat league row for this fixture (prefer kickoff date, then finished xG)."""
    rows = fetch_league_matches(league_code, season_year)
    kickoff = _fixture_kickoff_utc(fixture)
    candidates: List[Dict[str, Any]] = []
    for row in rows:
        ho = row.get("h") or {}
        ao = row.get("a") or {}
        rh = ho.get("title") if isinstance(ho, dict) else str(ho)
        ra = ao.get("title") if isinstance(ao, dict) else str(ao)
        if _names_match(home_name, rh) and _names_match(away_name, ra):
            candidates.append(row)
    if not candidates:
        return None
    if kickoff is not None:
        dated = [
            row
            for row in candidates
            if (_row_datetime_utc(row) and abs((_row_datetime_utc(row) - kickoff).total_seconds()) < 36 * 3600)
        ]
        if dated:
            for row in dated:
                if extract_xg_from_row(row):
                    return row
            return dated[0]
    for row in candidates:
        if extract_xg_from_row(row):
            return row
    return candidates[0]


def team_rolling_xg(
    league_code: str,
    season_year: int,
    team_name: str,
    *,
    min_samples: int = 3,
    limit: int = 8,
) -> Optional[Tuple[float, float, int]]:
    """Rolling avg (xg_for, xg_against) from recent finished Understat league matches."""
    rows = fetch_league_matches(league_code, season_year)
    xg_for: List[float] = []
    xg_against: List[float] = []
    for row in reversed(rows):
        if not row.get("isResult"):
            continue
        xg = row.get("xG")
        if not isinstance(xg, dict):
            continue
        ho = row.get("h") or {}
        ao = row.get("a") or {}
        rh = ho.get("title") if isinstance(ho, dict) else str(ho)
        ra = ao.get("title") if isinstance(ao, dict) else str(ao)
        try:
            if _names_match(team_name, rh):
                xf = float(xg.get("h"))
                xa = float(xg.get("a"))
            elif _names_match(team_name, ra):
                xf = float(xg.get("a"))
                xa = float(xg.get("h"))
            else:
                continue
        except (TypeError, ValueError):
            continue
        if xf <= 0.04 or xa < 0:
            continue
        xg_for.append(xf)
        xg_against.append(xa)
        if len(xg_for) >= limit:
            break
    if len(xg_for) < min_samples:
        return None
    return sum(xg_for) / len(xg_for), sum(xg_against) / len(xg_against), len(xg_for)


def resolve_understat_xg(
    league_code: str,
    season_year: int,
    home_name: str,
    away_name: str,
    fixture: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[Dict[str, float]], str, Dict[str, Any]]:
    """
    Match-level xG when the Understat row has values; else team rolling averages.

    Returns (payload, source_tag, meta). payload is None when nothing usable.
    """
    meta: Dict[str, Any] = {"season_year": season_year}
    row = find_fixture_row(league_code, season_year, home_name, away_name, fixture=fixture)
    if row:
        xg = extract_xg_from_row(row)
        if xg.get("xg_home") and xg.get("xg_away"):
            meta["match_confident"] = True
            meta["understat_row_id"] = row.get("id")
            return xg, "understat_xg", meta
        meta["row_without_xg"] = True
    home_roll = team_rolling_xg(league_code, season_year, home_name)
    away_roll = team_rolling_xg(league_code, season_year, away_name)
    if home_roll and away_roll:
        h_for, _, h_n = home_roll
        a_for, _, a_n = away_roll
        meta["home_n"] = h_n
        meta["away_n"] = a_n
        meta["team_rolling"] = True
        return {"xg_home": h_for, "xg_away": a_for}, "understat_team_xg", meta
    return None, "", meta


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
