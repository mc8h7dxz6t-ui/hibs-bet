"""Merge optional supplemental sources into one dict (fail-soft per source).

Env:
  HIBS_ENABLE_SUPPLEMENTAL — default on; set 0 to skip all supplemental HTTP.
  HIBS_ENABLE_HEAVY_SCRAPERS — FBref + full Understat (default **on**). Set to 0 only when heavy HTML is **detrimental** (rate limits, IP blocks, policy).
  HIBS_SKIP_HEAVY_WHEN_API_STRONG — default 1: per-fixture, skip heavy **only** when APIs already supply book odds, API/Stats xG, 4+ recent games each side, season stats, **and** league positions (same signal FBref/Understat would mainly reinforce).
  HIBS_ENABLE_UNDERSTAT_LIGHT — Understat xG row for fixtures in policy window (default **on** for supported leagues).
  HIBS_SCRAPE_XG — after supplemental, apply Understat + Scottish FBref + recent-match xG into ``xg_home`` / ``xg_away`` (default on).
  HIBS_ENABLE_SCOTTISH_FBREF_XG — FBref SPFL schedule xG for SCOTLAND* leagues (default on).
  HIBS_ENABLE_STATSBOMB_OPEN_MATCHES — StatsBomb open-data goals proxy for teams in policy window (off default).
  HIBS_PREFER_SCRAPED_STANDINGS — Wikipedia league table first (default on in aggregator).
  HIBS_SKIP_ODDS_API — skip The Odds API (explicit opt-out only when ODDS_API_KEY is usable).
  HIBS_SKIP_RAPID_STATS_XG — skip RapidAPI stats xG (default on; HIBS_MAX_DATA=1 + STATS_API_KEY enables).
  HIBS_MAX_DATA — when 1, prefer maximum safe inputs: do not skip heavy scrapers for "API strong" alone; enable Rapid stats xG when stats client is configured.

Source roadmap (FBref, Transfermarkt, WhoScored, SofaScore, Understat, FootyStats,
SoccerStats, DataMB): see ``hibs_predictor.scrapers.source_registry.SOURCE_CATALOG``.

Rolling window (with APIs unchanged): ``HIBS_STATS_LOOKBACK_DAYS`` (default 183), ``HIBS_STATS_FUTURE_DAYS``,
optional ``HIBS_DATA_POLICY_AS_OF`` — see ``data_source_policy``.
"""

import os
from datetime import datetime
from typing import Any, Dict, List

from hibs_predictor.cache import Cache
from hibs_predictor.data_quality import _has_stats, _position_ok


def _skip_heavy_when_api_strong(enriched: Dict[str, Any]) -> tuple:
    """If True, skip FBref / full Understat: APIs already cover the same inputs heavy would reinforce."""
    if os.getenv("HIBS_MAX_DATA", "").strip().lower() in ("1", "true", "yes", "on"):
        return False, ""
    if os.getenv("HIBS_SKIP_HEAVY_WHEN_API_STRONG", "1").lower() in ("0", "false", "no"):
        return False, ""
    if not enriched.get("odds_available"):
        return False, ""
    src = str(enriched.get("xg_source") or "").lower()
    if src not in ("api_fixture_xg", "stats_api_xg"):
        return False, ""
    try:
        nh = int(float(enriched.get("home_recent_n") or 0))
        na = int(float(enriched.get("away_recent_n") or 0))
    except (TypeError, ValueError):
        return False, ""
    if nh < 4 or na < 4:
        return False, ""
    if not _has_stats(enriched.get("home_stats")) or not _has_stats(enriched.get("away_stats")):
        return False, ""
    hp = enriched.get("home_position") or {}
    ap = enriched.get("away_position") or {}
    if not (_position_ok(hp) and _position_ok(ap)):
        return False, ""
    return True, "api_strong_skip_heavy"


def _understat_season_years_for_fixture(fixture: Dict[str, Any]) -> List[int]:
    from hibs_predictor.data_source_policy import parse_fixture_datetime_utc

    dt = parse_fixture_datetime_utc(fixture)
    if not dt:
        y = datetime.now().year
        return [y, y + 1, y - 1]
    y = dt.year
    if dt.month >= 7:
        return [y + 1, y, y - 1]
    return [y, y + 1, y - 1]


