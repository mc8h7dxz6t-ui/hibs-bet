"""
Scraped / derived xG for upcoming fixtures when API-Football fixture stats are empty.

Sources (priority):
  1. Understat league-page row for this fixture (top leagues)
  2. FBref schedule xG / team rolling averages (Scottish, EFL, selected European)
  3. StatsBomb open-data goals proxy → estimated xG when enabled
  4. Average xG from API-Sports last finished matches per team (all leagues with stats)
  5. Optional blend with existing goals_proxy when only one side has xG
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


def _statsbomb_xg_enabled() -> bool:
    raw = (os.getenv("HIBS_ENABLE_STATSBOMB_LIGHT") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    return _env_on("HIBS_MAX_DATA", "0")


def _xg_from_statsbomb_proxy(
    sb_proxy: Any,
    enriched: Dict[str, Any],
) -> Optional[Tuple[float, float]]:
    if not isinstance(sb_proxy, dict):
        return None
    home = sb_proxy.get("home") if isinstance(sb_proxy.get("home"), dict) else {}
    away = sb_proxy.get("away") if isinstance(sb_proxy.get("away"), dict) else {}
    if not home.get("ok") or not away.get("ok"):
        return None
    try:
        h_gf = float(home.get("gf_pg") or 0)
        h_ga = float(home.get("ga_pg") or 0)
        a_gf = float(away.get("gf_pg") or 0)
        a_ga = float(away.get("ga_pg") or 0)
        h_n = int(home.get("matches_used") or 0)
        a_n = int(away.get("matches_used") or 0)
    except (TypeError, ValueError):
        return None
    if h_n < 2 or a_n < 2 or h_gf <= 0 or a_gf <= 0:
        return None
    strength = float(enriched.get("league_factor") or 1.0)
    base = 1.1 * max(0.55, min(1.45, strength))
    xh = max(0.35, min(3.2, (h_gf + a_ga) / 2.0 * base / 1.15))
    xa = max(0.35, min(3.2, (a_gf + h_ga) / 2.0 * base / 1.15))
    return xh, xa


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
    from hibs_predictor.fixture_utils import fixture_team_name

    home_nm = fixture_team_name(fixture, "home")
    away_nm = fixture_team_name(fixture, "away")
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

    ss_block = sup.get("sofascore_xg") if isinstance(sup, dict) else None
    if isinstance(ss_block, dict):
        try:
            xh = float(ss_block.get("home_avg_for") or 0)
            xa = float(ss_block.get("away_avg_for") or 0)
            hn = int(ss_block.get("home_n") or 0)
            an = int(ss_block.get("away_n") or 0)
        except (TypeError, ValueError):
            xh = xa = hn = an = 0
        if xh > 0.04 and xa > 0.04 and hn >= 2 and an >= 2:
            meta["sofascore_n"] = {"home": hn, "away": an}
            return xh, xa, "sofascore_xg", meta

    try:
        from hibs_predictor.scrapers.sofascore_client import sofascore_xg_enabled, team_xg_profile_for_name

        if sofascore_xg_enabled():
            hp = team_xg_profile_for_name(home_nm)
            ap = team_xg_profile_for_name(away_nm)
            if hp and ap:
                xh = float(hp.get("avg_xg_for") or 0)
                xa = float(ap.get("avg_xg_for") or 0)
                if xh > 0.04 and xa > 0.04:
                    meta["sofascore_fetch"] = "direct"
                    meta["home_n"] = hp.get("n")
                    meta["away_n"] = ap.get("n")
                    return xh, xa, "sofascore_xg", meta
    except Exception:
        pass

    try:
        from hibs_predictor.scrapers.fbref_scottish_xg import resolve_fbref_schedule_xg

        fb = resolve_fbref_schedule_xg(league_code, home_nm, away_nm)
        if fb:
            xh, xa, tag, smeta = fb
            meta.update(smeta)
            return float(xh), float(xa), tag, meta
    except Exception:
        pass

    sup_fbref = sup.get("fbref_schedule") or sup.get("fbref_scottish")
    if isinstance(sup_fbref, dict):
        pair = _understat_pair_from_dict(sup_fbref)
        if pair:
            meta["fbref_schedule_key"] = "supplemental"
            src = str(sup_fbref.get("source") or "fbref_schedule_xg")
            return pair[0], pair[1], src, meta

    if _statsbomb_xg_enabled():
        sb_proxy = sup.get("statsbomb_open_team_proxy") if isinstance(sup, dict) else None
        pair = _xg_from_statsbomb_proxy(sb_proxy, enriched)
        if pair:
            meta["statsbomb"] = "open_goals_proxy"
            return pair[0], pair[1], "statsbomb_goals_proxy_xg", meta

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

    if current in ("goals_proxy", "mixed_api_goals_proxy", "unknown", ""):
        try:
            nh = int(float(enriched.get("home_recent_n") or 0))
            na = int(float(enriched.get("away_recent_n") or 0))
        except (TypeError, ValueError):
            nh = na = 0
        xh = float(enriched.get("xg_home") or 0)
        xa = float(enriched.get("xg_away") or 0)
        if nh >= 4 and na >= 4 and xh > 0.08 and xa > 0.08:
            meta["form_derived"] = True
            meta["home_n"] = nh
            meta["away_n"] = na
            return xh, xa, "form_derived_xg", meta

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
