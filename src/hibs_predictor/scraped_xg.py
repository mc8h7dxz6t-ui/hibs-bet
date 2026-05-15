"""
Scraped / derived xG for upcoming fixtures when API-Football fixture stats are empty.

Sources (priority):
  1. Understat league-page row for this fixture (top leagues)
  2. FBref SPFL schedule xG / team rolling averages (Scottish leagues)
  3. Average xG from API-Sports last finished matches per team (all leagues with stats)
  4. Optional blend with existing goals_proxy when only one side has xG
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from hibs_predictor.betting_engine import TeamStrengthCalculator


def _env_on(name: str, default: str = "1") -> bool:
    return (os.getenv(name, default) or default).strip().lower() not in ("0", "false", "no", "off")


def _avg_team_xg_from_recent(matches: List[Dict[str, Any]], team_id: int, min_samples: int = 2) -> Optional[float]:
    if not team_id or not matches:
        return None
    vals: List[float] = []
    for m in matches[:10]:
        v = TeamStrengthCalculator._team_xg_from_fixture_statistics(m, int(team_id))
        if v is not None and v > 0.04:
            vals.append(float(v))
    if len(vals) < min_samples:
        return None
    return sum(vals) / len(vals)


def _understat_pair_from_dict(us: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    try:
        uh = float(us.get("xg_home"))
        ua = float(us.get("xg_away"))
    except (TypeError, ValueError):
        return None
    if uh > 0.04 and ua > 0.04 and (uh + ua) < 6.5:
        return uh, ua
    return None


def _fetch_understat_row(
    league_code: str,
    fixture: Dict[str, Any],
    home_name: str,
    away_name: str,
) -> Optional[Dict[str, float]]:
    try:
        from hibs_predictor.scrapers import understat_client as us
        from hibs_predictor.scrapers.supplemental import _understat_season_years_for_fixture
        from hibs_predictor.scrapers.understat_client import extract_xg_from_row

        if league_code not in us.LEAGUE_SLUG:
            return None
        for sy in _understat_season_years_for_fixture(fixture):
            row = us.find_fixture_row(league_code, sy, home_name, away_name)
            if row:
                xg = extract_xg_from_row(row)
                if _understat_pair_from_dict(xg):
                    return xg
    except Exception:
        return None
    return None


def resolve_scraped_xg(
    fixture: Dict[str, Any],
    league_code: str,
    enriched: Dict[str, Any],
) -> Optional[Tuple[float, float, str, Dict[str, Any]]]:
    """
    Return (xg_home, xg_away, source_tag, debug_meta) or None if no scrape improves on goals-only proxy.
    """
    if not _env_on("HIBS_SCRAPE_XG", "1"):
        return None

    current = str(enriched.get("xg_source") or "").lower()
    if current in ("api_fixture_xg", "stats_api_xg"):
        return None

    home_id = (fixture.get("teams", {}) or {}).get("home", {}).get("id") or 0
    away_id = (fixture.get("teams", {}) or {}).get("away", {}).get("id") or 0
    home_nm = (fixture.get("home", {}) or {}).get("name", "")
    away_nm = (fixture.get("away", {}) or {}).get("name", "")
    sup = enriched.get("supplemental") if isinstance(enriched.get("supplemental"), dict) else {}
    meta: Dict[str, Any] = {}

    for key in ("understat", "understat_light"):
        us = sup.get(key) if isinstance(sup, dict) else None
        if isinstance(us, dict):
            pair = _understat_pair_from_dict(us)
            if pair:
                meta["understat_key"] = key
                return pair[0], pair[1], "understat_xg", meta

    if _env_on("HIBS_ENABLE_UNDERSTAT_LIGHT", "1"):
        us = _fetch_understat_row(league_code, fixture, home_nm, away_nm)
        if us:
            pair = _understat_pair_from_dict(us)
            if pair:
                meta["understat_fetch"] = "direct"
                return pair[0], pair[1], "understat_xg", meta

    try:
        from hibs_predictor.scrapers.fbref_scottish_xg import resolve_scottish_fbref_xg

        scot = resolve_scottish_fbref_xg(league_code, home_nm, away_nm)
        if scot:
            xh, xa, tag, smeta = scot
            meta.update(smeta)
            return float(xh), float(xa), tag, meta
    except Exception:
        pass

    sup_fbref = sup.get("fbref_scottish") if isinstance(sup, dict) else None
    if isinstance(sup_fbref, dict):
        pair = _understat_pair_from_dict(sup_fbref)
        if pair:
            meta["fbref_scottish_key"] = "supplemental"
            return pair[0], pair[1], str(sup_fbref.get("source") or "scottish_fbref_xg"), meta

    h_avg = _avg_team_xg_from_recent(enriched.get("home_recent") or [], int(home_id or 0))
    a_avg = _avg_team_xg_from_recent(enriched.get("away_recent") or [], int(away_id or 0))
    if h_avg is not None and a_avg is not None:
        meta["home_xg_samples"] = "recent_api"
        meta["away_xg_samples"] = "recent_api"
        return h_avg, a_avg, "scraped_recent_xg", meta

    if h_avg is not None or a_avg is not None:
        base_h = float(enriched.get("xg_home") or 1.2)
        base_a = float(enriched.get("xg_away") or 1.1)
        meta["partial_scrape"] = True
        return (h_avg if h_avg is not None else base_h), (a_avg if a_avg is not None else base_a), "partial_scraped_xg", meta

    return None


def apply_scraped_xg_to_enriched(
    fixture: Dict[str, Any],
    league_code: str,
    enriched: Dict[str, Any],
) -> Dict[str, Any]:
    """Mutate enriched xG fields when scrapers / recent-match xG beat goals_proxy."""
    resolved = resolve_scraped_xg(fixture, league_code, enriched)
    if not resolved:
        return enriched
    xh, xa, tag, meta = resolved
    enriched["xg_home"] = float(xh)
    enriched["xg_away"] = float(xa)
    enriched["xg_source"] = tag
    enriched["scraped_xg_meta"] = meta
    return enriched
