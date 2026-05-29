"""Per-league API enrichment gap metrics for /api/health and dashboard ops."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List


def _has_injuries(row: Dict[str, Any]) -> bool:
    inj = row.get("fixture_injuries")
    if isinstance(inj, list) and len(inj) > 0:
        return True
    home_inj = row.get("home_injuries") or row.get("injuries_home")
    away_inj = row.get("away_injuries") or row.get("injuries_away")
    return bool(home_inj or away_inj)


def _has_top_scorers(row: Dict[str, Any]) -> bool:
    h = row.get("home_top_scorers") or []
    a = row.get("away_top_scorers") or []
    return bool(h or a)


def _has_lineup_signal(row: Dict[str, Any]) -> bool:
    if row.get("lineup_confirmed"):
        return True
    fl = row.get("fixture_lineups")
    if isinstance(fl, dict) and (fl.get("home") or fl.get("away")):
        return True
    return False


def compute_league_api_gaps(fixtures: List[Dict[str, Any]], *, top_n: int = 24) -> List[Dict[str, Any]]:
    """
    Summarise missing injuries, topscorers, and lineup context per league code.

    Returns rows sorted by fixture count descending.
    """
    buckets: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {
            "fixtures": 0,
            "missing_injuries": 0,
            "missing_top_scorers": 0,
            "missing_lineup": 0,
        }
    )
    for row in fixtures or []:
        if not isinstance(row, dict):
            continue
        code = str(row.get("league") or "UNKNOWN").upper()
        b = buckets[code]
        b["fixtures"] += 1
        if not _has_injuries(row):
            b["missing_injuries"] += 1
        if not _has_top_scorers(row):
            b["missing_top_scorers"] += 1
        if not _has_lineup_signal(row):
            b["missing_lineup"] += 1

    out: List[Dict[str, Any]] = []
    for league, counts in buckets.items():
        n = max(1, int(counts["fixtures"]))
        out.append(
            {
                "league": league,
                "fixtures": counts["fixtures"],
                "missing_injuries": counts["missing_injuries"],
                "missing_injuries_pct": round(100.0 * counts["missing_injuries"] / n, 1),
                "missing_top_scorers": counts["missing_top_scorers"],
                "missing_top_scorers_pct": round(100.0 * counts["missing_top_scorers"] / n, 1),
                "missing_lineup": counts["missing_lineup"],
                "missing_lineup_pct": round(100.0 * counts["missing_lineup"] / n, 1),
            }
        )
    out.sort(key=lambda r: (-int(r["fixtures"]), str(r["league"])))
    return out[: max(1, top_n)]
