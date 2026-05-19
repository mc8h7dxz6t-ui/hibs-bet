"""StatsBomb open-data JSON (CC-BY-NC-SA) — https://github.com/statsbomb/open-data

Use alongside API-Football for *historical* structure when a competition exists in the open
repository. Coverage by league/season varies; see ``data-sources-probe`` + ``summarize_matches_in_policy_window``.
"""

from datetime import date
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import requests

from hibs_predictor.cache import Cache

OPEN_BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

# (substring of StatsBomb competition_name, country_name filter)
STATSBOMB_LEAGUE_OPEN: Dict[str, Tuple[str, str]] = {
    "EPL": ("Premier League", "England"),
    "LA_LIGA": ("La Liga", "Spain"),
    "SERIE_A": ("Serie A", "Italy"),
    "BUNDESLIGA": ("Bundesliga", "Germany"),
    "LIGUE_1": ("Ligue 1", "France"),
    "CHAMPIONSHIP": ("Championship", "England"),
    "EREDIVISIE": ("Eredivisie", "Netherlands"),
    "PRIMEIRA": ("Primeira Liga", "Portugal"),
    "BELGIUM_FIRST": ("Pro League", "Belgium"),
}


def _season_sort_key(row: Dict[str, Any]) -> Tuple[int, int]:
    """Prefer latest calendar end year from ``season_name`` (e.g. 2020/2021 -> 2021)."""
    sn = str(row.get("season_name") or "")
    parts = sn.split("/")
    try:
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            y0, y1 = int(parts[0]), int(parts[1])
            y_end = max(y0, y1)
            return (y_end, int(row.get("season_id") or 0))
        if len(parts) == 1 and parts[0].isdigit():
            return (int(parts[0]), int(row.get("season_id") or 0))
    except ValueError:
        pass
    return (0, int(row.get("season_id") or 0))


@lru_cache(maxsize=1)
def load_competitions() -> List[Dict[str, Any]]:
    r = requests.get(f"{OPEN_BASE}/competitions.json", timeout=25)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def load_matches(competition_id: int, season_id: int) -> List[Dict[str, Any]]:
    r = requests.get(f"{OPEN_BASE}/matches/{competition_id}/{season_id}.json", timeout=35)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def find_match_by_team_names(
    matches: List[Dict[str, Any]],
    home_name: str,
    away_name: str,
) -> Dict[str, Any]:
    """Return first StatsBomb match where home/away team names match (case-insensitive substring)."""
    h = (home_name or "").lower().strip()
    a = (away_name or "").lower().strip()
    for m in matches:
        ht_obj = m.get("home_team") or {}
        at_obj = m.get("away_team") or {}
        ht = (ht_obj.get("home_team_name") or ht_obj.get("name") or "").lower()
        at = (at_obj.get("away_team_name") or at_obj.get("name") or "").lower()
        if not ht or not at:
            continue
        if (h in ht or ht in h) and (a in at or at in a):
            return m
    return {}


def latest_open_season_meta(league_code: str) -> Dict[str, Any]:
    """Best open-data season row for this hibs league code (male, non-youth)."""
    spec = STATSBOMB_LEAGUE_OPEN.get(league_code)
    if not spec:
        return {}
    name_sub, country = spec
    comps = load_competitions()
    rows = [
        c
        for c in comps
        if name_sub.lower() in str(c.get("competition_name") or "").lower()
        and str(c.get("country_name") or "") == country
        and c.get("competition_gender") == "male"
        and not c.get("competition_youth")
    ]
    if not rows:
        return {}
    best = max(rows, key=_season_sort_key)
    return {
        "competition_id": best.get("competition_id"),
        "season_id": best.get("season_id"),
        "season_name": best.get("season_name"),
        "match_updated": best.get("match_updated"),
        "competition_name": best.get("competition_name"),
    }


def _match_date(m: Dict[str, Any]) -> Optional[date]:
    raw = m.get("match_date")
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def summarize_matches_in_policy_window(league_code: str, d_lo: date, d_hi: date) -> Dict[str, Any]:
    """Count open-data matches whose ``match_date`` lies in [d_lo, d_hi] for latest SB season of league."""
    meta = latest_open_season_meta(league_code)
    cid, sid = meta.get("competition_id"), meta.get("season_id")
    if cid is None or sid is None:
        return {"ok": False, "note": "no_open_data_competition", "match_count_in_window": 0}
    try:
        matches = load_matches(int(cid), int(sid))
    except Exception as exc:
        return {"ok": False, "note": str(exc)[:120], "match_count_in_window": 0}
    n = 0
    latest: Optional[date] = None
    for m in matches or []:
        md = _match_date(m)
        if md and d_lo <= md <= d_hi:
            n += 1
            if latest is None or md > latest:
                latest = md
    return {
        "ok": True,
        "match_count_in_window": n,
        "open_data_season": f"{meta.get('competition_name')} {meta.get('season_name')}",
        "note": None
        if n
        else "No matches in policy window for this open-data season (dataset may end before your window).",
        "latest_match_date_in_window": latest.isoformat() if latest else None,
    }


