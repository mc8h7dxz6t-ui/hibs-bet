"""Kick-off display in a configurable local timezone (default Europe/London)."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore


def display_timezone() -> ZoneInfo:
    name = (os.getenv("HIBS_DISPLAY_TIMEZONE") or "Europe/London").strip() or "Europe/London"
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Europe/London")


def display_tz_label() -> str:
    key = getattr(display_timezone(), "key", "Europe/London")
    if key == "Europe/London":
        return "UK"
    if "/" in key:
        return key.split("/", 1)[1].replace("_", " ")
    return key


def parse_kickoff_utc(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def attach_kickoff_display(fixture: Dict[str, Any]) -> Dict[str, Any]:
    """Add kickoff_time (HH:MM local), kickoff_day_local (YYYY-MM-DD local), kickoff_sort (UTC ISO)."""
    out = dict(fixture)
    dt_utc = parse_kickoff_utc(out.get("date"))
    if not dt_utc:
        out["kickoff_time"] = "—"
        out["kickoff_day_local"] = ""
        out["kickoff_sort"] = "9999"
        return out
    local = dt_utc.astimezone(display_timezone())
    out["kickoff_time"] = local.strftime("%H:%M")
    out["kickoff_day_local"] = local.strftime("%Y-%m-%d")
    out["kickoff_sort"] = dt_utc.isoformat()
    return out


def enrich_fixtures_kickoff(fixtures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [attach_kickoff_display(f) for f in fixtures]


def local_today() -> date:
    return datetime.now(display_timezone()).date()


def fixture_window_start_utc(now: Optional[datetime] = None) -> datetime:
    """Start of the display-TZ calendar day in UTC — keeps today's kick-offs visible after KO."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(display_timezone())
    start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_local.astimezone(timezone.utc)


def fixture_window_end_utc(now: Optional[datetime] = None, days: int = 5) -> datetime:
    """End of the display-TZ calendar day `days` ahead — includes late kick-offs on the last day."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(display_timezone())
    end_day = local.date() + timedelta(days=max(0, int(days)))
    end_local = datetime(
        end_day.year, end_day.month, end_day.day, 23, 59, 59, tzinfo=local.tzinfo
    )
    return end_local.astimezone(timezone.utc)


def day_heading_for_local_date(day_iso: str, fixture_count: int, today_local: Optional[date] = None) -> str:
    today_local = today_local or local_today()
    try:
        d = date.fromisoformat(day_iso)
    except ValueError:
        return f"{day_iso} · {fixture_count} fixtures"
    day_mon = f"{d.day} {d.strftime('%b')}"
    if d == today_local:
        return f"Today • {day_mon} · {fixture_count} fixtures"
    if d == today_local + timedelta(days=1):
        return f"Tomorrow • {day_mon} · {fixture_count} fixtures"
    return f"{d.strftime('%a')} • {day_mon} · {fixture_count} fixtures"
