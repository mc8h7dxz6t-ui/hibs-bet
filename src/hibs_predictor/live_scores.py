"""In-play scores from API-Football ``fixtures?live=all`` with short TTL caching."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from hibs_predictor.cache import Cache

IN_PLAY_STATUSES = frozenset({"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"})
FINISHED_STATUSES = frozenset({"FT", "AET", "PEN", "AWD", "WO", "ABD", "CANC", "PST"})

_LIVE_CACHE_KEY = "api_sports_live_all_v1"
_EVENTS_CACHE_PREFIX = "api_sports_fixture_events_"


def live_cache_ttl_hours() -> float:
    try:
        sec = int(os.getenv("HIBS_LIVE_CACHE_SEC", "45"))
    except ValueError:
        sec = 45
    sec = max(15, min(120, sec))
    return sec / 3600.0


def _max_event_fetches() -> int:
    try:
        return max(0, min(12, int(os.getenv("HIBS_LIVE_MAX_EVENT_FETCHES", "6"))))
    except ValueError:
        return 6


def parse_api_fixture_live(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize one API-Football fixture row into dashboard live fields."""
    fm = raw.get("fixture") if isinstance(raw.get("fixture"), dict) else {}
    status = fm.get("status") if isinstance(fm.get("status"), dict) else {}
    short = str(status.get("short") or "").upper()
    goals = raw.get("goals") if isinstance(raw.get("goals"), dict) else {}
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
    }


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


def _xg_from_statistics(stats_response: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Extract expected goals from fixtures/statistics when provider returns them."""
    if not stats_response or len(stats_response) < 2:
        return None
    out: Dict[str, Any] = {}
    for side in stats_response:
        team_name = ((side.get("team") or {}).get("name")) or ""
        for row in side.get("statistics") or []:
            typ = str(row.get("type") or "").lower()
            if "expected" in typ and "goal" in typ:
                key = "home" if not out.get("home") else "away"
                if not out.get("home"):
                    out["home"] = {"team": team_name, "xg": row.get("value")}
                else:
                    out["away"] = {"team": team_name, "xg": row.get("value")}
    return out or None


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


def _enrich_live_events(
    client: Any,
    live_by_id: Dict[int, Dict[str, Any]],
    cache: Cache,
    *,
    max_fetches: Optional[int] = None,
) -> None:
    limit = _max_event_fetches() if max_fetches is None else max(0, max_fetches)
    if limit <= 0:
        return
    ids = [fid for fid, row in live_by_id.items() if row.get("is_live")][:limit]
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


def merge_live_into_fixtures(
    fixtures: List[Dict[str, Any]],
    live_by_id: Dict[int, Dict[str, Any]],
) -> int:
    """Attach live_* fields to dashboard rows. Returns count of rows marked in-play."""
    merged = 0
    for row in fixtures:
        fid = row.get("id")
        try:
            fid_int = int(fid)
        except (TypeError, ValueError):
            continue
        live = live_by_id.get(fid_int)
        if not live:
            row.setdefault("is_live", False)
            continue
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
        ):
            if key in live and live[key] is not None:
                row[key] = live[key]
        if live.get("is_live"):
            merged += 1
    return merged


def attach_live_to_fixtures(
    fixtures: List[Dict[str, Any]],
    aggregator: Any,
    *,
    include_events: bool = True,
) -> int:
    """Fetch live snapshot and merge into fixture rows."""
    client = (getattr(aggregator, "clients", None) or {}).get("api_sports")
    if not client:
        return 0
    cache = Cache()
    live_by_id = fetch_live_by_id(client, cache=cache)
    if include_events and live_by_id:
        _enrich_live_events(client, live_by_id, cache)
    return merge_live_into_fixtures(fixtures, live_by_id)


def live_payload_for_ids(
    aggregator: Any,
    fixture_ids: List[int],
    *,
    include_events: bool = True,
    include_stats: bool = False,
) -> Dict[str, Any]:
    """JSON-serializable live slice for ``/api/fixtures/live`` polling."""
    client = (getattr(aggregator, "clients", None) or {}).get("api_sports")
    if not client:
        return {"fixtures": {}, "poll_after_sec": int(os.getenv("HIBS_LIVE_POLL_SEC", "60"))}

    cache = Cache()
    live_by_id = fetch_live_by_id(client, cache=cache)
    want = {int(i) for i in fixture_ids if i is not None}
    subset = {fid: dict(row) for fid, row in live_by_id.items() if fid in want and row.get("is_live")}

    if include_events and subset:
        _enrich_live_events(client, subset, cache)

    if include_stats and subset:
        for fid in list(subset.keys())[: _max_event_fetches()]:
            if not client.rate_limiter.check_rate_limit("api_sports"):
                break
            data = client._get_json("fixtures/statistics", params={"fixture": fid}, use_cache=False)
            resp = data.get("response") if isinstance(data.get("response"), list) else []
            xg = _xg_from_statistics(resp)
            if xg:
                subset[fid]["live_stats"] = xg

    out: Dict[str, Dict[str, Any]] = {}
    for fid, row in subset.items():
        out[str(fid)] = {
            k: row.get(k)
            for k in (
                "is_live",
                "live_status",
                "live_status_long",
                "live_minute",
                "live_score",
                "live_score_home",
                "live_score_away",
                "live_last_event",
                "live_stats",
            )
            if row.get(k) is not None
        }
    try:
        poll_sec = int(os.getenv("HIBS_LIVE_POLL_SEC", "60"))
    except ValueError:
        poll_sec = 60
    poll_sec = max(30, min(120, poll_sec))
    return {"fixtures": out, "poll_after_sec": poll_sec, "live_count": len(out)}


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
