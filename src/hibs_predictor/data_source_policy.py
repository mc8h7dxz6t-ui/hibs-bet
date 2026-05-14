"""
Rolling window for which external stats/scrapes may be used alongside APIs (hibs-bet).

Default: last ``HIBS_STATS_LOOKBACK_DAYS`` (183 ≈ 6 months) through ``now + HIBS_STATS_FUTURE_DAYS``
(14) for upcoming kickoffs. Optional ``HIBS_DATA_POLICY_AS_OF`` (ISO date/datetime) freezes the clock
for tests or what-if analysis (e.g. 2026-05-14).
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from dotenv import load_dotenv


def _as_of_utc() -> datetime:
    load_dotenv()
    raw = (os.getenv("HIBS_DATA_POLICY_AS_OF") or "").strip()
    if raw:
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def lookback_days() -> int:
    load_dotenv()
    try:
        return max(30, min(730, int(os.getenv("HIBS_STATS_LOOKBACK_DAYS", "183"))))
    except ValueError:
        return 183


def future_horizon_days() -> int:
    load_dotenv()
    try:
        return max(0, min(60, int(os.getenv("HIBS_STATS_FUTURE_DAYS", "14"))))
    except ValueError:
        return 14


def policy_window_utc() -> Tuple[datetime, datetime]:
    """Inclusive lower bound for history, upper bound for allowed upcoming fixtures."""
    now = _as_of_utc()
    lo = now - timedelta(days=lookback_days())
    hi = now + timedelta(days=future_horizon_days())
    return lo, hi


def policy_summary_dict() -> Dict[str, Any]:
    lo, hi = policy_window_utc()
    return {
        "as_of_utc": _as_of_utc().isoformat(),
        "lookback_days": lookback_days(),
        "future_horizon_days": future_horizon_days(),
        "window_start_utc": lo.isoformat(),
        "window_end_utc": hi.isoformat(),
    }


def parse_fixture_datetime_utc(fixture: Dict[str, Any]) -> Optional[datetime]:
    raw = fixture.get("date") or (fixture.get("fixture") or {}).get("date") or ""
    if not raw or not isinstance(raw, str):
        return None
    try:
        s = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


def fixture_in_policy_window(fixture: Dict[str, Any]) -> bool:
    """True if kickoff lies inside [now-lookback, now+future_horizon]."""
    dt = parse_fixture_datetime_utc(fixture)
    if not dt:
        return False
    lo, hi = policy_window_utc()
    return lo <= dt <= hi


def date_in_policy_window(d: date) -> bool:
    lo, hi = policy_window_utc()
    lo_d, hi_d = lo.date(), hi.date()
    return lo_d <= d <= hi_d
