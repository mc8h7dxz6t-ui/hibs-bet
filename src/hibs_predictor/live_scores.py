"""In-play scores from API-Football ``fixtures?live=all`` with short TTL caching."""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from hibs_predictor.cache import Cache
from hibs_predictor.config import LEAGUES

IN_PLAY_STATUSES = frozenset({"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"})
FINISHED_STATUSES = frozenset({"FT", "AET", "PEN", "AWD", "WO", "ABD", "CANC", "PST"})

_LIVE_CACHE_KEY = "api_sports_live_all_v2"
_EVENTS_CACHE_PREFIX = "api_sports_fixture_events_"
_STATS_CACHE_PREFIX = "api_sports_fixture_statistics_"

_STAT_TYPE_MAP = {
    "shots on goal": "shots_on",
    "shots off goal": "shots_off",
    "total shots": "total_shots",
    "blocked shots": "blocked_shots",
    "ball possession": "possession",
    "corner kicks": "corners",
    "fouls": "fouls",
    "offsides": "offsides",
    "expected goals": "xg",
    "expected_goals": "xg",
}

_STAT_ROW_LABELS = (
    ("shots_on", "Shots on goal"),
    ("total_shots", "Total shots"),
    ("possession", "Possession"),
    ("corners", "Corners"),
    ("xg", "Expected goals (xG)"),
)

_API_LEAGUE_ID_TO_CODE: Optional[Dict[int, str]] = None


def live_cache_ttl_hours() -> float:
    try:
        sec = int(os.getenv("HIBS_LIVE_CACHE_SEC", "45"))
    except ValueError:
        sec = 45
    sec = max(15, min(120, sec))
    return sec / 3600.0


def stats_cache_ttl_hours() -> float:
    try:
        sec = int(os.getenv("HIBS_LIVE_STATS_CACHE_SEC", "50"))
    except ValueError:
        sec = 50
    sec = max(45, min(60, sec))
    return sec / 3600.0


def _max_event_fetches() -> int:
    try:
        return max(0, min(12, int(os.getenv("HIBS_LIVE_MAX_EVENT_FETCHES", "6"))))
    except ValueError:
        return 6


def _max_stats_fetches() -> int:
    try:
        return max(0, min(15, int(os.getenv("HIBS_LIVE_MAX_STATS_FETCHES", "10"))))
    except ValueError:
        return 10


def _api_league_id_to_code() -> Dict[int, str]:
    global _API_LEAGUE_ID_TO_CODE
    if _API_LEAGUE_ID_TO_CODE is None:
        mapping: Dict[int, str] = {}
        for code, league in LEAGUES.items():
            aid = league.get("api_sports_id")
            if aid is not None:
                mapping[int(aid)] = code
        _API_LEAGUE_ID_TO_CODE = mapping
    return _API_LEAGUE_ID_TO_CODE


def _normalize_team(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip().lower())


def _team_names_match(a: str, b: str) -> bool:
    """Loose match for provider naming (e.g. SC Freiburg vs Freiburg, LOI clubs)."""
    from hibs_predictor.team_aliases import team_names_match

    return team_names_match(a, b)