def collect_supplemental(fixture: Dict[str, Any], league_code: str, enriched: Dict[str, Any]) -> Dict[str, Any]:
    if os.getenv("HIBS_ENABLE_SUPPLEMENTAL", "1").lower() in ("0", "false", "no"):
        return {}

    cache = Cache()
    fid = fixture.get("fixture", {}).get("id") or ""
    key = f"supplemental_{fid}_{league_code}"
    hit = cache.get(key, ttl_hours=6)
    if hit:
        return hit

    out: Dict[str, Any] = {}
    home = (fixture.get("home", {}) or {}).get("name", "")
    heavy_enabled = os.getenv("HIBS_ENABLE_HEAVY_SCRAPERS", "1").lower() not in ("0", "false", "no")
    skip_heavy, skip_reason = _skip_heavy_when_api_strong(enriched)
    heavy = heavy_enabled and not skip_heavy
    if heavy_enabled and skip_heavy:
        out["heavy_skipped"] = {"reason": skip_reason}
    elif not heavy_enabled:
        out["heavy_skipped"] = {"reason": "heavy_disabled_detrimental_or_manual"}

    try:
        from hibs_predictor.scrapers import statsbomb_open as sb

        comps = sb.load_competitions()
        out["statsbomb_competition_count"] = len(comps)
    except Exception as exc:
        out["statsbomb_error"] = str(exc)

    light_us = os.getenv("HIBS_ENABLE_UNDERSTAT_LIGHT", "1").lower() not in ("0", "false", "no", "off")
    if light_us:
        try:
            from hibs_predictor.data_source_policy import fixture_in_policy_window
            from hibs_predictor.scrapers import understat_client as us

            if fixture_in_policy_window(fixture) and league_code in us.LEAGUE_SLUG:
                away_nm = (fixture.get("away", {}) or {}).get("name", "")
                for sy in _understat_season_years_for_fixture(fixture):
                    row = us.find_fixture_row(league_code, sy, home, away_nm)
                    if row:
                        out["understat_light"] = us.extract_xg_from_row(row)
                        out["understat_light_season_year"] = sy
                        break
        except Exception as exc:
            out["understat_light_error"] = str(exc)

    sb_matches = os.getenv("HIBS_ENABLE_STATSBOMB_OPEN_MATCHES", "0").lower() in ("1", "true", "yes")
    if sb_matches:
        try:
            from hibs_predictor.data_source_policy import fixture_in_policy_window, policy_window_utc
            from hibs_predictor.scrapers import statsbomb_open as sb

            if fixture_in_policy_window(fixture) and league_code in sb.STATSBOMB_LEAGUE_OPEN:
                lo, hi = policy_window_utc()
                d_lo, d_hi = lo.date(), hi.date()
                away_nm = (fixture.get("away", {}) or {}).get("name", "")
                out["statsbomb_open_team_proxy"] = {
                    "home": sb.team_proxy_from_open_matches(league_code, home, d_lo, d_hi),
                    "away": sb.team_proxy_from_open_matches(league_code, away_nm, d_lo, d_hi),
                }
        except Exception as exc:
            out["statsbomb_open_team_proxy_error"] = str(exc)

    if heavy:
        try:
            from hibs_predictor.scrapers import understat_client as us

            away_nm = (fixture.get("away", {}) or {}).get("name", "")
            row = None
            for sy in _understat_season_years_for_fixture(fixture):
                row = us.find_fixture_row(league_code, sy, home, away_nm)
                if row:
                    break
            if row:
                out["understat"] = us.extract_xg_from_row(row)
        except Exception as exc:
            out["understat_error"] = str(exc)

        try:
            from hibs_predictor.scrapers import fbref_client as fr

            rows = fr.fetch_squad_stats_table(league_code)
            if rows:
                sr = fr.squad_row_for_team(rows, home)
                if sr:
                    out["fbref_home_squad"] = {"squad": sr.get("squad"), "stat_keys": list(sr.get("cells", {}).keys())[:12]}
        except Exception as exc:
            out["fbref_error"] = str(exc)

    try:
        from hibs_predictor.scrapers import wikipedia_standings as wps

        if league_code in wps.WP_SUFFIX:
            out["wikipedia_league_supported"] = True
    except Exception:
        pass

    try:
        from hibs_predictor.data_source_policy import fixture_in_policy_window
        from hibs_predictor.scrapers import sofascore_client as ss

        if fixture_in_policy_window(fixture):
            ent = ss.first_team_hit(home)
            if ent and ent.get("id"):
                ev = ss.team_last_xg_summary(int(ent["id"]))
                out["sofascore_team_events"] = ev[:5]
            if ss.sofascore_xg_enabled():
                away_nm = (fixture.get("away", {}) or {}).get("name", "")
                hp = ss.team_xg_profile_for_name(home)
                ap = ss.team_xg_profile_for_name(away_nm) if away_nm else None
                if hp and ap:
                    out["sofascore_xg"] = {
                        "home_avg_for": round(float(hp["avg_xg_for"]), 3),
                        "away_avg_for": round(float(ap["avg_xg_for"]), 3),
                        "home_n": int(hp.get("n") or 0),
                        "away_n": int(ap.get("n") or 0),
                    }
    except Exception as exc:
        out["sofascore_error"] = str(exc)

    cache.set(key, out, ttl_hours=6)
    return out
