"""Squad depth from API-Football ``players/squads`` (Transfermarkt alternative).

Read-only, 24h team cache, display + supplemental context only — no invented weights.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


def _squad_depth_enabled() -> bool:
    if os.getenv("HIBS_SKIP_API_SQUAD_DEPTH", "0").strip().lower() in ("1", "true", "yes", "on"):
        return False
    raw = (os.getenv("HIBS_ENABLE_API_SQUAD_DEPTH") or "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def summarize_squad_players(players: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Position counts from API-Football squad rows."""
    positions: Dict[str, int] = {}
    for row in players or []:
        if not isinstance(row, dict):
            continue
        pos = str(row.get("position") or "Unknown").strip() or "Unknown"
        positions[pos] = positions.get(pos, 0) + 1
    return {
        "size": len([p for p in (players or []) if isinstance(p, dict)]),
        "positions": positions,
        "source": "api_football",
    }


def attach_api_squad_depth(
    enriched: Dict[str, Any],
    api_client: Any,
    *,
    season: Optional[int] = None,
) -> Dict[str, Any]:
    """Fetch cached squad lists for both sides; merge into team_news_meta."""
    if not _squad_depth_enabled():
        return enriched
    home_id = enriched.get("home_id")
    away_id = enriched.get("away_id")
    if not home_id and not away_id:
        return enriched

    def _fetch(team_id: Optional[int]) -> Optional[Dict[str, Any]]:
        if not team_id:
            return None
        try:
            players = api_client.fetch_team_squad(int(team_id), season=season)
        except Exception:
            return None
        if not players:
            return None
        return summarize_squad_players(players)

    home_sq = _fetch(home_id)
    away_sq = _fetch(away_id)
    if home_sq:
        enriched["home_squad_depth"] = home_sq
    if away_sq:
        enriched["away_squad_depth"] = away_sq
    if not home_sq and not away_sq:
        return enriched

    meta = enriched.get("team_news_meta")
    if not isinstance(meta, dict):
        meta = {}
    injuries = enriched.get("fixture_injuries") or []
    if home_sq:
        meta["home_squad"] = home_sq
        ha = int(meta.get("home_absences") or 0)
        if home_sq.get("size"):
            meta["home_absence_pct"] = round(min(1.0, ha / max(1, int(home_sq["size"]))), 3)
    if away_sq:
        meta["away_squad"] = away_sq
        aa = int(meta.get("away_absences") or 0)
        if away_sq.get("size"):
            meta["away_absence_pct"] = round(min(1.0, aa / max(1, int(away_sq["size"]))), 3)
    enriched["team_news_meta"] = meta
    return enriched
