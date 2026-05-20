"""Sofascore public API (undocumented; may 403 without browser-like TLS — optional curl_cffi)."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import requests

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": "https://www.sofascore.com/",
}


def _env_on(name: str, default: str = "0") -> bool:
    return (os.getenv(name, default) or default).strip().lower() not in ("0", "false", "no", "off")


def sofascore_xg_enabled() -> bool:
    """Use SofaScore rolling xG when scrape xG is on and not explicitly disabled."""
    if not _env_on("HIBS_SCRAPE_XG", "1"):
        return False
    raw = (os.getenv("HIBS_ENABLE_SOFASCORE_XG") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    return _env_on("HIBS_MAX_DATA", "0")


def _http_get_json(url: str, *, params: Optional[Dict[str, Any]] = None, timeout: int = 15) -> Dict[str, Any]:
    try:
        from curl_cffi import requests as curl_requests  # type: ignore

        session = curl_requests.Session(impersonate="chrome120")
        r = session.get(url, params=params, headers=_HEADERS, timeout=timeout)
    except ImportError:
        r = requests.get(url, params=params, headers=_HEADERS, timeout=timeout)
    if r.status_code == 403:
        return {"_hibs_blocked": True, "_hibs_status": 403}
    r.raise_for_status()
    if not (r.headers.get("content-type") or "").startswith("application/json"):
        return {}
    data = r.json()
    return data if isinstance(data, dict) else {}


def probe_team_search(query: str) -> Tuple[Optional[Dict[str, Any]], bool]:
    """Return (team_entity, blocked_403) for health probes without raising."""
    data = _http_get_json("https://api.sofascore.com/api/v1/search/all", params={"q": query})
    if data.get("_hibs_blocked"):
        return None, True
    hit = None
    for block in data.get("results") or []:
        if block.get("type") != "team":
            continue
        entity = block.get("entity") or {}
        if entity.get("name"):
            hit = entity
            break
    return hit, False


def search_all(query: str, limit: int = 8) -> Dict[str, Any]:
    url = "https://api.sofascore.com/api/v1/search/all"
    data = _http_get_json(url, params={"q": query})
    if limit and isinstance(data.get("results"), list):
        data = {**data, "results": data["results"][:limit]}
    return data


def first_team_hit(query: str) -> Optional[Dict[str, Any]]:
    hit, _blocked = probe_team_search(query)
    return hit


def _parse_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        f = float(val)
        return f if f > 0.04 else None
    text = str(val).strip().replace("%", "")
    if not text:
        return None
    try:
        f = float(text)
    except ValueError:
        return None
    return f if f > 0.04 else None


def parse_xg_from_statistics_payload(data: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    """Extract home/away xG from /event/{id}/statistics or embedded statistics blocks."""
    stats_list = data.get("statistics")
    if not isinstance(stats_list, list):
        return None
    for block in stats_list:
        if not isinstance(block, dict):
            continue
        period = str(block.get("period") or "").upper()
        if period and period not in ("ALL", "FT", "FULLTIME", "MATCH"):
            continue
        groups = block.get("groups") or []
        for grp in groups:
            if not isinstance(grp, dict):
                continue
            for item in grp.get("statisticsItems") or []:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or item.get("key") or "").lower()
                if "expected" not in name or "goal" not in name:
                    continue
                xh = _parse_float(item.get("home"))
                xa = _parse_float(item.get("away"))
                if xh is not None and xa is not None:
                    return xh, xa
    return None


def extract_xg_from_event(event: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    """Try embedded statistics / score blocks on an event object."""
    if not isinstance(event, dict):
        return None
    embedded = event.get("statistics")
    if isinstance(embedded, list) and embedded:
        pair = parse_xg_from_statistics_payload({"statistics": embedded})
        if pair:
            return pair
    for side in ("homeScore", "awayScore"):
        blk = event.get(side)
        if isinstance(blk, dict):
            xg = _parse_float(blk.get("expectedGoals") or blk.get("xg"))
            if xg is not None:
                pass  # need both sides — handled below via statistics only
    return None


def fetch_event_statistics_xg(event_id: int) -> Optional[Tuple[float, float]]:
    url = f"https://api.sofascore.com/api/v1/event/{int(event_id)}/statistics"
    try:
        data = _http_get_json(url, timeout=12)
    except Exception:
        return None
    return parse_xg_from_statistics_payload(data)


def team_last_events(team_id: int, page: int = 0) -> List[Dict[str, Any]]:
    url = f"https://api.sofascore.com/api/v1/team/{int(team_id)}/events/last/{int(page)}"
    data = _http_get_json(url, timeout=15)
    evs = data.get("events") if isinstance(data, dict) else None
    return evs if isinstance(evs, list) else []


def team_last_xg_summary(team_id: int) -> List[Dict[str, Any]]:
    """Recent events for team (legacy shape for health probes)."""
    out: List[Dict[str, Any]] = []
    for e in team_last_events(team_id)[:10]:
        home = (e.get("homeTeam", {}) or {}).get("name")
        away = (e.get("awayTeam", {}) or {}).get("name")
        hx = e.get("homeScore", {})
        ax = e.get("awayScore", {})
        row: Dict[str, Any] = {
            "id": e.get("id"),
            "home": home,
            "away": away,
            "homeScore": hx,
            "awayScore": ax,
            "status": (e.get("status") or {}).get("type"),
        }
        xg = extract_xg_from_event(e)
        if not xg and e.get("id"):
            xg = fetch_event_statistics_xg(int(e["id"]))
        if xg:
            row["xg_home"] = xg[0]
            row["xg_away"] = xg[1]
        out.append(row)
    return out


def team_xg_profile(team_id: int, *, min_samples: int = 2, max_events: int = 8) -> Optional[Dict[str, Any]]:
    """
    Rolling average xG for and against from the team's last finished matches.
    Returns avg_xg_for, avg_xg_against, n (sample count).
    """
    tid = int(team_id)
    xg_for: List[float] = []
    xg_against: List[float] = []
    checked = 0
    for e in team_last_events(tid):
        if checked >= max_events:
            break
        status = str((e.get("status") or {}).get("type") or "").lower()
        if status not in ("finished", "ended", "afterpenalties", "afterextratime"):
            continue
        checked += 1
        home_team = (e.get("homeTeam") or {}) if isinstance(e.get("homeTeam"), dict) else {}
        away_team = (e.get("awayTeam") or {}) if isinstance(e.get("awayTeam"), dict) else {}
        home_id = int(home_team.get("id") or 0)
        away_id = int(away_team.get("id") or 0)
        pair = extract_xg_from_event(e)
        if not pair and e.get("id"):
            pair = fetch_event_statistics_xg(int(e["id"]))
        if not pair:
            continue
        xh, xa = pair
        if home_id == tid:
            xg_for.append(xh)
            xg_against.append(xa)
        elif away_id == tid:
            xg_for.append(xa)
            xg_against.append(xh)
    if len(xg_for) < min_samples:
        return None
    return {
        "avg_xg_for": sum(xg_for) / len(xg_for),
        "avg_xg_against": sum(xg_against) / len(xg_against),
        "n": len(xg_for),
        "team_id": tid,
    }


def team_xg_profile_for_name(team_name: str) -> Optional[Dict[str, Any]]:
    ent = first_team_hit(team_name)
    if not ent or not ent.get("id"):
        return None
    prof = team_xg_profile(int(ent["id"]))
    if prof:
        prof["team_name"] = ent.get("name") or team_name
    return prof
