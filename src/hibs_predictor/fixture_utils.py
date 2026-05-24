"""Normalize fixture dict shapes from API-Sports, Football-Data.org, FotMob, etc."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from hibs_predictor.scrapers.statsbomb_open import STATSBOMB_CUP_LEAGUES

_FINISHED_STATUSES = frozenset({"FT", "AET", "PEN", "AWD", "WO"})
_IN_PLAY_STATUSES = frozenset({"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"})


def display_competition_title(
    *,
    fallback_name: str,
    api_league_name: Optional[str] = None,
    api_round: Optional[str] = None,
    fotmob_league_name: Optional[str] = None,
    fdo_competition_name: Optional[str] = None,
) -> str:
    """Human-readable competition heading: prefer provider league/round over our configured league name."""
    fb = (fallback_name or "").strip() or "Fixture"
    prov = (
        (api_league_name or "").strip()
        or (fdo_competition_name or "").strip()
        or (fotmob_league_name or "").strip()
    )
    rnd = (api_round or "").strip()

    def _tidy(s: str) -> str:
        return " ".join(s.split()).replace(" - ", " — ")

    def _round_is_boring(r: str) -> bool:
        low = r.lower()
        if "regular season" in low:
            return True
        if re.match(r"^round\s+\d+$", low):
            return True
        return False

    def _round_is_special(r: str) -> bool:
        if not r or _round_is_boring(r):
            return False
        low = r.lower()
        return any(
            k in low
            for k in (
                "final",
                "semi",
                "quarter",
                "play-off",
                "playoff",
                "knockout",
                "qualif",
                "relegation",
                "promotion",
            )
        )

    # Knockout finals named by competition + final (e.g. Scottish Cup final).
    if prov and rnd:
        rlow = rnd.lower().strip()
        if "cup" in prov.lower() and (rlow == "final" or rlow.endswith(" final")):
            return _tidy(f"{prov} final")

    if rnd and _round_is_special(rnd):
        if prov and prov.lower() not in rnd.lower():
            return _tidy(f"{prov} — {rnd}")
        return _tidy(rnd)

    if prov and prov.lower() != fb.lower():
        return _tidy(prov)

    if prov:
        return _tidy(prov)

    return _tidy(fb)


def coerce_team_id(raw: Any) -> Optional[int]:
    """Normalize API/FDO team ids for comparisons and cache keys."""
    if raw is None or raw == "" or raw == 0:
        return None
    try:
        tid = int(raw)
        return tid if tid > 0 else None
    except (TypeError, ValueError):
        return None


def fixture_team_id(fixture: Dict[str, Any], side: str) -> Optional[int]:
    """Numeric team id from teams block when present."""
    teams = fixture.get("teams")
    if isinstance(teams, dict):
        blk = teams.get(side)
        if isinstance(blk, dict):
            tid = coerce_team_id(blk.get("id"))
            if tid is not None:
                return tid
    raw = fixture.get(side)
    if isinstance(raw, dict):
        return coerce_team_id(raw.get("id"))
    key = f"{side}_id"
    if fixture.get(key) is not None:
        return coerce_team_id(fixture.get(key))
    return None


def fixture_team_name(fixture: Dict[str, Any], side: str) -> str:
    """Return display name for home/away whether stored as dict, string, or under teams."""
    raw = fixture.get(side)
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, dict):
        return str(raw.get("name") or raw.get("shortName") or "").strip()
    teams = fixture.get("teams")
    if isinstance(teams, dict):
        blk = teams.get(side)
        if isinstance(blk, str):
            return blk.strip()
        if isinstance(blk, dict):
            return str(blk.get("name") or blk.get("shortName") or "").strip()
    return ""


def table_team_display(value: Any) -> str:
    """Render-safe team label from API dict or plain string."""
    if isinstance(value, dict):
        return str(
            value.get("name")
            or value.get("shortName")
            or value.get("teamName")
            or value.get("tla")
            or ""
        ).strip()
    return str(value or "").strip()


def normalize_position_rank(value: Any) -> Optional[int]:
    """Integer table rank; never pass through nested team dicts."""
    if isinstance(value, dict):
        if value.get("rank") is not None:
            n = _safe_int(value.get("rank"))
            return n if 0 < n < 500 else None
        inner = value.get("position")
        if inner is not None and not isinstance(inner, dict):
            n = _safe_int(inner)
            return n if 0 < n < 500 else None
        return None
    if value in (None, "", "?"):
        return None
    n = _safe_int(value)
    return n if 0 < n < 500 else None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def position_rank(pos: Any) -> Optional[int]:
    """Rank from a home/away position blob or bare rank."""
    if isinstance(pos, dict):
        rank = normalize_position_rank(pos.get("position", pos.get("rank")))
        if rank is not None:
            return rank
        return normalize_position_rank(pos.get("rank"))
    return normalize_position_rank(pos)


def position_points(pos: Any) -> Optional[int]:
    if not isinstance(pos, dict):
        return None
    pts = pos.get("points")
    if pts in (None, "", "?"):
        return None
    try:
        return int(pts)
    except (TypeError, ValueError):
        return None


def normalize_position_dict(pos: Any) -> Dict[str, Any]:
    """Sanitize standings blobs attached to fixtures for templates and insight text."""
    if not isinstance(pos, dict):
        return {}
    out = dict(pos)
    rank = normalize_position_rank(out.get("position", out.get("rank")))
    if rank is None:
        rank = normalize_position_rank(out.get("rank"))
    if rank is not None:
        out["position"] = rank
    elif "position" in out:
        out.pop("position", None)
    team_name = table_team_display(out.get("team"))
    if team_name:
        out["team"] = team_name
    tid = out.get("team_id")
    if tid is None and isinstance(pos.get("team"), dict):
        tid = coerce_team_id(pos.get("team", {}).get("id"))
    if tid is not None:
        out["team_id"] = coerce_team_id(tid)
    for key in ("played", "won", "drawn", "lost", "goals_for", "goals_against", "goal_diff", "points"):
        if key in out:
            out[key] = _safe_int(out.get(key))
    form = out.get("form")
    if form is not None and not isinstance(form, str):
        out["form"] = str(form)
    return out


def normalize_fixture_display(fixture: Dict[str, Any]) -> None:
    """Coerce home/away names and position blobs on a fixture row (mutates in place)."""
    home = fixture_team_name(fixture, "home")
    away = fixture_team_name(fixture, "away")
    if home:
        fixture["home"] = home
    if away:
        fixture["away"] = away
    fixture["home_position"] = normalize_position_dict(fixture.get("home_position"))
    fixture["away_position"] = normalize_position_dict(fixture.get("away_position"))


def fixture_status_short(fixture: Dict[str, Any]) -> str:
    """Best-effort short status (FT, 1H, NS, …)."""
    for key in ("fixture_status", "status_short"):
        raw = fixture.get(key)
        if raw:
            return str(raw).upper()
    fm = fixture.get("fixture")
    if isinstance(fm, dict):
        st = fm.get("status")
        if isinstance(st, dict) and st.get("short"):
            return str(st.get("short")).upper()
        if st:
            return str(st).upper()
    st = fixture.get("status")
    if isinstance(st, dict) and st.get("short"):
        return str(st.get("short")).upper()
    if st:
        return str(st).upper()
    return ""


def is_finished_fixture(fixture: Dict[str, Any]) -> bool:
    return fixture_status_short(fixture) in _FINISHED_STATUSES


def is_in_play_fixture(fixture: Dict[str, Any]) -> bool:
    if fixture.get("is_live"):
        return True
    return fixture_status_short(fixture) in _IN_PLAY_STATUSES


def is_cup_competition(league_code: Any) -> bool:
    return str(league_code or "").strip().upper() in STATSBOMB_CUP_LEAGUES


def cup_round_label(fixture: Dict[str, Any]) -> str:
    meta = fixture.get("competition_meta") if isinstance(fixture.get("competition_meta"), dict) else {}
    rnd = str(meta.get("api_round") or meta.get("round") or "").strip()
    if rnd and "regular season" not in rnd.lower():
        return rnd
    league = str(fixture.get("league_name") or fixture.get("league") or "").strip()
    return league or "Cup tie"


def table_form_inconsistent(position: Dict[str, Any], last10: List[Dict[str, Any]]) -> bool:
    """True when league rank and recent W/D/L form visibly disagree (display only)."""
    rank = position_rank(position)
    if rank is None or not last10:
        return False
    sample = last10[:5]
    wins = sum(1 for r in sample if r.get("result") == "W")
    losses = sum(1 for r in sample if r.get("result") == "L")
    if rank <= 6 and wins <= 1 and losses >= 3:
        return True
    if rank >= 14 and wins >= 3 and losses <= 1:
        return True
    return False


def goal_scorers_from_events(events: List[Dict[str, Any]]) -> List[str]:
    """Goal scorers from API-Football fixtures/events (real data only)."""
    out: List[str] = []
    for ev in events or []:
        detail = str(ev.get("detail") or "").lower()
        ev_type = str(ev.get("type") or "").lower()
        if "goal" not in detail and ev_type not in ("goal",):
            continue
        if "missed" in detail or "cancel" in detail:
            continue
        player = ((ev.get("player") or {}).get("name")) or ""
        team = ((ev.get("team") or {}).get("name")) or ""
        minute = (ev.get("time") or {}).get("elapsed")
        label = player or team
        if not label:
            continue
        if minute is not None:
            label = f"{label} {minute}'"
        out.append(label)
    return out


def format_goal_scorers_line(scorers: List[str], *, max_names: int = 4) -> str:
    if not scorers:
        return ""
    shown = scorers[:max_names]
    line = ", ".join(shown)
    if len(scorers) > max_names:
        line += f" +{len(scorers) - max_names}"
    return line
