"""Domestic API-Football season id and calendar-year league helpers."""

from __future__ import annotations

import os
from datetime import datetime
from typing import List, Optional

from dotenv import load_dotenv

# Spring–autumn leagues: API-Football season id is the calendar year (e.g. 2026 in May 2026).
CALENDAR_YEAR_LEAGUES = frozenset(
    {
        "NORWAY_ELITESERIEN",
        "FINLAND_VEIKKAUSLIIGA",
    }
)


def api_football_season_year(now: Optional[datetime] = None) -> int:
    """
    Return the active Jul-based domestic season id.

    Override with ``HIBS_CURRENT_SEASON`` (integer year, e.g. 2025) for tests or
    early-season provider lag; otherwise uses calendar month >= July → ``year`` else ``year - 1``.
    """
    load_dotenv()
    raw = (os.getenv("HIBS_CURRENT_SEASON") or "").strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    d = now or datetime.now()
    return d.year if d.month >= 7 else d.year - 1


def season_candidates(
    now: Optional[datetime] = None,
    *,
    league_code: Optional[str] = None,
) -> List[int]:
    """
    Season years to try for standings, form, and enrich (current first).

    Jul-based leagues: primary Jul id + previous year.
    Calendar-year leagues (Nordics): prefer ``now.year`` before Jul id when month < 7.
    """
    d = now or datetime.now()
    primary = api_football_season_year(d)
    out = [primary, primary - 1]
    code = (league_code or "").strip().upper()
    if code in CALENDAR_YEAR_LEAGUES and d.month < 7 and d.year not in out:
        out.insert(0, d.year)
    return out


def fbref_season_labels(league_code: str, now: Optional[datetime] = None) -> List[str]:
    """FBref schedule URL season segments to try (most likely first)."""
    d = now or datetime.now()
    code = (league_code or "").strip().upper()
    if code in CALENDAR_YEAR_LEAGUES:
        y = d.year
        labels = [str(y)]
        if d.month < 3:
            labels.append(str(y - 1))
        elif y - 1 not in labels:
            labels.append(str(y - 1))
        return labels
    if d.month >= 7:
        return [f"{d.year}-{d.year + 1}"]
    return [f"{d.year - 1}-{d.year}"]
