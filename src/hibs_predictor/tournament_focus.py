"""Tournament / international focus mode (World Cup window, date-driven).

Default (no ``HIBS_TOURNAMENT_FOCUS``): domestic leagues outside **2026-06-01 →
2026-07-18**; international focus ON inside that window (UTC calendar).

``HIBS_TOURNAMENT_FOCUS=worldcup`` (or ``euros`` / ``international``) forces focus
on anytime. ``HIBS_TOURNAMENT_FOCUS=0`` forces domestic even inside the window.

When active, fixture fetch defaults to international competition codes only (fewer
API calls on VPS) and the dashboard defaults to the International region filter.
Pass ``include_domestic=True`` (dashboard ``?domestic=1``) to fetch all leagues when
the user picks All / UK / European region chips.
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

# Optional during World Cup window (API-Football league 10); not in base list until enabled.
INTL_FRIENDLIES_CODE = "INTL_FRIENDLIES"

_DEFAULT_AUTO_START = date(2026, 6, 1)
_DEFAULT_AUTO_END = date(2026, 7, 18)
# International friendlies window (pre-World Cup block through tournament end).
_DEFAULT_FRIENDLIES_AUTO_START = date(2026, 5, 20)


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


def _friendlies_window() -> tuple[date, date]:
    """Calendar range when INTL_FRIENDLIES are included in international focus fetch."""
    start = (
        _parse_date(os.getenv("HIBS_FRIENDLIES_FOCUS_START", ""))
        or _DEFAULT_FRIENDLIES_AUTO_START
    )
    _, end = _auto_window()
    if end < start:
        start, end = end, start
    return start, end


def friendlies_window_active(*, today: Optional[date] = None) -> bool:
    cur = today if today is not None else _today_utc()
    start, end = _friendlies_window()
    return start <= cur <= end


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


def _friendlies_in_focus(*, today: Optional[date] = None) -> bool:
    """Include international friendlies in international focus fetch lists."""
    if _env_truthy("HIBS_TOURNAMENT_INCLUDE_FRIENDLIES"):
        return True
    if friendlies_window_active(today=today):
        return True
    return tournament_focus_mode(today=today) == "worldcup"


def international_focus_league_codes(*, today: Optional[date] = None) -> List[str]:
    """League codes fetched when tournament focus is on and domestic is excluded."""
    codes = list(INTERNATIONAL_FOCUS_LEAGUE_CODES)
    if _friendlies_in_focus(today=today) and INTL_FRIENDLIES_CODE not in codes:
        codes.insert(1, INTL_FRIENDLIES_CODE)
    return codes


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
    if tournament_focus_active(today=today) or friendlies_window_active(today=today):
        return "international"
    return ""


def league_codes_for_fetch(
    *,
    today: Optional[date] = None,
    include_domestic: bool = False,
) -> List[str]:
    if tournament_focus_active(today=today) and not include_domestic:
        return international_focus_league_codes(today=today)
    return list(ALL_LEAGUE_CODES)


def effective_dashboard_league_order(
    *,
    today: Optional[date] = None,
    include_domestic: bool = False,
) -> List[str]:
    if tournament_focus_active(today=today) and not include_domestic:
        return international_focus_league_codes(today=today)
    return list(DASHBOARD_LEAGUE_ORDER)


def prioritize_fixtures_for_focus(
    fixtures: List[Dict[str, Any]],
    *,
    today: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """International fixtures first for assistant / summaries when focus or friendlies window is on."""
    if not tournament_focus_active(today=today) and not friendlies_window_active(today=today):
        return list(fixtures or [])
    intl = set(international_focus_league_codes(today=today))
    primary: List[Dict[str, Any]] = []
    secondary: List[Dict[str, Any]] = []
    for row in fixtures or []:
        if str(row.get("league") or "") in intl:
            primary.append(row)
        else:
            secondary.append(row)
    order = {code: i for i, code in enumerate(international_focus_league_codes(today=today))}
    primary.sort(
        key=lambda f: (
            order.get(str(f.get("league") or ""), 99),
            f.get("kickoff_sort") or f.get("date") or "",
        )
    )
    secondary.sort(key=lambda f: f.get("kickoff_sort") or f.get("date") or "")
    return primary + secondary


def tournament_focus_context(
    *,
    today: Optional[date] = None,
    include_domestic: bool = False,
) -> Dict[str, Any]:
    active = tournament_focus_active(today=today)
    mode = tournament_focus_mode(today=today) or ""
    start, end = _auto_window()
    fr_start, fr_end = _friendlies_window()
    intl_only = active and not include_domestic
    return {
        "active": active,
        "mode": mode,
        "label": tournament_focus_label(today=today) if active else "",
        "default_region": dashboard_default_region(today=today),
        "fetch_leagues": list(league_codes_for_fetch(today=today, include_domestic=include_domestic)),
        "include_friendlies": _friendlies_in_focus(today=today),
        "friendlies_window_active": friendlies_window_active(today=today),
        "intl_only_fetch": intl_only,
        "auto_window_start": start.isoformat(),
        "auto_window_end": end.isoformat(),
        "friendlies_window_start": fr_start.isoformat(),
        "friendlies_window_end": fr_end.isoformat(),
    }