def _team_name(m: Dict[str, Any], side: str) -> str:
    blk = m.get(f"{side}_team") or {}
    return str(blk.get(f"{side}_team_name") or blk.get("name") or "")


def team_proxy_from_open_matches(
    league_code: str,
    team_name: str,
    d_lo: date,
    d_hi: date,
    limit: int = 8,
) -> Dict[str, Any]:
    """
    Goals for/against from StatsBomb *matches* JSON only (no per-shot events download).

    Cached per (league, team, window day bucket).
    """
    cache = Cache()
    key = f"sb_team_proxy_{league_code}_{team_name[:40]}_{d_lo}_{d_hi}_{limit}"
    hit = cache.get(key, ttl_hours=12)
    if hit:
        return hit

    meta = latest_open_season_meta(league_code)
    cid, sid = meta.get("competition_id"), meta.get("season_id")
    out: Dict[str, Any] = {"ok": False, "matches_used": 0, "gf_pg": None, "ga_pg": None, "season": None}
    if cid is None or sid is None:
        cache.set(key, out, ttl_hours=12)
        return out
    try:
        matches = load_matches(int(cid), int(sid))
    except Exception as exc:
        out["error"] = str(exc)[:120]
        cache.set(key, out, ttl_hours=6)
        return out

    tn = (team_name or "").lower().strip()
    picked: List[Dict[str, Any]] = []
    for m in matches or []:
        md = _match_date(m)
        if not md or md < d_lo or md > d_hi:
            continue
        ht = _team_name(m, "home").lower()
        at = _team_name(m, "away").lower()
        if not ht or not at:
            continue
        if tn in ht or ht in tn or tn in at or at in tn:
            picked.append(m)
    picked.sort(key=lambda x: str(x.get("match_date") or ""), reverse=True)
    picked = picked[:limit]

    if not picked:
        out["season"] = f"{meta.get('competition_name')} {meta.get('season_name')}"
        cache.set(key, out, ttl_hours=12)
        return out

    gf = ga = 0
    for m in picked:
        md = _match_date(m)
        if not md:
            continue
        ht = _team_name(m, "home").lower()
        at = _team_name(m, "away").lower()
        hs = m.get("home_score")
        aws = m.get("away_score")
        try:
            hi, ai = int(hs), int(aws)
        except (TypeError, ValueError):
            continue
        if tn in ht or ht in tn:
            gf += hi
            ga += ai
        else:
            gf += ai
            ga += hi
    n_used = len(picked)
    out = {
        "ok": True,
        "matches_used": n_used,
        "gf_pg": round(gf / max(1, n_used), 3),
        "ga_pg": round(ga / max(1, n_used), 3),
        "season": f"{meta.get('competition_name')} {meta.get('season_name')}",
        "open_data_through": str(meta.get("match_updated") or ""),
    }
    cache.set(key, out, ttl_hours=12)
    return out


def load_events(match_id: int) -> List[Dict[str, Any]]:
    """Full event array for one match (large). Prefer caching at call site."""
    r = requests.get(f"{OPEN_BASE}/events/{int(match_id)}.json", timeout=45)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def summarize_shot_xg_from_events(match_id: int) -> Dict[str, Any]:
    """Aggregate StatsBomb shot ``statsbomb_xg`` when events file exists (single match)."""
    cache = Cache()
    key = f"sb_evsum_{match_id}"
    hit = cache.get(key, ttl_hours=24)
    if hit:
        return hit
    out: Dict[str, Any] = {"ok": False, "match_id": match_id, "shots": 0, "xg_total": None}
    try:
        evs = load_events(match_id)
    except Exception as exc:
        out["error"] = str(exc)[:120]
        cache.set(key, out, ttl_hours=6)
        return out
    xg_sum = 0.0
    n = 0
    for e in evs:
        if (e.get("type") or {}).get("name") != "Shot":
            continue
        shot = e.get("shot") or {}
        xg = shot.get("statsbomb_xg")
        if xg is None:
            continue
        try:
            xg_sum += float(xg)
            n += 1
        except (TypeError, ValueError):
            continue
    out = {"ok": True, "match_id": match_id, "shots": n, "xg_total": round(xg_sum, 4) if n else 0.0}
    cache.set(key, out, ttl_hours=24)
    return out
