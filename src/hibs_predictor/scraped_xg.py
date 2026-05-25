"""
Scraped / derived xG for upcoming fixtures when API-Football fixture stats are empty.

Resolution order (score-based upgrade; never downgrade API fixture xG):
  1. Understat league-page row for this fixture (top leagues)
  2. FotMob league-table xG (UEFA cups default-on; domestic when HIBS_ENABLE_FOTMOB_XG)
  3. Recent finished matches with API statistics xG per team
  4. API season team attack/defence blend (real season stats only)
  5. FBref schedule xG when heavy scrapers run and not blocked on VPS
  6. SofaScore team averages (optional)
  7. StatsBomb open-data goals proxy (cups / when enabled)
  8. Partial scrape / goals_proxy re-tags avoided where possible
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional, Tuple

from hibs_predictor.betting_engine import TeamStrengthCalculator

Resolver = Callable[
    [Dict[str, Any], str, Dict[str, Any], Dict[str, Any], int, int, str, str],
    Optional[Tuple[float, float, str, Dict[str, Any]]],
]


def _env_on(name: str, default: str = "1") -> bool:
    return (os.getenv(name, default) or default).strip().lower() not in ("0", "false", "no", "off")


def _fbref_blocked() -> bool:
    return os.getenv("HIBS_FBREF_BLOCKED", "0").strip().lower() in ("1", "true", "yes", "on")


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


def _statsbomb_xg_enabled(league_code: str = "") -> bool:
    """Mirror supplemental ``_statsbomb_team_proxy_on``: cups default-on; else light/max-data."""
    raw = (os.getenv("HIBS_ENABLE_STATSBOMB_LIGHT") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    if league_code:
        try:
            from hibs_predictor.scrapers import statsbomb_open as sb

            if league_code in sb.STATSBOMB_CUP_LEAGUES:
                return True
        except Exception:
            pass
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
) -> Optional[Tuple[Dict[str, float], str, Dict[str, Any]]]:
    try:
        from hibs_predictor.scrapers import understat_client as us
        from hibs_predictor.scrapers.supplemental import _understat_season_years_for_fixture

        if league_code not in us.LEAGUE_SLUG:
            return None
        for sy in _understat_season_years_for_fixture(fixture):
            payload, tag, meta = us.resolve_understat_xg(
                league_code, sy, home_name, away_name, fixture=fixture
            )
            if payload and _understat_pair_from_dict(payload):
                meta["understat_fetch"] = "direct"
                meta["season_year"] = sy
                return payload, tag, meta
    except Exception:
        return None
    return None


def _api_season_team_xg(
    enriched: Dict[str, Any],
    league_strength: float,
) -> Optional[Tuple[float, float, Dict[str, Any]]]:
    """Blend season GF/GA per game from API team statistics (not recent-form proxy)."""
    hs = enriched.get("home_stats") if isinstance(enriched.get("home_stats"), dict) else {}
    aws = enriched.get("away_stats") if isinstance(enriched.get("away_stats"), dict) else {}
    if str(hs.get("source") or "") == "football_data_org" or str(aws.get("source") or "") == "football_data_org":
        return None
    try:
        hp = int(hs.get("played") or 0)
        ap = int(aws.get("played") or 0)
        h_gf = float(hs.get("goals_for") or 0)
        h_ga = float(hs.get("goals_against") or 0)
        a_gf = float(aws.get("goals_for") or 0)
        a_ga = float(aws.get("goals_against") or 0)
    except (TypeError, ValueError):
        return None
    if hp < 5 or ap < 5 or h_gf <= 0 or a_gf <= 0:
        return None
    h_for_pg = h_gf / hp
    h_against_pg = h_ga / hp
    a_for_pg = a_gf / ap
    a_against_pg = a_ga / ap
    strength = max(0.55, min(1.45, float(league_strength or 1.0)))
    xh = max(0.35, min(3.2, (h_for_pg + a_against_pg) / 2.0 * strength / 1.12))
    xa = max(0.35, min(3.2, (a_for_pg + h_against_pg) / 2.0 * strength / 1.12))
    meta = {"home_played": hp, "away_played": ap, "api_season_blend": True}
    return xh, xa, meta


def _try_understat(
    fixture: Dict[str, Any],
    league_code: str,
    enriched: Dict[str, Any],
    sup: Dict[str, Any],
    home_id: int,
    away_id: int,
    home_nm: str,
    away_nm: str,
) -> Optional[Tuple[float, float, str, Dict[str, Any]]]:
    meta: Dict[str, Any] = {}
    for key in ("understat", "understat_light"):
        us = sup.get(key) if isinstance(sup, dict) else None
        if isinstance(us, dict):
            pair = _understat_pair_from_dict(us)
            if pair:
                meta["understat_key"] = key
                meta["match_confident"] = not bool(sup.get("understat_light_team_rolling"))
                tag = str(sup.get(f"{key}_source") or sup.get("understat_light_source") or "understat_xg")
                if sup.get("understat_light_team_rolling"):
                    tag = "understat_team_xg"
                    meta["team_rolling"] = True
                return pair[0], pair[1], tag, meta

    if _env_on("HIBS_ENABLE_UNDERSTAT_LIGHT", "1"):
        fetched = _fetch_understat_row(league_code, fixture, home_nm, away_nm)
        if fetched:
            us, tag, fmeta = fetched
            pair = _understat_pair_from_dict(us)
            if pair:
                meta.update(fmeta)
                return pair[0], pair[1], tag, meta
    return None


def _try_fotmob(
    fixture: Dict[str, Any],
    league_code: str,
    enriched: Dict[str, Any],
    sup: Dict[str, Any],
    home_id: int,
    away_id: int,
    home_nm: str,
    away_nm: str,
) -> Optional[Tuple[float, float, str, Dict[str, Any]]]:
    meta: Dict[str, Any] = {}
    fm_block = sup.get("fotmob_xg") if isinstance(sup, dict) else None
    if isinstance(fm_block, dict):
        pair = _understat_pair_from_dict(fm_block)
        if pair:
            meta["fotmob_league"] = True
            meta["home_n"] = fm_block.get("home_n")
            meta["away_n"] = fm_block.get("away_n")
            return pair[0], pair[1], "fotmob_league_xg", meta

    try:
        from hibs_predictor.scrapers.fotmob_client import fotmob_xg_enabled, resolve_league_fixture_xg

        if fotmob_xg_enabled(league_code):
            fx = resolve_league_fixture_xg(league_code, home_nm, away_nm)
            if fx:
                xh, xa, fmeta = fx
                meta.update(fmeta)
                meta["fotmob_fetch"] = "direct"
                return float(xh), float(xa), "fotmob_league_xg", meta
    except Exception:
        pass
    return None


def _try_recent_api_xg(
    fixture: Dict[str, Any],
    league_code: str,
    enriched: Dict[str, Any],
    sup: Dict[str, Any],
    home_id: int,
    away_id: int,
    home_nm: str,
    away_nm: str,
) -> Optional[Tuple[float, float, str, Dict[str, Any]]]:
    meta: Dict[str, Any] = {}
    h_avg = _avg_team_xg_from_recent(enriched.get("home_recent") or [], int(home_id or 0))
    a_avg = _avg_team_xg_from_recent(enriched.get("away_recent") or [], int(away_id or 0))
    if h_avg is not None and a_avg is not None:
        meta["home_xg_samples"] = "recent_api"
        meta["away_xg_samples"] = "recent_api"
        return h_avg, a_avg, "scraped_recent_xg", meta
    return None


def _try_api_season(
    fixture: Dict[str, Any],
    league_code: str,
    enriched: Dict[str, Any],
    sup: Dict[str, Any],
    home_id: int,
    away_id: int,
    home_nm: str,
    away_nm: str,
) -> Optional[Tuple[float, float, str, Dict[str, Any]]]:
    league = enriched.get("league_factor")
    if league is None:
        try:
            from hibs_predictor.config import LEAGUES

            league = LEAGUES.get(league_code, {}).get("strength_factor", 1.0)
        except Exception:
            league = 1.0
    hit = _api_season_team_xg(enriched, float(league or 1.0))
    if hit:
        xh, xa, meta = hit
        return xh, xa, "api_season_team_xg", meta
    return None


def _try_sofascore(
    fixture: Dict[str, Any],
    league_code: str,
    enriched: Dict[str, Any],
    sup: Dict[str, Any],
    home_id: int,
    away_id: int,
    home_nm: str,
    away_nm: str,
) -> Optional[Tuple[float, float, str, Dict[str, Any]]]:
    meta: Dict[str, Any] = {}
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
    return None


def _try_fbref(
    fixture: Dict[str, Any],
    league_code: str,
    enriched: Dict[str, Any],
    sup: Dict[str, Any],
    home_id: int,
    away_id: int,
    home_nm: str,
    away_nm: str,
) -> Optional[Tuple[float, float, str, Dict[str, Any]]]:
    if _fbref_blocked():
        return None
    meta: Dict[str, Any] = {}
    sup_fbref = sup.get("fbref_schedule") or sup.get("fbref_scottish")
    if isinstance(sup_fbref, dict):
        pair = _understat_pair_from_dict(sup_fbref)
        if pair:
            meta["fbref_schedule_key"] = "supplemental"
            src = str(sup_fbref.get("source") or "fbref_schedule_xg")
            return pair[0], pair[1], src, meta

    try:
        from hibs_predictor.scrapers.fbref_scottish_xg import resolve_fbref_schedule_xg

        fb = resolve_fbref_schedule_xg(league_code, home_nm, away_nm)
        if fb:
            xh, xa, tag, smeta = fb
            meta.update(smeta)
            return float(xh), float(xa), tag, meta
    except Exception:
        pass
    return None


def _try_statsbomb(
    fixture: Dict[str, Any],
    league_code: str,
    enriched: Dict[str, Any],
    sup: Dict[str, Any],
    home_id: int,
    away_id: int,
    home_nm: str,
    away_nm: str,
) -> Optional[Tuple[float, float, str, Dict[str, Any]]]:
    if not _statsbomb_xg_enabled(league_code):
        return None
    sb_proxy = sup.get("statsbomb_open_team_proxy") if isinstance(sup, dict) else None
    pair = _xg_from_statsbomb_proxy(sb_proxy, enriched)
    if pair:
        return pair[0], pair[1], "statsbomb_goals_proxy_xg", {"statsbomb": "open_goals_proxy"}
    return None


def _try_partial_scrape(
    fixture: Dict[str, Any],
    league_code: str,
    enriched: Dict[str, Any],
    sup: Dict[str, Any],
    home_id: int,
    away_id: int,
    home_nm: str,
    away_nm: str,
) -> Optional[Tuple[float, float, str, Dict[str, Any]]]:
    h_avg = _avg_team_xg_from_recent(enriched.get("home_recent") or [], int(home_id or 0))
    a_avg = _avg_team_xg_from_recent(enriched.get("away_recent") or [], int(away_id or 0))
    if h_avg is not None or a_avg is not None:
        base_h = float(enriched.get("xg_home") or 1.2)
        base_a = float(enriched.get("xg_away") or 1.1)
        return (
            h_avg if h_avg is not None else base_h,
            a_avg if a_avg is not None else base_a,
            "partial_scraped_xg",
            {"partial_scrape": True},
        )
    return None


_SCRAPE_RESOLVERS: List[Resolver] = [
    _try_understat,
    _try_fotmob,
    _try_recent_api_xg,
    _try_api_season,
    _try_fbref,
    _try_sofascore,
    _try_statsbomb,
    _try_partial_scrape,
]


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
    always_deep = os.getenv("HIBS_ALWAYS_DEEP_SCRAPE", "1").lower() not in ("0", "false", "no", "off")
    if current in ("api_fixture_xg", "stats_api_xg") and not always_deep:
        return None

    from hibs_predictor.fixture_utils import fixture_team_id, fixture_team_name

    home_id = fixture_team_id(fixture, "home") or fixture_team_id(enriched, "home") or 0
    away_id = fixture_team_id(fixture, "away") or fixture_team_id(enriched, "away") or 0

    home_nm = fixture_team_name(fixture, "home")
    away_nm = fixture_team_name(fixture, "away")
    sup = enriched.get("supplemental") if isinstance(enriched.get("supplemental"), dict) else {}

    for resolver in _SCRAPE_RESOLVERS:
        hit = resolver(fixture, league_code, enriched, sup, home_id, away_id, home_nm, away_nm)
        if hit:
            return hit

    return None


def _xg_source_score(tag: str, enriched: Dict[str, Any]) -> float:
    from hibs_predictor.data_quality import _xg_points

    n_h = float(enriched.get("home_recent_n") or 0)
    n_a = float(enriched.get("away_recent_n") or 0)
    return _xg_points(str(tag or "").lower(), n_h, n_a, enriched)


def apply_scraped_xg_to_enriched(
    fixture: Dict[str, Any],
    league_code: str,
    enriched: Dict[str, Any],
) -> Dict[str, Any]:
    """Mutate enriched xG fields when scrapers / recent-match xG beat goals_proxy."""
    resolved = resolve_scraped_xg(fixture, league_code, enriched)
    if not resolved:
        from hibs_predictor.xg_source_display import attach_xg_display_fields

        attach_xg_display_fields(enriched, enriched)
        return enriched
    xh, xa, tag, meta = resolved
    current = str(enriched.get("xg_source") or "").lower()
    if current and _xg_source_score(tag, enriched) < _xg_source_score(current, enriched):
        from hibs_predictor.xg_source_display import attach_xg_display_fields

        attach_xg_display_fields(enriched, enriched)
        return enriched
    enriched["xg_home"] = float(xh)
    enriched["xg_away"] = float(xa)
    enriched["xg_source"] = tag
    enriched["scraped_xg_meta"] = meta
    from hibs_predictor.xg_source_display import attach_xg_display_fields

    attach_xg_display_fields(enriched, enriched)
    return enriched
