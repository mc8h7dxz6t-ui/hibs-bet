"""Normalize fixture dict shapes from API-Sports, Football-Data.org, FotMob, etc."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional


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
        return str(raw.get("name") or "").strip()
    teams = fixture.get("teams")
    if isinstance(teams, dict):
        blk = teams.get(side)
        if isinstance(blk, str):
            return blk.strip()
        if isinstance(blk, dict):
            return str(blk.get("name") or "").strip()
    return ""
