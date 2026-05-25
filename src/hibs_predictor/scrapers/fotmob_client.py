"""FotMob public JSON — fixture fallback + league-table xG enrichment.

FotMob exposes public, unauthenticated JSON used by its website. The endpoint is
undocumented/unversioned, so this adapter is deliberately read-only, cached, and
used only as a fixture gap-filler after primary providers return nothing.

League xG (``/api/data/leagues?id=``): season team xG / xG conceded from the
competition table — fills UEFA cups and domestic leagues when Understat/API xG
is thin. Per-match ``matchDetails`` is Turnstile-gated (403) and not used here.

Env:
  HIBS_ENABLE_FOTMOB_XG — explicit on/off for league-table xG (default off except
    UEFA cups + ``HIBS_MAX_DATA=1``).
  HIBS_ENABLE_FOTMOB_FIXTURES — daily matches fixture fallback (see web.py).
  FOTMOB_TIMEZONE — timezone for daily matches (default Europe/London).
"""

from __future__ import annotations

import os
import re
import unicodedata
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

from hibs_predictor.cache import Cache

# Working endpoint (2025+): old ``/api/matches`` returns 404 HTML.
MATCHES_URL = "https://www.fotmob.com/api/data/matches"
LEAGUES_URL = "https://www.fotmob.com/api/data/leagues"
DEFAULT_TIMEZONE = "Europe/London"

# Prefer explicit primary id when a league_code maps to multiple FotMob ids.
FOTMOB_PRIMARY_LEAGUE_ID: Dict[str, int] = {
    "UECL": 10216,
    "PRIMEIRA": 61,
}

# UEFA / internationals / domestic cups: league-table xG on by default (main xG gap vs Understat).
FOTMOB_XG_CUP_DEFAULT_ON = frozenset(
    {
        "UCL",
        "EUROPA_LEAGUE",
        "UECL",
        "EUROS",
        "WORLD_CUP",
        "NATIONS_LEAGUE",
        "SCOTTISH_CUP",
        "FA_CUP",
        "LEAGUE_CUP",
        "COUPE_DE_FRANCE",
    }
)

# Cup ties without their own FotMob xG table — use parent league season xG.
FOTMOB_XG_LEAGUE_FALLBACK: Dict[str, str] = {
    "SCOTTISH_CUP": "SCOTLAND",
    "SCOTLAND_L1": "SCOTLAND_CHAMP",
    "SCOTLAND_L2": "SCOTLAND_CHAMP",
    "FA_CUP": "EPL",
    "LEAGUE_CUP": "EPL",
    "COUPE_DE_FRANCE": "LIGUE_1",
}

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
    "NATIONS_LEAGUE": {9806, 9807, 9808, 9809},
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


def _env_on(name: str, default: str = "0") -> bool:
    return (os.getenv(name, default) or default).strip().lower() not in ("0", "false", "no", "off")


def fotmob_xg_enabled(league_code: str = "") -> bool:
    """League-table xG when scrape xG is on; cups default-on; MAX_DATA enables all mapped leagues."""
    if not _env_on("HIBS_SCRAPE_XG", "1"):
        return False
    raw = (os.getenv("HIBS_ENABLE_FOTMOB_XG") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    code = (league_code or "").strip().upper()
    if code in FOTMOB_XG_CUP_DEFAULT_ON:
        return True
    return _env_on("HIBS_MAX_DATA", "0")


def effective_xg_league_code(league_code: str) -> str:
    """Map cup / lower-tier codes to a FotMob league with an xG table."""
    code = (league_code or "").strip().upper()
    if code in FOTMOB_LEAGUE_IDS:
        return code
    return FOTMOB_XG_LEAGUE_FALLBACK.get(code, code)


def primary_league_id(league_code: str) -> Optional[int]:
    """Single FotMob competition id for a hibs league code."""
    code = effective_xg_league_code(league_code)
    if code in FOTMOB_PRIMARY_LEAGUE_ID:
        return FOTMOB_PRIMARY_LEAGUE_ID[code]
    ids = FOTMOB_LEAGUE_IDS.get(code)
    if not ids:
        return None
    return min(ids)


def _norm_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    for rm in (" fc", " afc", " cf", " sc", " united", " city"):
        if s.endswith(rm):
            s = s[: -len(rm)].strip()
    return s


def fetch_league_data(league_id: int, *, cache: Optional[Cache] = None) -> Dict[str, Any]:
    """Fetch competition payload (standings + xG table). Cached ~12h per league id."""
    cache = cache or Cache()
    key = f"fotmob_league_{int(league_id)}"
    hit = cache.get(key, ttl_hours=12.0)
    if isinstance(hit, dict) and hit.get("details") is not None:
        return hit
    resp = requests.get(LEAGUES_URL, params={"id": int(league_id)}, headers=_HEADERS, timeout=25)
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, dict):
        payload = {}
    cache.set(key, payload, ttl_hours=12.0)
    return payload


