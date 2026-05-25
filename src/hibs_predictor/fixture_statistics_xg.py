"""Budgeted API-Football ``fixtures/statistics`` xG for fixtures without measured xG."""

from __future__ import annotations

import os
from typing import Any, Optional, Tuple

from hibs_predictor.prediction_log import parse_result_xg_from_statistics

MEASURED_XG_SOURCES = frozenset(
    {
        "api_fixture_xg",
        "stats_api_xg",
        "api_statistics_xg",
    }
)

# Season blend from API team stats is useful xG; do not spend fixtures/statistics budget on it.
SEASON_XG_SOURCES = frozenset(
    {
        "api_season_team_xg",
        "team_season_xg",
    }
)

_statistics_budget_remaining: Optional[int] = None


def reset_statistics_xg_budget() -> None:
    """Call at the start of each dashboard fixture refresh cycle."""
    global _statistics_budget_remaining
    _statistics_budget_remaining = None


def fixture_statistics_xg_enabled() -> bool:
    return (os.getenv("HIBS_FETCH_FIXTURE_STATISTICS_XG") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def max_statistics_fetches_per_refresh() -> int:
    raw = (os.getenv("HIBS_FETCH_FIXTURE_STATISTICS_XG_MAX") or "24").strip()
    try:
        return max(0, min(80, int(raw)))
    except ValueError:
        return 24


def needs_statistics_xg_fetch(xg_source: Any) -> bool:
    s = str(xg_source or "").strip().lower()
    if s in MEASURED_XG_SOURCES or s in SEASON_XG_SOURCES:
        return False
    return True


def _take_budget() -> bool:
    global _statistics_budget_remaining
    if _statistics_budget_remaining is None:
        _statistics_budget_remaining = max_statistics_fetches_per_refresh()
    if _statistics_budget_remaining <= 0:
        return False
    _statistics_budget_remaining -= 1
    return True


def fetch_fixture_statistics_xg(
    api_client: Any,
    cache: Any,
    fixture_id: int,
    *,
    home_team_id: Optional[int] = None,
    away_team_id: Optional[int] = None,
    home_name: Optional[str] = None,
    away_name: Optional[str] = None,
    current_source: str = "",
) -> Optional[Tuple[float, float, str]]:
    """
    One API ``fixtures/statistics`` call when the fixture still lacks measured xG.
    Returns (xg_home, xg_away, ``api_statistics_xg``) or None.
    """
    if not fixture_statistics_xg_enabled():
        return None
    if not needs_statistics_xg_fetch(current_source):
        return None
    if not api_client or not fixture_id:
        return None
    if not _take_budget():
        return None

    cache_key = f"api_fixture_statistics_xg_{int(fixture_id)}"
    cached = cache.get(cache_key, ttl_hours=12.0)
    if isinstance(cached, (list, tuple)) and len(cached) >= 3:
        try:
            return float(cached[0]), float(cached[1]), str(cached[2])
        except (TypeError, ValueError):
            pass

    fetch_fn = getattr(api_client, "fetch_fixture_statistics", None)
    if not callable(fetch_fn):
        return None
    try:
        stats = fetch_fn(int(fixture_id), ttl_hours=12.0)
    except TypeError:
        stats = fetch_fn(int(fixture_id))
    except Exception:
        return None

    xh, xa = parse_result_xg_from_statistics(
        stats,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_name=home_name,
        away_name=away_name,
    )
    if xh is None or xa is None or xh <= 0.04 or xa <= 0.04:
        return None

    out: Tuple[float, float, str] = (float(xh), float(xa), "api_statistics_xg")
    cache.set(cache_key, out, ttl_hours=12.0)
    return out
