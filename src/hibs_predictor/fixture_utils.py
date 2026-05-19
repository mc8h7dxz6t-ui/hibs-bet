"""Normalize fixture dict shapes from API-Sports, Football-Data.org, FotMob, etc."""

from __future__ import annotations

from typing import Any, Dict


def fixture_team_id(fixture: Dict[str, Any], side: str) -> Optional[int]:
    """Numeric team id from teams block when present."""
    teams = fixture.get("teams")
    if isinstance(teams, dict):
        blk = teams.get(side)
        if isinstance(blk, dict):
            tid = blk.get("id")
            try:
                return int(tid) if tid not in (None, "", 0) else None
            except (TypeError, ValueError):
                return None
    raw = fixture.get(side)
    if isinstance(raw, dict):
        try:
            tid = raw.get("id")
            return int(tid) if tid not in (None, "", 0) else None
        except (TypeError, ValueError):
            return None
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
