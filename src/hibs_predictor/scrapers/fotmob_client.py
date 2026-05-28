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
        "INTL_FRIENDLIES",
        "SCOTTISH_CUP",
        "FA_CUP",
        "LEAGUE_CUP",
        "COUPE_DE_FRANCE",
        "COPA_DEL_REY",
        "COPPA_ITALIA",
        "DFB_POKAL",
    }
)

# Cup ties without their own FotMob xG table — use parent league season xG (all cups in config).
FOTMOB_XG_LEAGUE_FALLBACK: Dict[str, str] = {
    "SCOTTISH_CUP": "SCOTLAND",
    "SCOTLAND_L1": "SCOTLAND_CHAMP",
    "SCOTLAND_L2": "SCOTLAND_CHAMP",
    "FA_CUP": "EPL",
    "LEAGUE_CUP": "EPL",
    "COUPE_DE_FRANCE": "LIGUE_1",
    "COPA_DEL_REY": "LA_LIGA",
    "COPPA_ITALIA": "SERIE_A",
    "DFB_POKAL": "BUNDESLIGA",
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
    "DENMARK_SL": {46},
    "GREECE_SL": {135},
    "AUSTRIA_BL": {38},
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
    # National-team friendlies (FotMob id varies; name scan in fixtures_international_friendlies).
    "INTL_FRIENDLIES": {914609},
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
    if code == "INTL_FRIENDLIES":
        if _env_on("HIBS_ENABLE_FOTMOB_FRIENDLIES", "0"):
            return True
        try:
            from hibs_predictor.tournament_focus import friendlies_max_data_profile_enabled

            if friendlies_max_data_profile_enabled():
                return True
        except Exception:
            pass
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


def _finished_match_scores(match: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    """Best-effort full-time goals from a FotMob daily-match row."""
    if not isinstance(match, dict):
        return None
    home = match.get("home") if isinstance(match.get("home"), dict) else {}
    away = match.get("away") if isinstance(match.get("away"), dict) else {}
    status = match.get("status") if isinstance(match.get("status"), dict) else {}
    reason = status.get("reason") if isinstance(status.get("reason"), dict) else {}
    short = str(reason.get("short") or status.get("short") or match.get("status") or "").upper()
    if short and short not in ("FT", "AET", "PEN", "FULL_TIME", "FINISHED"):
        if not status.get("finished") and not status.get("completed"):
            return None
    try:
        if home.get("score") is not None and away.get("score") is not None:
            return int(home["score"]), int(away["score"])
    except (TypeError, ValueError):
        pass
    score_str = str(status.get("scoreStr") or "").strip()
    if score_str and "-" in score_str:
        parts = [p.strip() for p in score_str.replace("–", "-").split("-", 1)]
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            return int(parts[0]), int(parts[1])
    return None


def fotmob_match_to_recent_format(match: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize a finished FotMob daily-match row → API-Sports-like recent shape."""
    scores = _finished_match_scores(match)
    if not scores:
        return None
    home_g, away_g = scores
    home = match.get("home") or {}
    away = match.get("away") or {}
    if not isinstance(home, dict) or not isinstance(away, dict):
        return None
    home_name = home.get("longName") or home.get("name") or "?"
    away_name = away.get("longName") or away.get("name") or "?"
    status = match.get("status") if isinstance(match.get("status"), dict) else {}
    date_s = (
        match.get("utcTime")
        or status.get("utcTime")
        or match.get("time")
        or match.get("date")
        or ""
    )
    mid = match.get("id") or match.get("matchId")
    hid = home.get("id") if isinstance(home, dict) else 0
    aid = away.get("id") if isinstance(away, dict) else 0
    try:
        return {
            "fixture": {
                "date": date_s,
                "status": {"short": "FT"},
            },
            "teams": {
                "home": {"id": int(hid or 0), "name": home_name},
                "away": {"id": int(aid or 0), "name": away_name},
            },
            "goals": {"home": int(home_g), "away": int(away_g)},
            "_source": "fotmob_calendar",
        }
    except (TypeError, ValueError):
        return None


def _league_table_rows_from_inner(inner: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in ("all", "total", "home", "away"):
        block = inner.get(key)
        if isinstance(block, list) and block:
            return [r for r in block if isinstance(r, dict)]
    return []


def parse_league_standings_table(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract season standings rows (points, goals) from FotMob league payload."""
    table_blocks = payload.get("table")
    if not isinstance(table_blocks, list):
        return []
    rows: List[Dict[str, Any]] = []
    for block in table_blocks:
        if not isinstance(block, dict):
            continue
        data = block.get("data")
        if not isinstance(data, dict):
            continue
        inner = data.get("table")
        if not isinstance(inner, dict):
            continue
        part = _league_table_rows_from_inner(inner)
        if part:
            rows = part
            break
    out: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows, start=1):
        name = row.get("name") or row.get("shortName")
        if not name:
            continue
        try:
            played = int(row.get("played") or row.get("matches") or 0)
        except (TypeError, ValueError):
            played = 0
        try:
            pts = int(row.get("pts") or row.get("points") or 0)
        except (TypeError, ValueError):
            pts = 0
        try:
            gf = int(row.get("goals") or row.get("goalsFor") or row.get("goalsScored") or 0)
        except (TypeError, ValueError):
            gf = 0
        try:
            ga = int(row.get("goalsConceded") or row.get("goalsAgainst") or 0)
        except (TypeError, ValueError):
            ga = 0
        pos = row.get("idx") or row.get("index") or row.get("position") or idx
        try:
            pos_i = int(pos)
        except (TypeError, ValueError):
            pos_i = idx
        out.append(
            {
                "name": name,
                "shortName": row.get("shortName"),
                "id": row.get("id"),
                "position": pos_i,
                "played": played,
                "points": pts,
                "goals": gf,
                "goalsConceded": ga,
            }
        )
    return out


def row_to_season_stats(row: Dict[str, Any]) -> Dict[str, Any]:
    """Map a FotMob standings row into ``home_stats`` / ``away_stats`` shape."""
    try:
        played = int(row.get("played") or 0)
        gf = int(row.get("goals") or 0)
        ga = int(row.get("goalsConceded") or 0)
        pts = int(row.get("points") or 0)
        pos = int(row.get("position") or 0)
    except (TypeError, ValueError):
        return {}
    if played < 1 and gf <= 0 and ga <= 0:
        return {}
    return {
        "played": played,
        "goals_for": gf,
        "goals_against": ga,
        "points": pts,
        "position": pos if pos > 0 else None,
        "source": "fotmob_table",
    }


def team_season_stats_from_fotmob_league(
    league_code: str, team_name: str, *, cache: Optional[Cache] = None
) -> Dict[str, Any]:
    """Season GF/GA/position from FotMob league table when API stats are empty."""
    lid = primary_league_id(league_code)
    if lid is None or not team_name:
        return {}
    try:
        payload = fetch_league_data(lid, cache=cache)
        rows = parse_league_standings_table(payload)
        row = find_team_xg_row(rows, team_name)
        if not row:
            return {}
        return row_to_season_stats(row)
    except Exception:
        return {}


def team_recent_from_fotmob_calendar(
    league_code: str,
    team_name: str,
    *,
    lookback_days: int = 75,
    limit: int = 10,
    cache: Optional[Cache] = None,
) -> List[Dict[str, Any]]:
    """Last finished matches for a team from FotMob daily feeds (no API-Sports id required)."""
    from hibs_predictor.live_scores import _team_names_match

    code = (league_code or "").strip().upper()
    if not team_name or not code:
        return []
    if code == "INTL_FRIENDLIES":
        try:
            lookback_days = max(
                int(lookback_days),
                int(os.getenv("HIBS_FOTMOB_INTL_RECENT_DAYS", "120")),
            )
        except ValueError:
            lookback_days = 120
    cache = cache or Cache()
    end = date.today()
    start = end - timedelta(days=max(7, min(120, int(lookback_days))))
    try:
        raw_matches = fixtures_for_league(code, start, end, cache=cache)
    except Exception:
        return []
    finished: List[Dict[str, Any]] = []
    for m in raw_matches:
        norm = fotmob_match_to_recent_format(m)
        if not norm:
            continue
        th = (norm.get("teams") or {}).get("home") or {}
        ta = (norm.get("teams") or {}).get("away") or {}
        hn = str(th.get("name") or "")
        an = str(ta.get("name") or "")
        if not (_team_names_match(team_name, hn) or _team_names_match(team_name, an)):
            continue
        finished.append(norm)
    finished.sort(key=lambda x: str((x.get("fixture") or {}).get("date") or ""), reverse=True)
    return finished[: max(1, int(limit))]


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


# National-team friendlies: friendlies table is often thin — try Nations / WC / Euros xG tables next.
FOTMOB_NATIONAL_XG_FALLBACK_CODES: Tuple[str, ...] = (
    "INTL_FRIENDLIES",
    "NATIONS_LEAGUE",
    "WORLD_CUP",
    "EUROS",
)


def _resolve_xg_for_fotmob_code(
    league_code: str,
    home_name: str,
    away_name: str,
    *,
    cache: Optional[Cache] = None,
    force: bool = False,
    requested_code: Optional[str] = None,
) -> Optional[Tuple[float, float, Dict[str, Any]]]:
    if not force and not fotmob_xg_enabled(league_code):
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
        meta: Dict[str, Any] = {
            "league_id": lid,
            "home_n": hp.get("n"),
            "away_n": ap.get("n"),
            "home_avg_for": round(float(hp["avg_xg_for"]), 3),
            "away_avg_for": round(float(ap["avg_xg_for"]), 3),
        }
        req = (requested_code or league_code or "").strip().upper()
        if effective != req:
            meta["fotmob_league_fallback"] = effective
        return pair[0], pair[1], meta
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
    code = (league_code or "").strip().upper()
    if code == "INTL_FRIENDLIES":
        for alt in FOTMOB_NATIONAL_XG_FALLBACK_CODES:
            hit = _resolve_xg_for_fotmob_code(
                alt,
                home_name,
                away_name,
                cache=cache,
                force=(alt == "INTL_FRIENDLIES"),
                requested_code=code,
            )
            if hit:
                return hit
        return None
    return _resolve_xg_for_fotmob_code(code, home_name, away_name, cache=cache, requested_code=code)


def team_season_stats_from_national_fotmob(
    league_code: str, team_name: str, *, cache: Optional[Cache] = None
) -> Dict[str, Any]:
    """Season GF/GA for national teams — try competitive intl tables when friendlies table is empty."""
    code = (league_code or "").strip().upper()
    if code != "INTL_FRIENDLIES":
        return team_season_stats_from_fotmob_league(league_code, team_name, cache=cache)
    for alt in FOTMOB_NATIONAL_XG_FALLBACK_CODES:
        lid = primary_league_id(alt)
        if lid is None:
            continue
        try:
            payload = fetch_league_data(lid, cache=cache)
            rows = parse_league_standings_table(payload)
            row = find_team_xg_row(rows, team_name)
            if not row:
                continue
            stats = row_to_season_stats(row)
            if stats:
                stats.setdefault("source", "fotmob_table")
                if alt != code:
                    stats["fotmob_league_fallback"] = alt
                return stats
        except Exception:
            continue
    return {}


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


def _is_national_friendlies_league_name(name: str) -> bool:
    n = (name or "").lower()
    if "friendl" not in n:
        return False
    if "club" in n:
        return False
    return True


def fixtures_international_friendlies(
    start: date, end: date, *, cache: Optional[Cache] = None
) -> List[Dict[str, Any]]:
    """National-team friendly matches from FotMob daily feed (league name contains Friendlies)."""
    cache = cache or Cache()
    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for day in _date_range(start, end):
        payload = fetch_matches_for_date(day, cache=cache)
        for league in payload.get("leagues") or []:
            if not isinstance(league, dict):
                continue
            lname = str(league.get("name") or "")
            if not _is_national_friendlies_league_name(lname):
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
                    "name": lname,
                }
                rows.append(out)
    return rows


def fixtures_for_league(league_code: str, start: date, end: date, *, cache: Optional[Cache] = None) -> List[Dict[str, Any]]:
    """Extract FotMob match rows for a configured league over an inclusive date range."""
    code = (league_code or "").strip().upper()
    if code == "INTL_FRIENDLIES":
        return fixtures_international_friendlies(start, end, cache=cache)
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
