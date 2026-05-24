"""Documented xG resolution order for /status and ops (matches production aggregator wiring)."""

from __future__ import annotations

import os
from typing import Any, Dict, List

from dotenv import load_dotenv


def _fbref_blocked() -> bool:
    load_dotenv()
    return os.getenv("HIBS_FBREF_BLOCKED", "0").lower() in ("1", "true", "yes")


def _heavy_enabled() -> bool:
    load_dotenv()
    return os.getenv("HIBS_ENABLE_HEAVY_SCRAPERS", "1").lower() not in ("0", "false", "no")


def xg_priority_chain_dict() -> Dict[str, Any]:
    """
    Human-readable priority chain for dashboard /status.

    Order reflects ``DataAggregator._fetch_expected_goals`` then supplemental
    ``apply_scraped_xg_to_enriched`` upgrades (score-based, never downgrade).
    """
    fbref_blocked = _fbref_blocked()
    heavy = _heavy_enabled()
    steps: List[Dict[str, str]] = [
        {
            "rank": "1",
            "source": "api_fixture_xg",
            "when": "API-Football fixture payload includes expected_goals for both teams.",
            "leagues": "All when API returns per-fixture xG (often top leagues + some cups).",
        },
        {
            "rank": "2",
            "source": "stats_api_xg",
            "when": "RapidAPI stats feed returns both sides (skipped when HIBS_SKIP_RAPID_STATS_XG=1).",
            "leagues": "Same as stats API coverage.",
        },
        {
            "rank": "3",
            "source": "understat_xg / understat_team_xg",
            "when": "Understat light/heavy scrape beats goals_proxy (league embed or team rolling).",
            "leagues": "Big-5 + comps on Understat; optional blend via HIBS_USE_SUPPLEMENTAL_XG_PRIOR.",
        },
        {
            "rank": "4",
            "source": "fotmob_league_xg",
            "when": "FotMob league table xG/conceded when enabled (UEFA cups default on; HIBS_ENABLE_FOTMOB_XG).",
            "leagues": "UCL, Europa, UECL, internationals; domestic when MAX_DATA or explicit flag.",
        },
        {
            "rank": "5",
            "source": "fbref_schedule_xg / scottish_fbref_xg",
            "when": "FBref schedule or squad aggregates when heavy scrapers run and not blocked.",
            "leagues": "Scottish + schedule-linked leagues; skipped entirely when HIBS_FBREF_BLOCKED=1.",
        },
        {
            "rank": "6",
            "source": "scraped_recent_xg / sofascore_xg",
            "when": "Recent finished matches carry API statistics xG per team.",
            "leagues": "Any league where last-N API stats include Expected Goals.",
        },
        {
            "rank": "7",
            "source": "form_derived_xg / statsbomb_goals_proxy_xg",
            "when": "4+ recent games each side with goals but no direct xG; cup open-data proxy.",
            "leagues": "Cups without API xG; domestic when form is deep enough.",
        },
        {
            "rank": "8",
            "source": "mixed_api_goals_proxy",
            "when": "Partial API xG or attack/defence estimate from recent GF/GA.",
            "leagues": "Fallback for thin API coverage.",
        },
        {
            "rank": "9",
            "source": "goals_proxy",
            "when": "No trustworthy xG path; Poisson λ from recent goals only.",
            "leagues": "Lower coverage fixtures; lowest data_quality xG block score.",
        },
    ]
    per_league: List[Dict[str, str]] = [
        {
            "code": "UECL",
            "note": "FotMob id 10216 (primary); API league 848. Final round uses calendar-window season fetch.",
        },
        {
            "code": "PRIMEIRA",
            "note": "FotMob id 61; play-off rounds tagged via API round (Play-offs — Final).",
        },
        {
            "code": "NORWAY_ELITESERIEN / FINLAND_VEIKKAUSLIIGA",
            "note": "Calendar-year season candidates before Jul id when month < 7; SoccerStats table fallback.",
        },
        {
            "code": "SCOTLAND",
            "note": "FBref schedule xG when not blocked; otherwise API + SoccerStats.",
        },
        {
            "code": "WORLD_CUP / EUROS / NATIONS_LEAGUE",
            "note": "FotMob ids 77 / 50 / 9806–9809 when HIBS_ENABLE_FOTMOB_XG; else API fixture xG and form-derived paths.",
        },
    ]
    notes: List[str] = []
    if fbref_blocked:
        notes.append(
            "HIBS_FBREF_BLOCKED=1 — FBref steps are skipped on VPS; chain jumps from FotMob/Understat to recent-match xG or goals_proxy."
        )
    if not heavy:
        notes.append(
            "HIBS_ENABLE_HEAVY_SCRAPERS=0 — full Understat league pages and FBref squad paths are off; rely on API + light scrapers."
        )
    return {
        "headline": "xG priority chain (highest wins; never invent stats)",
        "fbref_blocked": fbref_blocked,
        "heavy_scrapers": heavy,
        "steps": steps,
        "per_league_notes": per_league,
        "ops_notes": notes,
    }
