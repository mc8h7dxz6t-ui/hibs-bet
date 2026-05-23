"""Tournament / international focus mode (World Cup window, env-driven).

When active, fixture fetch is limited to international competition codes (fewer API
calls on VPS) and the dashboard defaults to the International region filter.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from hibs_predictor.config import ALL_LEAGUE_CODES, DASHBOARD_LEAGUE_ORDER

# Fetch + display priority during focus (World Cup first, then Nations, then Euros).
INTERNATIONAL_FOCUS_LEAGUE_CODES = [
    "WORLD_CUP",
    "NATIONS_LEAGUE",
    "EUROS",
]

_DEFAULT_AUTO_START = date(2026, 5, 15)
_DEFAULT_AUTO_END = date(2026, 7, 31)


def _env_truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def _parse_date(raw: str) -> Optional[date]:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _auto_window() -> tuple[date, date]:
    start = _parse_date(os.getenv("HIBS_TOURNAMENT_FOCUS_START", "")) or _DEFAULT_AUTO_START
    end = _parse_date(os.getenv("HIBS_TOURNAMENT_FOCUS_END", "")) or _DEFAULT_AUTO_END
    if end < start:
        start, end = end, start
    return start, end


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _focus_explicitly_disabled() -> bool:
    raw = (os.getenv("HIBS_TOURNAMENT_FOCUS") or "").strip().lower()
    return raw in ("0", "false", "no", "off", "none", "disabled")


def _mode_from_env_raw(raw: str) -> Optional[str]:
    if raw in ("worldcup", "world_cup", "wc", "fifa"):
        return "worldcup"
    if raw in ("euros", "euro", "ec"):
        return "euros"
    if raw in ("international", "intl", "nations"):
        return "international"
    if raw in ("1", "true", "yes", "on"):
        return "worldcup"
    return None


def tournament_focus_mode(*, today: Optional[date] = None) -> Optional[str]:
    """Active focus slug (worldcup / euros / international) or None when off."""
    if _focus_explicitly_disabled():
        return None

    raw = (os.getenv("HIBS_TOURNAMENT_FOCUS") or "").strip().lower()
    mode = _mode_from_env_raw(raw)
    if mode:
        return mode
    if _env_truthy("HIBS_FOCUS_INTERNATIONAL"):
        return "international"

    if raw:
        return None

    cur = today if today is not None else _today_utc()
    start, end = _auto_window()
    if start <= cur <= end:
        return "worldcup"
    return None


def tournament_focus_active(*, today: Optional[date] = None) -> bool:
    return tournament_focus_mode(today=today) is not None


def tournament_focus_label(*, today: Optional[date] = None) -> str:
    mode = tournament_focus_mode(today=today)
    if mode == "worldcup":
        return "World Cup focus"
    if mode == "euros":
        return "Euros focus"
    if mode == "international":
        return "International focus"
    return ""


def dashboard_default_region(*, today: Optional[date] = None) -> str:
    return "international" if tournament_focus_active(today=today) else ""


def league_codes_for_fetch(*, today: Optional[date] = None) -> List[str]:
    if tournament_focus_active(today=today):
        return list(INTERNATIONAL_FOCUS_LEAGUE_CODES)
    return list(ALL_LEAGUE_CODES)


def effective_dashboard_league_order(*, today: Optional[date] = None) -> List[str]:
    if tournament_focus_active(today=today):
        return list(INTERNATIONAL_FOCUS_LEAGUE_CODES)
    return list(DASHBOARD_LEAGUE_ORDER)


def prioritize_fixtures_for_focus(
    fixtures: List[Dict[str, Any]],
    *,
    today: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """International fixtures first for assistant / summaries when focus is on."""
    if not tournament_focus_active(today=today):
        return list(fixtures or [])
    intl = set(INTERNATIONAL_FOCUS_LEAGUE_CODES)
    primary: List[Dict[str, Any]] = []
    secondary: List[Dict[str, Any]] = []
    for row in fixtures or []:
        if str(row.get("league") or "") in intl:
            primary.append(row)
        else:
            secondary.append(row)
    order = {code: i for i, code in enumerate(INTERNATIONAL_FOCUS_LEAGUE_CODES)}
    primary.sort(
        key=lambda f: (
            order.get(str(f.get("league") or ""), 99),
            f.get("kickoff_sort") or f.get("date") or "",
        )
    )
    secondary.sort(key=lambda f: f.get("kickoff_sort") or f.get("date") or "")
    return primary + secondary


def tournament_focus_context(*, today: Optional[date] = None) -> Dict[str, Any]:
    active = tournament_focus_active(today=today)
    mode = tournament_focus_mode(today=today) or ""
    start, end = _auto_window()
    return {
        "active": active,
        "mode": mode,
        "label": tournament_focus_label(today=today) if active else "",
        "default_region": dashboard_default_region(today=today),
        "fetch_leagues": list(INTERNATIONAL_FOCUS_LEAGUE_CODES) if active else [],
        "auto_window_start": start.isoformat(),
        "auto_window_end": end.isoformat(),
    }
