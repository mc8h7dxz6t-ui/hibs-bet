"""Merge optional supplemental sources into one dict (fail-soft per source).

Env:
  HIBS_ENABLE_SUPPLEMENTAL — default on; set 0 to skip all supplemental HTTP.
  HIBS_ENABLE_HEAVY_SCRAPERS — FBref + full Understat (default **on**). Set to 0 only when heavy HTML is **detrimental** (rate limits, IP blocks, policy).
  HIBS_ALWAYS_DEEP_SCRAPE — default **on**: always run heavy/light supplemental scrapers when scrape is enabled (see ``HIBS_SCRAPE_XG``).
  HIBS_SKIP_HEAVY_WHEN_API_STRONG — default **off**: set to 1 to skip FBref/full Understat per-fixture when APIs already cover odds, xG, form, stats, and table positions.
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


def _always_deep_scrape() -> bool:
    """When on (default), never skip heavy scrapers for API-strong fixtures."""
    return os.getenv("HIBS_ALWAYS_DEEP_SCRAPE", "1").lower() not in ("0", "false", "no", "off")


def _skip_heavy_when_api_strong(enriched: Dict[str, Any]) -> tuple:
    """If True, skip FBref / full Understat: APIs already cover the same inputs heavy would reinforce."""
    if _always_deep_scrape():
        return False, ""
    if os.getenv("HIBS_MAX_DATA", "").strip().lower() in ("1", "true", "yes", "on"):
        return False, ""
    if os.getenv("HIBS_SKIP_HEAVY_WHEN_API_STRONG", "0").lower() in ("0", "false", "no"):
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


def _record_miss(out: Dict[str, Any], key: str, detail: str) -> None:
    """Surface best-effort scrape attempts that returned nothing (visible in supplemental JSON)."""
    misses = out.get("supplemental_misses")
    if not isinstance(misses, dict):
        misses = {}
        out["supplemental_misses"] = misses
    misses[key] = detail


def _understat_season_years_for_fixture(fixture: Dict[str, Any]) -> List[int]:
    """Understat league URLs use the season end year (2025/26 → 2026). Avoid futile y+1 probes mid-season."""
    from hibs_predictor.data_source_policy import parse_fixture_datetime_utc

    dt = parse_fixture_datetime_utc(fixture)
    if not dt:
        now = datetime.now()
        end_year = now.year + 1 if now.month >= 7 else now.year
        return [end_year, end_year - 1]
    end_year = dt.year + 1 if dt.month >= 7 else dt.year
    out: List[int] = []
    for y in (end_year, end_year - 1, end_year + 1):
        if y not in out:
            out.append(y)
    return out


def collect_supplemental(fixture: Dict[str, Any], league_code: str, enriched: Dict[str, Any]) -> Dict[str, Any]:
    if os.getenv("HIBS_ENABLE_SUPPLEMENTAL", "1").lower() in ("0", "false", "no"):
        return {}

    cache = Cache()
    fid = fixture.get("fixture", {}).get("id") or ""
    key = f"supplemental_{fid}_{league_code}"
    hit = cache.get(key, ttl_hours=6)
    if hit:
        skip_heavy_now, _ = _skip_heavy_when_api_strong(enriched)
        stale_skip = isinstance(hit, dict) and hit.get("heavy_skipped") and not skip_heavy_now
        if not stale_skip:
            return hit

    out: Dict[str, Any] = {}
    from hibs_predictor.fixture_utils import fixture_team_name

    home = fixture_team_name(fixture, "home")
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
            from hibs_predictor.scrapers import understat_client as us

            if league_code in us.LEAGUE_SLUG:
                away_nm = fixture_team_name(fixture, "away")
                for sy in _understat_season_years_for_fixture(fixture):
                    payload, tag, umeta = us.resolve_understat_xg(
                        league_code, sy, home, away_nm, fixture=fixture
                    )
                    if payload and (payload.get("xg_home") or payload.get("xg_away")):
                        out["understat_light"] = payload
                        out["understat_light_season_year"] = sy
                        out["understat_light_source"] = tag
                        if umeta.get("team_rolling"):
                            out["understat_light_team_rolling"] = True
                            if umeta.get("home_n") is not None:
                                out["understat_light_home_n"] = umeta.get("home_n")
                            if umeta.get("away_n") is not None:
                                out["understat_light_away_n"] = umeta.get("away_n")
                        break
                if "understat_light" not in out:
                    _record_miss(out, "understat_light", "no_row_or_rolling_xg")
        except Exception as exc:
            out["understat_light_error"] = str(exc)

    def _statsbomb_team_proxy_on(lc: str) -> bool:
        from hibs_predictor.scrapers import statsbomb_open as sb_mod

        raw = os.getenv("HIBS_ENABLE_STATSBOMB_OPEN_MATCHES", "").strip().lower()
        if raw in ("0", "false", "no", "off"):
            return False
        if raw in ("1", "true", "yes", "on"):
            return True
        light = os.getenv("HIBS_ENABLE_STATSBOMB_LIGHT", "").strip().lower()
        if light in ("1", "true", "yes", "on"):
            return True
        if light in ("0", "false", "no", "off"):
            return False
        if lc in sb_mod.STATSBOMB_CUP_LEAGUES:
            return True
        return os.getenv("HIBS_MAX_DATA", "").strip().lower() in ("1", "true", "yes", "on")

    sb_matches = _statsbomb_team_proxy_on(league_code)
    if sb_matches:
        try:
            from hibs_predictor.data_source_policy import fixture_in_policy_window, policy_window_utc
            from hibs_predictor.scrapers import statsbomb_open as sb

            if fixture_in_policy_window(fixture) and league_code in sb.STATSBOMB_LEAGUE_OPEN:
                lo, hi = policy_window_utc()
                d_lo, d_hi = lo.date(), hi.date()
                away_nm = fixture_team_name(fixture, "away")
                out["statsbomb_open_team_proxy"] = {
                    "home": sb.team_proxy_from_open_matches(league_code, home, d_lo, d_hi),
                    "away": sb.team_proxy_from_open_matches(league_code, away_nm, d_lo, d_hi),
                }
        except Exception as exc:
            out["statsbomb_open_team_proxy_error"] = str(exc)

    if heavy:
        try:
            from hibs_predictor.scrapers import understat_client as us

            away_nm = fixture_team_name(fixture, "away")
            for sy in _understat_season_years_for_fixture(fixture):
                payload, tag, _ = us.resolve_understat_xg(
                    league_code, sy, home, away_nm, fixture=fixture
                )
                if payload:
                    out["understat"] = payload
                    out["understat_source"] = tag
                    break
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
            if os.getenv("HIBS_PREFER_SCRAPED_STANDINGS", "1").lower() in ("1", "true", "yes"):
                rows = wps.fetch_league_table(league_code)
                if rows:
                    out["wikipedia_table_rows"] = len(rows)
                    wr = wps.find_team_row(rows, home)
                    ar = wps.find_team_row(rows, fixture_team_name(fixture, "away"))
                    if wr or ar:
                        out["wikipedia_positions"] = {
                            "home": bool(wr),
                            "away": bool(ar),
                        }
                    elif rows:
                        _record_miss(out, "wikipedia_positions", "team_name_no_match")
    except Exception as exc:
        out["wikipedia_error"] = str(exc)[:120]

    try:
        from hibs_predictor.scrapers import soccerstats_standings as sstats

        if league_code in sstats.LEAGUE_PARAM:
            out["soccerstats_league_supported"] = True
            if os.getenv("HIBS_PREFER_SCRAPED_STANDINGS", "1").lower() in ("1", "true", "yes"):
                ss_rows = sstats.fetch_league_table(league_code, cache=cache)
                if ss_rows:
                    out["soccerstats_table_rows"] = len(ss_rows)
                    sr_h = sstats.find_team_row(ss_rows, home)
                    sr_a = sstats.find_team_row(ss_rows, fixture_team_name(fixture, "away"))
                    if sr_h or sr_a:
                        out["soccerstats_positions"] = {
                            "home": bool(sr_h),
                            "away": bool(sr_a),
                        }
                    elif ss_rows:
                        _record_miss(out, "soccerstats_positions", "team_name_no_match")
    except Exception as exc:
        out["soccerstats_error"] = str(exc)[:120]

    try:
        from hibs_predictor.scrapers import fotmob_client as fm

        if league_code in fm.FOTMOB_LEAGUE_IDS:
            out["fotmob_league_supported"] = True
    except Exception:
        pass

    try:
        from hibs_predictor.data_source_policy import fixture_in_policy_window
        from hibs_predictor.scrapers.fbref_scottish_xg import has_fbref_schedule_xg, resolve_fbref_schedule_xg

        if fixture_in_policy_window(fixture) and has_fbref_schedule_xg(league_code):
            away_nm = fixture_team_name(fixture, "away")
            fb = resolve_fbref_schedule_xg(league_code, home, away_nm)
            if fb:
                xh, xa, tag, fmeta = fb
                out["fbref_schedule"] = {
                    "xg_home": xh,
                    "xg_away": xa,
                    "source": tag,
                    **{k: v for k, v in (fmeta or {}).items() if k not in ("xg_home", "xg_away")},
                }
    except Exception as exc:
        out["fbref_schedule_error"] = str(exc)[:160]

    try:
        from hibs_predictor.data_source_policy import fixture_in_policy_window
        from hibs_predictor.scrapers import sofascore_client as ss

        if fixture_in_policy_window(fixture):
            ent, blocked = ss.probe_team_search(home)
            if blocked:
                out["sofascore_blocked"] = True
                _record_miss(out, "sofascore", "http_403_blocked")
            elif ent and ent.get("id"):
                ev = ss.team_last_xg_summary(int(ent["id"]))
                out["sofascore_team_events"] = ev[:5]
            if ss.sofascore_xg_enabled() and not blocked:
                away_nm = fixture_team_name(fixture, "away")
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
