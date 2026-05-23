"""Data-source coverage notes for upcoming seasons.

This is product-facing source audit metadata, not scraper configuration. Keep it
honest: only mark a source as wired when the app uses it today.
"""

from __future__ import annotations

from typing import Any, Dict, List

from hibs_predictor.scrapers.source_registry import SOURCE_CATALOG


SEASON_COVERAGE: List[Dict[str, Any]] = [
    {
        "season": "2025/26",
        "status": "active",
        "summary": "Primary coverage comes from API-Football plus Football-Data.org fixture and standings fallbacks; FotMob can fill selected empty fixture calendars experimentally, with odds and side markets when bookmaker feeds expose them.",
        "strengths": [
            "Fixtures, standings, team stats, recent form, injuries and 1X2 odds for API-supported leagues.",
            "Understat, FBref, SoccerStats, SofaScore, FotMob and recent-match xG paths fill gaps where the source supports the league.",
            "Season candidates include the active domestic season and previous-season standings fallback for awkward or completed fixture windows.",
        ],
        "shortcomings": [
            "No player-prop feed is wired, so assistants and builders must not suggest player shots/cards/scorers.",
            "xG depth varies by league; lower divisions may fall back to goals proxy or recent-match estimates.",
            "Cup, international and summer windows can have sparse standings or team-stat context; unsupported or unstable public sites remain metadata-only.",
        ],
    },
    {
        "season": "2026/27",
        "status": "future-ready",
        "summary": "The rolling season resolver will move domestic API requests into 2026 once the calendar passes July, but source availability depends on providers publishing schedules and tables.",
        "strengths": [
            "Fixture fetchers try current and previous season ids so early-season windows can still resolve.",
            "Policy-window scrapers are date-gated, making them safe to use as new fixtures enter the app window.",
            "Data-quality scoring exposes missing table, xG, odds and side-market blocks per fixture.",
        ],
        "shortcomings": [
            "Provider season ids can lag before fixtures are officially published.",
            "FBref/SoccerStats season pages may not exist or may change layout at rollover.",
            "Historical xG sources may not cover promoted clubs or new competitions immediately.",
        ],
    },
]


def assistant_data_policy() -> Dict[str, Any]:
    """Guards for betting assistant surfaces — snapshot fields only."""
    return {
        "no_invented_stats": True,
        "no_placeholder_odds": True,
        "no_default_btts_pct": True,
        "no_player_props": True,
        "refusal_when_snapshot_empty": True,
        "note": (
            "Assistants and bet builders use only live fixture packets (odds, model %, xG, form, "
            "injuries, rationale_metrics). Missing fields yield 'not enough data' — never fabricated picks."
        ),
    }


def data_coverage_status() -> Dict[str, Any]:
    """Return source audit metadata for UI/API surfaces."""
    wired = [s for s in SOURCE_CATALOG if s.get("status") == "wired"]
    experimental = [s for s in SOURCE_CATALOG if s.get("status") == "experimental"]
    planned = [s for s in SOURCE_CATALOG if s.get("status") == "planned"]
    return {
        "seasons": SEASON_COVERAGE,
        "sources": SOURCE_CATALOG,
        "counts": {
            "wired": len(wired),
            "experimental": len(experimental),
            "planned": len(planned),
        },
        "no_player_props": True,
        "player_prop_note": "No player-prop source is wired; bet builders are limited to real 1X2, BTTS, totals and double-chance markets when priced.",
        "assistant": assistant_data_policy(),
    }
