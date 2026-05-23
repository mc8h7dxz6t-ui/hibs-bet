"""Confirmed lineup helpers — API-Football ``fixtures/lineups`` (Phase 2)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict

from hibs_predictor.team_news_enrich import (
    _norm_player_name,
    top_scorers_listed_absent,
)


class LineupPlayer(TypedDict, total=False):
    id: int
    name: str
    number: int
    pos: str


class ConfirmedLineup(TypedDict, total=False):
    formation: str
    start_xi: List[LineupPlayer]
    source: str
    confirmed_at: str


def _env_truthy(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def lineup_fetch_enabled(*, api_client_present: bool = True) -> bool:
    """True when lineup API calls are allowed (default on when API-Sports is loaded)."""
    if not api_client_present:
        return False
    if _env_truthy("HIBS_SKIP_API_LINEUPS"):
        return False
    raw = os.getenv("HIBS_ENABLE_LINEUP_FETCH", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    # Default on when API client is available (mirrors injuries when key present).
    return True


def _kickoff_utc(enriched: Dict[str, Any]) -> Optional[datetime]:
    raw = enriched.get("date")
    if not raw and isinstance(enriched.get("fixture"), dict):
        raw = enriched["fixture"].get("date")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def minutes_to_kickoff(
    enriched: Dict[str, Any],
    *,
    now: Optional[datetime] = None,
) -> Optional[float]:
    """Minutes until kickoff (negative after KO)."""
    kick = _kickoff_utc(enriched)
    if not kick:
        return None
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return (kick - now_utc).total_seconds() / 60.0


def should_fetch_lineups(
    enriched: Dict[str, Any],
    *,
    now: Optional[datetime] = None,
    api_client_present: bool = True,
) -> bool:
    """Pre-kickoff window only — do not poll live lineups after the match starts."""
    if not lineup_fetch_enabled(api_client_present=api_client_present):
        return False
    mins = minutes_to_kickoff(enriched, now=now)
    if mins is None:
        return False
    if mins < -15:
        return False
    try:
        max_hours = float(os.getenv("HIBS_LINEUP_FETCH_MAX_HOURS", "24"))
    except (TypeError, ValueError):
        max_hours = 24.0
    return mins <= max_hours * 60.0


def lineup_cache_ttl_hours(enriched: Dict[str, Any]) -> float:
    """Shorter TTL near kickoff; longer when lineups are still far out."""
    mins = minutes_to_kickoff(enriched)
    if mins is None:
        return 0.5
    if mins <= 90:
        return 0.25
    if mins <= 360:
        return 0.5
    if mins <= 24 * 60:
        return 2.0
    return 4.0


def _parse_start_xi(team_block: Dict[str, Any]) -> List[LineupPlayer]:
    start = team_block.get("startXI") or team_block.get("startXi") or []
    if not isinstance(start, list):
        return []
    out: List[LineupPlayer] = []
    for row in start:
        if not isinstance(row, dict):
            continue
        pl = row.get("player") if isinstance(row.get("player"), dict) else row
        if not isinstance(pl, dict):
            continue
        name = str(pl.get("name") or "").strip()
        if not name:
            continue
        entry: LineupPlayer = {"name": name}
        if pl.get("id") is not None:
            try:
                entry["id"] = int(pl["id"])
            except (TypeError, ValueError):
                pass
        if pl.get("number") is not None:
            try:
                entry["number"] = int(pl["number"])
            except (TypeError, ValueError):
                pass
        pos = pl.get("pos")
        if pos:
            entry["pos"] = str(pos)
        out.append(entry)
    return out


def _side_for_team_block(
    team_block: Dict[str, Any],
    *,
    home_id: Optional[int],
    away_id: Optional[int],
    home_name: str,
    away_name: str,
) -> Optional[str]:
    team = team_block.get("team") or {}
    tid = team.get("id")
    try:
        if home_id and tid and int(tid) == int(home_id):
            return "home"
        if away_id and tid and int(tid) == int(away_id):
            return "away"
    except (TypeError, ValueError):
        pass
    tname = str(team.get("name") or "").strip().lower()
    if tname:
        hn = home_name.strip().lower()
        an = away_name.strip().lower()
        if hn and (tname == hn or tname in hn or hn in tname):
            return "home"
        if an and (tname == an or tname in an or an in tname):
            return "away"
    return None


def parse_api_lineups(
    raw: List[Dict[str, Any]],
    *,
    home_id: Optional[int],
    away_id: Optional[int],
    home_name: str,
    away_name: str,
) -> Dict[str, Any]:
    """Normalize API-Football lineup rows into ``fixture_lineups`` + metadata."""
    home_lineup: Optional[ConfirmedLineup] = None
    away_lineup: Optional[ConfirmedLineup] = None
    now_iso = datetime.now(timezone.utc).isoformat()
    for block in raw or []:
        if not isinstance(block, dict):
            continue
        side = _side_for_team_block(
            block,
            home_id=home_id,
            away_id=away_id,
            home_name=home_name,
            away_name=away_name,
        )
        if side is None:
            continue
        xi = _parse_start_xi(block)
        if not xi:
            continue
        entry: ConfirmedLineup = {
            "formation": str(block.get("formation") or ""),
            "start_xi": xi,
            "source": "api_sports_lineups",
            "confirmed_at": now_iso,
        }
        if side == "home":
            home_lineup = entry
        else:
            away_lineup = entry
    fixture_lineups: Optional[Dict[str, ConfirmedLineup]] = None
    if home_lineup or away_lineup:
        fixture_lineups = {}
        if home_lineup:
            fixture_lineups["home"] = home_lineup
        if away_lineup:
            fixture_lineups["away"] = away_lineup
    home_n = len((home_lineup or {}).get("start_xi") or [])
    away_n = len((away_lineup or {}).get("start_xi") or [])
    confirmed = home_n >= 11 and away_n >= 11
    partial = (home_n >= 11 or away_n >= 11) and not confirmed
    return {
        "fixture_lineups": fixture_lineups,
        "lineup_confirmed": confirmed,
        "lineup_partial": partial,
        "home_xi_n": home_n,
        "away_xi_n": away_n,
    }


def _xi_name_set(lineup: Optional[ConfirmedLineup]) -> set[str]:
    if not lineup:
        return set()
    names: set[str] = set()
    for pl in lineup.get("start_xi") or []:
        if not isinstance(pl, dict):
            continue
        key = _norm_player_name(str(pl.get("name") or ""))
        if key:
            names.add(key)
    return names


def top_scorers_out_of_xi(
    top_scorers: List[Dict[str, Any]],
    xi_names: set[str],
    *,
    injuries: List[Dict[str, Any]],
    side: str,
    home_name: str,
    away_name: str,
    home_id: Optional[int],
    away_id: Optional[int],
) -> List[Dict[str, Any]]:
    """Top scorers not in the confirmed starting XI (no guessing when XI empty)."""
    if not xi_names or not top_scorers:
        return []
    injury_absent = top_scorers_listed_absent(
        top_scorers,
        injuries,
        side=side,
        home_name=home_name,
        away_name=away_name,
        home_id=home_id,
        away_id=away_id,
    )
    injury_names = {_norm_player_name(str(r.get("name") or "")) for r in injury_absent}
    out: List[Dict[str, Any]] = []
    for row in top_scorers:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        key = _norm_player_name(name)
        if not key or key in xi_names:
            continue
        entry: Dict[str, Any] = {"name": name, "goals": row.get("goals")}
        if key in injury_names:
            entry["on_injury_feed"] = True
        out.append(entry)
    return out


def apply_lineup_fields(
    enriched: Dict[str, Any],
    *,
    raw_lineups: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Set ``fixture_lineups``, ``lineup_confirmed``, and ``lineup_meta``.

    When ``raw_lineups`` is supplied (API response), parse starting XIs and cross-check
    league top scorers. Never invents players — only uses confirmed API data.
    """
    home_name = str(enriched.get("home") or "")
    away_name = str(enriched.get("away") or "")
    home_id = enriched.get("home_id")
    away_id = enriched.get("away_id")
    injuries = enriched.get("fixture_injuries") or []
    if not isinstance(injuries, list):
        injuries = []

    parsed: Dict[str, Any] = {
        "fixture_lineups": enriched.get("fixture_lineups"),
        "lineup_confirmed": bool(enriched.get("lineup_confirmed")),
        "lineup_partial": False,
        "home_xi_n": 0,
        "away_xi_n": 0,
    }
    if raw_lineups is not None:
        parsed = parse_api_lineups(
            raw_lineups,
            home_id=home_id,
            away_id=away_id,
            home_name=home_name,
            away_name=away_name,
        )

    enriched["fixture_lineups"] = parsed.get("fixture_lineups")
    enriched["lineup_confirmed"] = bool(parsed.get("lineup_confirmed"))
    meta: Dict[str, Any] = dict(enriched.get("lineup_meta") or {})
    meta["home_xi_n"] = int(parsed.get("home_xi_n") or 0)
    meta["away_xi_n"] = int(parsed.get("away_xi_n") or 0)
    meta["lineup_partial"] = bool(parsed.get("lineup_partial"))
    meta["source"] = "api_sports_lineups" if parsed.get("fixture_lineups") else meta.get("source")

    if enriched["lineup_confirmed"]:
        fl = enriched["fixture_lineups"] or {}
        home_xi = _xi_name_set(fl.get("home"))
        away_xi = _xi_name_set(fl.get("away"))
        home_scorers = enriched.get("home_top_scorers") or []
        away_scorers = enriched.get("away_top_scorers") or []
        if isinstance(home_scorers, list) and home_scorers and home_xi:
            meta["home_scorers_out_of_xi"] = top_scorers_out_of_xi(
                home_scorers,
                home_xi,
                injuries=injuries,
                side="home",
                home_name=home_name,
                away_name=away_name,
                home_id=home_id,
                away_id=away_id,
            )
        if isinstance(away_scorers, list) and away_scorers and away_xi:
            meta["away_scorers_out_of_xi"] = top_scorers_out_of_xi(
                away_scorers,
                away_xi,
                injuries=injuries,
                side="away",
                home_name=home_name,
                away_name=away_name,
                home_id=home_id,
                away_id=away_id,
            )
        if fl.get("home"):
            meta["home_formation"] = (fl["home"] or {}).get("formation") or ""
        if fl.get("away"):
            meta["away_formation"] = (fl["away"] or {}).get("formation") or ""

    enriched["lineup_meta"] = meta
    return enriched


def lineup_confidence_multiplier(fixture: Dict[str, Any]) -> float:
    """
    Display-only confidence scale when XI is unconfirmed near kickoff.

    Does not alter λ — mirrors motivation / injury split (engine vs display).
    """
    if not _env_truthy("HIBS_LINEUP_CONFIDENCE_PENALTY", "1"):
        return 1.0
    if fixture.get("lineup_confirmed"):
        return 1.0
    mins = minutes_to_kickoff(fixture)
    if mins is None:
        return 1.0
    try:
        window = float(os.getenv("HIBS_LINEUP_CONFIDENCE_WINDOW_MIN", "120"))
    except (TypeError, ValueError):
        window = 120.0
    if mins > window or mins < 0:
        return 1.0
    try:
        floor = float(os.getenv("HIBS_LINEUP_CONFIDENCE_FLOOR", "0.94"))
    except (TypeError, ValueError):
        floor = 0.94
    return max(0.85, min(1.0, floor))
