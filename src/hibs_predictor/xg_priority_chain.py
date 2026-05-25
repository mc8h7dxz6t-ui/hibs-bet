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
            "rank": "1b",
            "source": "api_statistics_xg",
            "when": "fixtures/statistics Expected Goals when fixture xG empty (HIBS_FETCH_FIXTURE_STATISTICS_XG=1; budget HIBS_FETCH_FIXTURE_STATISTICS_XG_MAX).",
            "leagues": "Live/finished fixtures where provider publishes stats xG.",
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
            "when": "FotMob season table xG/conceded (UEFA cups + domestic cups default-on; HIBS_ENABLE_FOTMOB_XG for all).",
            "leagues": "UCL, Europa, UECL, internationals, SCOTTISH_CUP→SPFL table; domestic when MAX_DATA or explicit flag.",
        },
        {
            "rank": "5",
            "source": "scraped_recent_xg",
            "when": "Average xG from each team's last finished matches where API published Expected Goals.",
            "leagues": "Any league where last-N API stats include per-match xG.",
        },
        {
            "rank": "6",
            "source": "api_season_team_xg",
            "when": "Season GF/GA per game from API team statistics blended attack vs opponent defence.",
            "leagues": "When fixture xG empty but API season stats have 5+ matches played.",
        },
        {
            "rank": "7",
            "source": "fbref_schedule_xg / scottish_fbref_xg",
            "when": "FBref schedule or squad aggregates when heavy scrapers run and not blocked.",
            "leagues": "Scottish + schedule-linked leagues; skipped entirely when HIBS_FBREF_BLOCKED=1.",
        },
        {
            "rank": "8",
            "source": "sofascore_xg",
            "when": "SofaScore team xG averages when enabled.",
            "leagues": "Optional; lower priority than API recent/season paths.",
        },
        {
            "rank": "9",
            "source": "statsbomb_goals_proxy_xg",
            "when": "StatsBomb open-data goals proxy for cups when other scrapes miss.",
            "leagues": "UEFA cups, domestic cups, COUPE_DE_FRANCE, etc.",
        },
        {
            "rank": "10",
            "source": "mixed_api_goals_proxy",
            "when": "Partial API xG or attack/defence estimate from recent GF/GA.",
            "leagues": "Fallback for thin API coverage.",
        },
        {
            "rank": "11",
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
            "code": "SCOTLAND / SCOTTISH_CUP",
            "note": "SPFL FotMob id 64; cup ties use SCOTLAND table fallback. FBref when not blocked; else API recent/season.",
        },
        {
            "code": "WORLD_CUP / EUROS / NATIONS_LEAGUE",
            "note": "FotMob ids 77 / 50 / 9806–9809 when HIBS_ENABLE_FOTMOB_XG or cup default-on.",
        },
        {
            "code": "INTL_FRIENDLIES",
            "note": "API-Football league 10; no FotMob table — API fixture xG, recent-match stats, or goals_proxy.",
        },
    ]
    notes: List[str] = []
    if fbref_blocked:
        notes.append(
            "HIBS_FBREF_BLOCKED=1 — FBref steps are skipped on VPS; chain uses FotMob, Understat, recent API xG, or goals_proxy."
        )
    if not heavy:
        notes.append(
            "HIBS_ENABLE_HEAVY_SCRAPERS=0 — full Understat league pages and FBref squad paths are off; rely on API + light scrapers."
        )
    notes.append(
        "UI shows xg_source_label + xg_confidence_tier (strong / usable / thin / proxy) on each fixture expand panel."
    )
    return {
        "headline": "xG priority chain (highest wins; never invent stats)",
        "fbref_blocked": fbref_blocked,
        "heavy_scrapers": heavy,
        "steps": steps,
        "per_league_notes": per_league,
        "ops_notes": notes,
    }