def parse_league_xg_table(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract team xG rows from ``table[].data.table.xg``."""
    table_blocks = payload.get("table")
    if not isinstance(table_blocks, list):
        return []
    for block in table_blocks:
        if not isinstance(block, dict):
            continue
        data = block.get("data")
        if not isinstance(data, dict):
            continue
        inner = data.get("table")
        if not isinstance(inner, dict):
            continue
        xg_rows = inner.get("xg")
        if isinstance(xg_rows, list) and xg_rows:
            return [r for r in xg_rows if isinstance(r, dict)]
    return []


def find_team_xg_row(rows: List[Dict[str, Any]], team_name: str) -> Optional[Dict[str, Any]]:
    tn = _norm_name(team_name)
    if not tn:
        return None
    for row in rows:
        for key in ("name", "shortName"):
            rt = _norm_name(str(row.get(key) or ""))
            if not rt:
                continue
            if tn == rt or tn in rt or rt in tn:
                return row
            tp = tn.split()
            rp = rt.split()
            if tp and rp and tp[0] == rp[0] and len(tp[0]) > 3:
                return row
    return None


def row_to_xg_profile(row: Dict[str, Any], *, min_played: int = 3) -> Optional[Dict[str, Any]]:
    """Per-match xG for/against from season totals."""
    try:
        played = int(row.get("played") or 0)
        xg = float(row.get("xg") or 0)
        xgc = float(row.get("xgConceded") or 0)
    except (TypeError, ValueError):
        return None
    if played < min_played or xg <= 0:
        return None
    return {
        "avg_xg_for": xg / played,
        "avg_xg_against": xgc / played if xgc > 0 else xg / played,
        "n": played,
        "team_name": row.get("name") or row.get("shortName"),
        "team_id": row.get("id"),
    }


def fixture_xg_from_profiles(
    home_prof: Dict[str, Any], away_prof: Dict[str, Any]
) -> Optional[Tuple[float, float]]:
    """Blend attack vs opponent defence (same pattern as StatsBomb goals proxy)."""
    try:
        xh = (float(home_prof["avg_xg_for"]) + float(away_prof["avg_xg_against"])) / 2.0
        xa = (float(away_prof["avg_xg_for"]) + float(home_prof["avg_xg_against"])) / 2.0
    except (TypeError, ValueError, KeyError):
        return None
    if xh <= 0.04 or xa <= 0.04:
        return None
    return max(0.35, min(3.2, xh)), max(0.35, min(3.2, xa))


def team_xg_profile_for_league(
    league_code: str, team_name: str, *, cache: Optional[Cache] = None
) -> Optional[Dict[str, Any]]:
    if not fotmob_xg_enabled(league_code):
        return None
    lid = primary_league_id(league_code)
    if lid is None:
        return None
    try:
        payload = fetch_league_data(lid, cache=cache)
        rows = parse_league_xg_table(payload)
        row = find_team_xg_row(rows, team_name)
        if not row:
            return None
        prof = row_to_xg_profile(row)
        if prof:
            prof["league_id"] = lid
            prof["league_code"] = league_code
        return prof
    except Exception:
        return None


def resolve_league_fixture_xg(
    league_code: str,
    home_name: str,
    away_name: str,
    *,
    cache: Optional[Cache] = None,
) -> Optional[Tuple[float, float, Dict[str, Any]]]:
    """
    Return (xg_home, xg_away, meta) from FotMob league-table xG, or None.
    One HTTP fetch per league id (cached); no invented stats on failure.
    """
    if not fotmob_xg_enabled(league_code):
        return None
    effective = effective_xg_league_code(league_code)
    lid = primary_league_id(effective)
    if lid is None:
        return None
    try:
        payload = fetch_league_data(lid, cache=cache)
        rows = parse_league_xg_table(payload)
        if len(rows) < 2:
            return None
        h_row = find_team_xg_row(rows, home_name)
        a_row = find_team_xg_row(rows, away_name)
        if not h_row or not a_row:
            return None
        hp = row_to_xg_profile(h_row)
        ap = row_to_xg_profile(a_row)
        if not hp or not ap:
            return None
        pair = fixture_xg_from_profiles(hp, ap)
        if not pair:
            return None
        meta = {
            "league_id": lid,
            "home_n": hp.get("n"),
            "away_n": ap.get("n"),
            "home_avg_for": round(float(hp["avg_xg_for"]), 3),
            "away_avg_for": round(float(ap["avg_xg_for"]), 3),
        }
        if effective != (league_code or "").strip().upper():
            meta["fotmob_league_fallback"] = effective
        return pair[0], pair[1], meta
    except Exception:
        return None


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
        return {"ok": n >= 5, "league_count": n, "date": day.isoformat(), "http_status": 200}
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        hint = (
            "HTTP 404 — use /api/data/matches (legacy /api/matches is dead)"
            if status == 404
            else str(exc)[:160]
        )
        return {
            "ok": False,
            "league_count": 0,
            "http_status": status,
            "error": hint,
            "date": day.isoformat(),
        }
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