def _stat_type_key(stat_type: str) -> Optional[str]:
    return _STAT_TYPE_MAP.get(str(stat_type or "").strip().lower())


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().rstrip("%")
    if not text or text == "-":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_api_fixture_live(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize one API-Football fixture row into dashboard live fields."""
    fm = raw.get("fixture") if isinstance(raw.get("fixture"), dict) else {}
    status = fm.get("status") if isinstance(fm.get("status"), dict) else {}
    short = str(status.get("short") or "").upper()
    goals = raw.get("goals") if isinstance(raw.get("goals"), dict) else {}
    teams = raw.get("teams") if isinstance(raw.get("teams"), dict) else {}
    league = raw.get("league") if isinstance(raw.get("league"), dict) else {}
    home_team = (teams.get("home") or {}).get("name") or ""
    away_team = (teams.get("away") or {}).get("name") or ""
    api_league_id = league.get("id")
    league_code = None
    if api_league_id is not None:
        try:
            league_code = _api_league_id_to_code().get(int(api_league_id))
        except (TypeError, ValueError):
            league_code = None
    home_g = goals.get("home")
    away_g = goals.get("away")
    elapsed = status.get("elapsed")
    is_live = short in IN_PLAY_STATUSES
    live_score = None
    if home_g is not None and away_g is not None:
        live_score = f"{home_g}-{away_g}"
    return {
        "fixture_id": fm.get("id"),
        "is_live": is_live,
        "live_status": short or None,
        "live_status_long": status.get("long") or short or None,
        "live_minute": elapsed if elapsed is not None else None,
        "live_score_home": home_g,
        "live_score_away": away_g,
        "live_score": live_score,
        "live_last_event": None,
        "live_stats": None,
        "live_xg_home": None,
        "live_xg_away": None,
        "_match_home": home_team,
        "_match_away": away_team,
        "_match_league_code": league_code,
    }


def parse_live_statistics(
    stats_response: List[Dict[str, Any]],
    *,
    home_name: Optional[str] = None,
    away_name: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[float], Optional[float]]:
    """Parse fixtures/statistics into home/away metrics, display rows, and xG floats."""
    if not stats_response or len(stats_response) < 2:
        return None, None, None

    parsed_sides: List[Dict[str, Any]] = []
    for side in stats_response[:2]:
        team_name = ((side.get("team") or {}).get("name")) or ""
        metrics: Dict[str, Any] = {"team": team_name}
        for row in side.get("statistics") or []:
            key = _stat_type_key(str(row.get("type") or ""))
            if key:
                metrics[key] = row.get("value")
        parsed_sides.append(metrics)

    home_side = parsed_sides[0]
    away_side = parsed_sides[1]
    if home_name and away_name:
        norm_home = _normalize_team(home_name)
        norm_away = _normalize_team(away_name)
        for side in parsed_sides:
            tn = _normalize_team(side.get("team") or "")
            if tn == norm_home:
                home_side = side
            elif tn == norm_away:
                away_side = side

    rows: List[Dict[str, Any]] = []
    for field, label in _STAT_ROW_LABELS:
        hv = home_side.get(field)
        av = away_side.get(field)
        if hv is None and av is None:
            continue
        rows.append({"label": label, "home": hv, "away": av})

    xg_home = _to_float(home_side.get("xg"))
    xg_away = _to_float(away_side.get("xg"))
    stats = {
        "home": home_side,
        "away": away_side,
        "rows": rows,
    }
    return stats, xg_home, xg_away


def _last_event_from_response(events: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not events:
        return None
    last = events[-1]
    team = ((last.get("team") or {}).get("name")) or ""
    player = ((last.get("player") or {}).get("name")) or ""
    assist = ((last.get("assist") or {}).get("name")) or ""
    elapsed = (last.get("time") or {}).get("elapsed")
    detail = str(last.get("detail") or last.get("type") or "").strip()
    label_parts = []
    if elapsed is not None:
        label_parts.append(f"{elapsed}'")
    if detail:
        label_parts.append(detail)
    if player:
        label_parts.append(player)
    if assist and detail.lower().find("goal") >= 0:
        label_parts.append(f"(ast {assist})")
    if team and not player:
        label_parts.append(team)
    label = " · ".join(label_parts) if label_parts else None
    if not label:
        return None
    return {
        "minute": elapsed,
        "type": last.get("type"),
        "detail": detail,
        "player": player or None,
        "team": team or None,
        "label": label,
    }


def _apply_stats_to_live_row(
    live_row: Dict[str, Any],
    stats_response: List[Dict[str, Any]],
    *,
    home_name: Optional[str] = None,
    away_name: Optional[str] = None,
) -> None:
    stats, xg_home, xg_away = parse_live_statistics(
        stats_response,
        home_name=home_name or live_row.get("_match_home"),
        away_name=away_name or live_row.get("_match_away"),
    )
    if stats:
        live_row["live_stats"] = stats
    if xg_home is not None:
        live_row["live_xg_home"] = xg_home
    if xg_away is not None:
        live_row["live_xg_away"] = xg_away


def fetch_live_by_id(client: Any, cache: Optional[Cache] = None) -> Dict[int, Dict[str, Any]]:
    """``fixtures?live=all`` mapped by fixture id (short TTL, respects rate limiter)."""
    cache = cache or Cache()
    cached = cache.get(_LIVE_CACHE_KEY, ttl_hours=live_cache_ttl_hours())
    if isinstance(cached, dict):
        return cached

    if not getattr(client, "rate_limiter", None) or not client.rate_limiter.check_rate_limit("api_sports"):
        return {}

    data = client._get_json("fixtures", params={"live": "all"}, use_cache=False)
    by_id: Dict[int, Dict[str, Any]] = {}
    for raw in data.get("response") or []:
        if not isinstance(raw, dict):
            continue
        parsed = parse_api_fixture_live(raw)
        fid = parsed.get("fixture_id")
        try:
            fid_int = int(fid)
        except (TypeError, ValueError):
            continue
        by_id[fid_int] = parsed

    cache.set(_LIVE_CACHE_KEY, by_id, ttl_hours=live_cache_ttl_hours())
    return by_id


def _build_team_league_index(live_by_id: Dict[int, Dict[str, Any]]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    index: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for row in live_by_id.values():
        if not row.get("is_live"):
            continue
        home = _normalize_team(row.get("_match_home") or "")
        away = _normalize_team(row.get("_match_away") or "")
        league = str(row.get("_match_league_code") or "")
        if home and away:
            index[(home, away, league)] = row
    return index


def _build_team_only_index(live_by_id: Dict[int, Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    index: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in live_by_id.values():
        if not row.get("is_live"):
            continue
        home = _normalize_team(row.get("_match_home") or "")
        away = _normalize_team(row.get("_match_away") or "")
        if home and away:
            index[(home, away)] = row
    return index


def _resolve_live_for_fixture(
    row: Dict[str, Any],
    live_by_id: Dict[int, Dict[str, Any]],
    team_index: Dict[Tuple[str, str, str], Dict[str, Any]],
    team_only_index: Dict[Tuple[str, str], Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    fid = row.get("id")
    try:
        fid_int = int(fid)
    except (TypeError, ValueError):
        fid_int = None
    if fid_int is not None and fid_int in live_by_id:
        return live_by_id[fid_int]
    home = _normalize_team(str(row.get("home") or ""))
    away = _normalize_team(str(row.get("away") or ""))
    league = str(row.get("league") or "")
    if home and away:
        hit = team_index.get((home, away, league))
        if hit:
            return hit
        if league:
            hit = team_index.get((home, away, ""))
            if hit:
                return hit
        exact = team_only_index.get((home, away))
        if exact:
            return exact
        for (lh, la), live_row in team_only_index.items():
            if _team_names_match(home, lh) and _team_names_match(away, la):
                return live_row
            if _team_names_match(home, la) and _team_names_match(away, lh):
                return live_row
    return None


def _enrich_live_events(
    client: Any,
    live_by_id: Dict[int, Dict[str, Any]],
    cache: Cache,
    *,
    max_fetches: Optional[int] = None,
    fixture_ids: Optional[List[int]] = None,
) -> None:
    limit = _max_event_fetches() if max_fetches is None else max(0, max_fetches)
    if limit <= 0:
        return
    ids = [fid for fid, row in live_by_id.items() if row.get("is_live")]
    if fixture_ids is not None:
        want = set(fixture_ids)
        ids = [fid for fid in ids if fid in want]
    ids = ids[:limit]
    for fid in ids:
        ck = f"{_EVENTS_CACHE_PREFIX}{fid}"
        events = cache.get(ck, ttl_hours=live_cache_ttl_hours())
        if events is None:
            if not client.rate_limiter.check_rate_limit("api_sports"):
                break
            data = client._get_json("fixtures/events", params={"fixture": fid}, use_cache=False)
            events = data.get("response") if isinstance(data.get("response"), list) else []
            cache.set(ck, events, ttl_hours=live_cache_ttl_hours())
        if events:
            live_by_id[fid]["live_last_event"] = _last_event_from_response(events)


def _enrich_live_statistics(
    client: Any,
    live_by_id: Dict[int, Dict[str, Any]],
    cache: Cache,
    *,
    fixture_rows: Optional[List[Dict[str, Any]]] = None,
    max_fetches: Optional[int] = None,
) -> None:
    limit = _max_stats_fetches() if max_fetches is None else max(0, max_fetches)
    if limit <= 0:
        return

    row_by_id: Dict[int, Dict[str, Any]] = {}
    if fixture_rows:
        for row in fixture_rows:
            try:
                row_by_id[int(row["id"])] = row
            except (TypeError, ValueError, KeyError):
                pass

    ids = [fid for fid, live in live_by_id.items() if live.get("is_live")]
    if row_by_id:
        ids = [fid for fid in ids if fid in row_by_id]
    ids = ids[:limit]

    for fid in ids:
        ck = f"{_STATS_CACHE_PREFIX}{fid}"
        stats_response = cache.get(ck, ttl_hours=stats_cache_ttl_hours())
        if stats_response is None:
            if not client.rate_limiter.check_rate_limit("api_sports"):
                break
            data = client._get_json("fixtures/statistics", params={"fixture": fid}, use_cache=False)
            stats_response = data.get("response") if isinstance(data.get("response"), list) else []
            cache.set(ck, stats_response, ttl_hours=stats_cache_ttl_hours())
        if not stats_response:
            continue
        dash = row_by_id.get(fid) if row_by_id else None
        _apply_stats_to_live_row(
            live_by_id[fid],
            stats_response,
            home_name=str(dash.get("home") or "") if dash else None,
            away_name=str(dash.get("away") or "") if dash else None,
        )


def _copy_live_fields(row: Dict[str, Any], live: Dict[str, Any]) -> None:
    for key in (
        "is_live",
        "live_status",
        "live_status_long",
        "live_minute",
        "live_score_home",
        "live_score_away",
        "live_score",
        "live_last_event",
        "live_stats",
        "live_xg_home",
        "live_xg_away",
    ):
        if key in live and live[key] is not None:
            row[key] = live[key]


def merge_live_into_fixtures(
    fixtures: List[Dict[str, Any]],
    live_by_id: Dict[int, Dict[str, Any]],
) -> int:
    """Attach live_* fields to dashboard rows. Returns count of rows marked in-play."""
    merged = 0
    team_index = _build_team_league_index(live_by_id)
    team_only_index = _build_team_only_index(live_by_id)
    for row in fixtures:
        live = _resolve_live_for_fixture(row, live_by_id, team_index, team_only_index)
        if not live:
            row.setdefault("is_live", False)
            continue
        _copy_live_fields(row, live)
        if live.get("is_live"):
            merged += 1
    return merged


def attach_live_to_fixtures(
    fixtures: List[Dict[str, Any]],
    aggregator: Any,
    *,
    include_events: bool = True,
    include_stats: bool = True,
) -> int:
    """Fetch live snapshot and merge into fixture rows."""
    client = (getattr(aggregator, "clients", None) or {}).get("api_sports")
    if not client:
        return 0
    cache = Cache()
    live_by_id = fetch_live_by_id(client, cache=cache)
    if not live_by_id:
        return 0
    if include_events:
        _enrich_live_events(client, live_by_id, cache, fixture_rows=fixtures)
    if include_stats:
        _enrich_live_statistics(client, live_by_id, cache, fixture_rows=fixtures)
    return merge_live_into_fixtures(fixtures, live_by_id)


_LIVE_PAYLOAD_KEYS = (
    "is_live",
    "live_status",
    "live_status_long",
    "live_minute",
    "live_score",
    "live_score_home",
    "live_score_away",
    "live_last_event",
    "live_stats",
    "live_xg_home",
    "live_xg_away",
)


def live_payload_for_ids(
    aggregator: Any,
    fixture_ids: List[int],
    *,
    include_events: bool = True,
    include_stats: bool = True,
    fixture_rows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """JSON-serializable live slice for ``/api/fixtures/live`` polling."""
    client = (getattr(aggregator, "clients", None) or {}).get("api_sports")
    if not client:
        return {"fixtures": {}, "poll_after_sec": int(os.getenv("HIBS_LIVE_POLL_SEC", "60"))}

    cache = Cache()
    live_by_id = fetch_live_by_id(client, cache=cache)
    want = {int(i) for i in fixture_ids if i is not None}
    rows_by_id: Dict[int, Dict[str, Any]] = {}
    for r in fixture_rows or []:
        try:
            rows_by_id[int(r["id"])] = r
        except (TypeError, ValueError, KeyError):
            continue
    team_index = _build_team_league_index(live_by_id)
    team_only_index = _build_team_only_index(live_by_id)

    by_dashboard_id: Dict[int, Dict[str, Any]] = {}
    api_rows_by_id: Dict[int, Dict[str, Any]] = {}
    for fid_int in want:
        dash_row = rows_by_id.get(fid_int)
        live = None
        if fid_int in live_by_id and live_by_id[fid_int].get("is_live"):
            live = live_by_id[fid_int]
        elif dash_row:
            live = _resolve_live_for_fixture(dash_row, live_by_id, team_index, team_only_index)
        if not live or not live.get("is_live"):
            continue
        live_copy = dict(live)
        by_dashboard_id[fid_int] = live_copy
        try:
            api_fid = int(live_copy.get("fixture_id") or fid_int)
        except (TypeError, ValueError):
            api_fid = fid_int
        api_rows_by_id[api_fid] = live_copy

    if include_events and api_rows_by_id:
        _enrich_live_events(client, api_rows_by_id, cache, fixture_ids=list(api_rows_by_id.keys()))

    if include_stats and api_rows_by_id:
        rows_for_stats = fixture_rows if fixture_rows else [{"id": fid} for fid in by_dashboard_id]
        _enrich_live_statistics(client, api_rows_by_id, cache, fixture_rows=rows_for_stats)

    out: Dict[str, Dict[str, Any]] = {}
    for fid, row in by_dashboard_id.items():
        out[str(fid)] = {k: row.get(k) for k in _LIVE_PAYLOAD_KEYS if row.get(k) is not None}
    try:
        poll_sec = int(os.getenv("HIBS_LIVE_POLL_SEC", "60"))
    except ValueError:
        poll_sec = 60
    poll_sec = max(30, min(120, poll_sec))
    return {"fixtures": out, "poll_after_sec": poll_sec, "live_count": len(by_dashboard_id)}


def fixture_ids_likely_in_play(fixtures: List[Dict[str, Any]], *, now: Optional[datetime] = None) -> List[int]:
    """Fixture ids that may need polling (started within lookback, not clearly finished)."""
    now = now or datetime.now(timezone.utc)
    lookback = timedelta(hours=3)
    ids: List[int] = []
    for row in fixtures:
        if row.get("is_live"):
            try:
                ids.append(int(row["id"]))
            except (TypeError, ValueError):
                pass
            continue
        status = str(row.get("live_status") or "").upper()
        if status in FINISHED_STATUSES:
            continue
        raw = row.get("kickoff_sort") or row.get("date")
        if not raw:
            continue
        try:
            ko = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except (TypeError, ValueError, OSError):
            continue
        if ko.tzinfo is None:
            ko = ko.replace(tzinfo=timezone.utc)
        if ko <= now <= ko + lookback:
            try:
                ids.append(int(row["id"]))
            except (TypeError, ValueError):
                pass
    return ids
