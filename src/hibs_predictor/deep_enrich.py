"""Targeted second-pass enrichment for fixtures below a data-quality target (e.g. 90%)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from hibs_predictor.data_quality import (
    _SHOWPIECE_LEAGUES,
    _effective_xg_source,
    _has_stats,
    _position_ok,
    _xg_points,
    compute_fixture_data_quality,
)
from hibs_predictor.fixture_utils import fixture_team_id, fixture_team_name

if TYPE_CHECKING:
    from hibs_predictor.data_aggregator import DataAggregator

XG_TARGET_EARNED = 16.0
DEEP_BAND_MIN = 75.0
SHOWPIECE_DEEP_TARGET = 95.0
SHOWPIECE_DEEP_BAND_MIN = 0.0


def is_showpiece_league(league_code: Optional[str]) -> bool:
    """UEFA cups / internationals where thin first-pass rows must be rescued (not skipped)."""
    return str(league_code or "").strip().upper() in _SHOWPIECE_LEAGUES


def deep_band_min(league_code: Optional[str]) -> float:
    """Minimum raw DQ before deep pass runs; showpieces allow rescue from any score."""
    if deep_enrich_rescue_low_enabled():
        return SHOWPIECE_DEEP_BAND_MIN
    return SHOWPIECE_DEEP_BAND_MIN if is_showpiece_league(league_code) else DEEP_BAND_MIN


def _env_truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def dev_full_dq_enabled() -> bool:
    """Local developer profile: 90%% target across the fixture window, rescue thin rows."""
    if _env_truthy("HIBS_DEV_FULL_DQ"):
        return True
    return (os.getenv("HIBS_ENV") or "").strip().lower() in ("dev", "development", "local")


def deep_enrich_rescue_low_enabled() -> bool:
    """Allow deep pass when first-pass DQ is below the usual 75%% band (e.g. after cache clear)."""
    if dev_full_dq_enabled():
        return True
    return _env_truthy("HIBS_DEEP_ENRICH_RESCUE_LOW")


def deep_enrich_today_only() -> bool:
    """When set, second-pass enrich runs only for kickoffs today (saves API on the rest of the window)."""
    if dev_full_dq_enabled():
        return False
    return _env_truthy("HIBS_DEEP_ENRICH_TODAY_ONLY")


def deep_enrich_window_days() -> int:
    """Kickoffs within this many days (UTC) may get deep enrich when today-only is off."""
    if dev_full_dq_enabled():
        try:
            return max(1, min(14, int(os.getenv("HIBS_DEEP_ENRICH_WINDOW_DAYS", "7"))))
        except ValueError:
            return 7
    raw = (os.getenv("HIBS_DEEP_ENRICH_WINDOW_DAYS") or "").strip()
    if not raw:
        return 0
    try:
        return max(0, min(14, int(raw)))
    except ValueError:
        return 0


def fixture_within_deep_window(fixture: Dict[str, Any], *, days: int) -> bool:
    kick = _fixture_kickoff_utc(fixture)
    if not kick or days <= 0:
        return False
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days)
    return now - timedelta(hours=6) <= kick <= end


def _deep_enrich_horizon_days(league_code: Optional[str] = None) -> int:
    from hibs_predictor.tournament_focus import friendlies_fetch_window_days, friendlies_max_data_active

    if league_code and friendlies_max_data_active(league_code=league_code):
        return friendlies_fetch_window_days()
    if not deep_enrich_today_only():
        window = deep_enrich_window_days()
        return window if window > 0 else 14
    window = deep_enrich_window_days()
    return window if window > 0 else 0


def deep_enrich_applies_to_fixture(
    fixture: Dict[str, Any],
    league_code: Optional[str] = None,
) -> bool:
    """Whether this kickoff is eligible for a second-pass enrich."""
    if fixture_is_today(fixture):
        return True
    from hibs_predictor.tournament_focus import friendlies_max_data_active

    if league_code and friendlies_max_data_active(league_code=league_code):
        return fixture_within_deep_window(fixture, days=_deep_enrich_horizon_days(league_code))
    if not deep_enrich_today_only():
        window = deep_enrich_window_days()
        if window <= 0:
            return True
        return fixture_within_deep_window(fixture, days=window)
    window = deep_enrich_window_days()
    if window > 0:
        return fixture_within_deep_window(fixture, days=window)
    return False


def summer_daily_deep_target_pct(league_code: str) -> Optional[float]:
    """Realistic deep-enrich target for Nordics during domestic offseason (not inflated)."""
    from hibs_predictor.tournament_focus import domestic_offseason_active, is_summer_daily_league

    if not domestic_offseason_active() or not is_summer_daily_league(league_code):
        return None
    return 88.0


def deep_enrich_target_pct(league_code: Optional[str] = None) -> float:
    """Return target DQ %% when deep pass is enabled; 0 disables."""
    if dev_full_dq_enabled() and not (os.getenv("HIBS_TARGET_DQ_PCT") or "").strip():
        if league_code:
            summer = summer_daily_deep_target_pct(league_code)
            if summer is not None:
                return summer
            if is_showpiece_league(league_code):
                return SHOWPIECE_DEEP_TARGET
        return 90.0
    raw = (os.getenv("HIBS_TARGET_DQ_PCT") or "").strip()
    if raw:
        try:
            target = max(DEEP_BAND_MIN, min(100.0, float(raw)))
            if league_code and is_showpiece_league(league_code):
                return max(target, SHOWPIECE_DEEP_TARGET)
            return target
        except ValueError:
            pass
    if _env_truthy("HIBS_DEEP_ENRICH"):
        if league_code:
            summer = summer_daily_deep_target_pct(league_code)
            if summer is not None:
                return summer
            if is_showpiece_league(league_code):
                return SHOWPIECE_DEEP_TARGET
        return 90.0
    return 0.0


def deep_enrich_max_retries(league_code: Optional[str] = None) -> int:
    from hibs_predictor.tournament_focus import friendlies_max_data_active

    showpiece = is_showpiece_league(league_code) or friendlies_max_data_active(league_code=league_code)
    default = "3" if showpiece else "2"
    try:
        return max(1, min(4, int(os.getenv("HIBS_DEEP_ENRICH_MAX_RETRIES", default))))
    except ValueError:
        return 3 if showpiece else 2


def _current_xg_earned(enriched: Dict[str, Any]) -> float:
    src = _effective_xg_source(enriched)
    n_h = float(enriched.get("home_recent_n") or 0)
    n_a = float(enriched.get("away_recent_n") or 0)
    return _xg_points(src, n_h, n_a, enriched)


def _weak_block_keys(dq: Dict[str, Any]) -> List[str]:
    keys: List[str] = []
    for block in dq.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        key = str(block.get("key") or "")
        if not key:
            continue
        try:
            earned = float(block.get("earned") or 0)
            max_pts = float(block.get("max") or 0)
        except (TypeError, ValueError):
            continue
        if max_pts > 0 and earned < max_pts * 0.85:
            keys.append(key)
    return keys


def analyze_dq_gaps(enriched: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize which scoring blocks keep a fixture below a DQ target."""
    dq = compute_fixture_data_quality(enriched)
    pct = float(dq.get("score_pct") or 0)
    weak = _weak_block_keys(dq)
    gaps: List[Dict[str, Any]] = []
    for block in dq.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        key = block.get("key")
        if key not in weak:
            continue
        try:
            earned = float(block.get("earned") or 0)
            max_pts = float(block.get("max") or 0)
        except (TypeError, ValueError):
            continue
        gaps.append(
            {
                "key": key,
                "label": block.get("label"),
                "earned": earned,
                "max": max_pts,
                "shortfall": round(max(0.0, max_pts * 0.85 - earned), 2),
            }
        )
    return {"score_pct": pct, "weak_keys": weak, "gaps": gaps, "field_scores": dq.get("field_scores")}


def _invalidate_cache_key(aggregator: "DataAggregator", cache_key: str) -> None:
    path = aggregator.cache._get_cache_path(cache_key)
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def _fixture_kickoff_utc(fixture: Dict[str, Any]) -> Optional[datetime]:
    raw = fixture.get("date")
    if not raw and isinstance(fixture.get("fixture"), dict):
        raw = fixture["fixture"].get("date")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def fixture_is_today(fixture: Dict[str, Any]) -> bool:
    kick = _fixture_kickoff_utc(fixture)
    if not kick:
        return False
    today = datetime.now(timezone.utc).date()
    return kick.astimezone(timezone.utc).date() == today


def _fill_recent_if_needed(
    aggregator: "DataAggregator",
    enriched: Dict[str, Any],
    fixture: Dict[str, Any],
    league_code: str,
    *,
    fdo_comp: Optional[str],
) -> None:
    home_id = fixture_team_id(fixture, "home") or fixture_team_id(enriched, "home")
    away_id = fixture_team_id(fixture, "away") or fixture_team_id(enriched, "away")
    home_nm = fixture_team_name(fixture, "home") or fixture_team_name(enriched, "home")
    away_nm = fixture_team_name(fixture, "away") or fixture_team_name(enriched, "away")
    prefer_name_ids = fixture.get("source") == "fotmob_public" or str(
        (fixture.get("fixture") or {}).get("id") if isinstance(fixture.get("fixture"), dict) else fixture.get("id")
        or ""
    ).startswith("fotmob_")
    from hibs_predictor.data_aggregator import _recent_match_rates

    if home_id and float(enriched.get("home_recent_n") or 0) < 8:
        try:
            enriched["home_recent"] = aggregator._fetch_team_recent_matches(
                home_id,
                fdo_comp=fdo_comp,
                team_name=home_nm,
                prefer_name_resolution=prefer_name_ids,
                league_code=league_code,
            )
            rates = _recent_match_rates(enriched["home_recent"], home_id, team_name=home_nm or "")
            enriched["home_recent_n"] = int(rates["n"])
            enriched["home_btts_rate"] = rates["btts_rate"]
            enriched["home_over25_rate"] = rates["over25_rate"]
            enriched["home_over15_rate"] = rates["over15_rate"]
        except Exception:
            pass
    if away_id and float(enriched.get("away_recent_n") or 0) < 8:
        try:
            enriched["away_recent"] = aggregator._fetch_team_recent_matches(
                away_id,
                fdo_comp=fdo_comp,
                team_name=away_nm,
                prefer_name_resolution=prefer_name_ids,
                league_code=league_code,
            )
            rates = _recent_match_rates(enriched["away_recent"], away_id, team_name=away_nm or "")
            enriched["away_recent_n"] = int(rates["n"])
            enriched["away_btts_rate"] = rates["btts_rate"]
            enriched["away_over25_rate"] = rates["over25_rate"]
            enriched["away_over15_rate"] = rates["over15_rate"]
        except Exception:
            pass


def _fill_stats_if_needed(
    aggregator: "DataAggregator",
    enriched: Dict[str, Any],
    league_code: str,
    league_api_id: Optional[int],
    season: int,
    *,
    fdo_comp: Optional[str],
) -> None:
    home_id = fixture_team_id(enriched, "home")
    away_id = fixture_team_id(enriched, "away")
    from hibs_predictor.data_aggregator import _cup_domestic_stats_league, _recent_match_rates
    from hibs_predictor.fixture_utils import is_cup_competition

    stats_code = league_code
    stats_api_id = league_api_id
    if is_cup_competition(league_code):
        stats_code, stats_api_id = _cup_domestic_stats_league(league_code)

    home_rates = _recent_match_rates(enriched.get("home_recent") or [], home_id or 0)
    away_rates = _recent_match_rates(enriched.get("away_recent") or [], away_id or 0)
    if home_id and not _has_stats(enriched.get("home_stats")):
        try:
            enriched["home_stats"] = aggregator._fetch_team_stats(
                home_id, stats_code, stats_api_id, season, home_rates, fdo_comp=fdo_comp
            )
        except Exception:
            pass
    if away_id and not _has_stats(enriched.get("away_stats")):
        try:
            enriched["away_stats"] = aggregator._fetch_team_stats(
                away_id, stats_code, stats_api_id, season, away_rates, fdo_comp=fdo_comp
            )
        except Exception:
            pass


def _fill_standings_if_needed(
    aggregator: "DataAggregator",
    enriched: Dict[str, Any],
    fixture: Dict[str, Any],
    league_code: str,
    league_api_id: Optional[int],
    season: int,
    *,
    fdo_comp: Optional[str],
) -> None:
    home_id = fixture_team_id(fixture, "home")
    away_id = fixture_team_id(fixture, "away")
    home_nm = fixture_team_name(fixture, "home")
    away_nm = fixture_team_name(fixture, "away")
    hp = enriched.get("home_position") or {}
    ap = enriched.get("away_position") or {}
    if not _position_ok(hp) and league_api_id and "api_sports" in aggregator.clients:
        try:
            row = aggregator._fetch_api_sports_position_with_fallback(home_id, league_api_id, season)
            if row:
                enriched["home_position"] = row
        except Exception:
            pass
    if not _position_ok(ap) and league_api_id and "api_sports" in aggregator.clients:
        try:
            row = aggregator._fetch_api_sports_position_with_fallback(away_id, league_api_id, season)
            if row:
                enriched["away_position"] = row
        except Exception:
            pass
    if fdo_comp and "football_data_org" in aggregator.clients:
        if not _position_ok(enriched.get("home_position")):
            try:
                row = aggregator._fetch_football_data_position_with_fallback(home_id, home_nm, fdo_comp, season)
                if row:
                    enriched["home_position"] = row
            except Exception:
                pass
        if not _position_ok(enriched.get("away_position")):
            try:
                row = aggregator._fetch_football_data_position_with_fallback(away_id, away_nm, fdo_comp, season)
                if row:
                    enriched["away_position"] = row
            except Exception:
                pass


def apply_xg_ladder(
    aggregator: "DataAggregator",
    fixture: Dict[str, Any],
    league_code: str,
    enriched: Dict[str, Any],
    *,
    league_strength: float = 1.0,
) -> Dict[str, Any]:
    """
    Try xG sources in sequence until the xG block reaches at least 16/18 points.
    Order: API fixture → scraped ladder (understat/fbref/statsbomb) → supplemental understat batch.
    """
    if _current_xg_earned(enriched) >= XG_TARGET_EARNED:
        return enriched

    fx = fixture.get("fixture") if isinstance(fixture.get("fixture"), dict) else {}
    raw_fid = fx.get("id") if isinstance(fx, dict) else fixture.get("id")
    try:
        fixture_id = int(raw_fid) if raw_fid not in (None, "", "0", 0) else None
    except (TypeError, ValueError):
        fixture_id = None

    from hibs_predictor.data_aggregator import _recent_match_rates

    home_id = fixture_team_id(fixture, "home") or 0
    away_id = fixture_team_id(fixture, "away") or 0
    home_rates = _recent_match_rates(enriched.get("home_recent") or [], home_id)
    away_rates = _recent_match_rates(enriched.get("away_recent") or [], away_id)

    if fixture_id:
        _invalidate_cache_key(aggregator, f"xg_data_v2_{fixture_id}")
        try:
            xh, xa, tag = aggregator._fetch_expected_goals(
                fixture_id,
                home_rates,
                away_rates,
                league_strength,
                allow_statistics_xg=True,
                league_code=league_code,
            )
            enriched["xg_home"], enriched["xg_away"], enriched["xg_source"] = float(xh), float(xa), tag
        except Exception:
            pass
        if _current_xg_earned(enriched) >= XG_TARGET_EARNED:
            return enriched

    if _current_xg_earned(enriched) >= XG_TARGET_EARNED:
        return enriched

    prev_skip = os.environ.get("HIBS_SKIP_HEAVY_WHEN_API_STRONG")
    os.environ["HIBS_SKIP_HEAVY_WHEN_API_STRONG"] = "0"
    try:
        from hibs_predictor.scraped_xg import apply_scraped_xg_to_enriched
        from hibs_predictor.scrapers.supplemental import collect_supplemental

        sup = collect_supplemental(fixture, league_code, enriched)
        if isinstance(sup, dict) and sup:
            merged = dict(enriched.get("supplemental") or {})
            merged.update(sup)
            enriched["supplemental"] = merged
        enriched = apply_scraped_xg_to_enriched(fixture, league_code, enriched)
    except Exception:
        pass
    finally:
        if prev_skip is None:
            os.environ.pop("HIBS_SKIP_HEAVY_WHEN_API_STRONG", None)
        else:
            os.environ["HIBS_SKIP_HEAVY_WHEN_API_STRONG"] = prev_skip

    return enriched


def _fill_odds_if_needed(
    aggregator: "DataAggregator",
    enriched: Dict[str, Any],
    fixture: Dict[str, Any],
    league_code: str,
) -> None:
    book = bool(enriched.get("odds_available")) or all(
        enriched.get(k) is not None and float(enriched.get(k) or 0) > 1.0
        for k in ("odds_home", "odds_draw", "odds_away")
    )
    mo = enriched.get("market_odds") or {}
    side_ok = bool((mo.get("btts") or {}).get("yes")) or bool((mo.get("totals_2_5") or {}).get("over"))
    if book and side_ok:
        return
    fx = fixture.get("fixture") if isinstance(fixture.get("fixture"), dict) else {}
    fid = fx.get("id") if isinstance(fx, dict) else fixture.get("id")
    if fid:
        _invalidate_cache_key(aggregator, f"odds_bundle_{fid}_{league_code}")
    try:
        bundle = aggregator._fetch_odds_bundle(fixture, league_code)
        enriched["odds_home"] = bundle["odds_home"]
        enriched["odds_draw"] = bundle["odds_draw"]
        enriched["odds_away"] = bundle["odds_away"]
        enriched["odds_available"] = bundle["odds_available"]
        enriched["market_odds"] = bundle["market_odds"]
        enriched["all_bookmaker_odds"] = bundle.get("all_bookmaker_odds") or []
    except Exception:
        pass


def _apply_friendlies_supplemental_rescue(
    aggregator: "DataAggregator",
    enriched: Dict[str, Any],
    fixture: Dict[str, Any],
    league_code: str,
) -> None:
    """FotMob calendar + national xG tables + injuries for pre–WC friendlies max-data."""
    from hibs_predictor.tournament_focus import friendlies_max_data_active

    if not friendlies_max_data_active(league_code=league_code):
        return
    home_id = fixture_team_id(fixture, "home") or fixture_team_id(enriched, "home")
    away_id = fixture_team_id(fixture, "away") or fixture_team_id(enriched, "away")
    try:
        from hibs_predictor.scrapers.thin_data_rescue import apply_thin_data_rescue

        enriched.update(
            apply_thin_data_rescue(
                enriched,
                fixture,
                league_code,
                home_id=home_id,
                away_id=away_id,
                supplemental=enriched.get("supplemental"),
                force=True,
            )
        )
    except Exception:
        pass
    try:
        from hibs_predictor.scrapers.supplemental import collect_supplemental

        sup = collect_supplemental(fixture, league_code, enriched)
        if isinstance(sup, dict) and sup:
            merged = dict(enriched.get("supplemental") or {})
            merged.update(sup)
            enriched["supplemental"] = merged
    except Exception:
        pass
    _fill_injuries_if_needed(aggregator, enriched, fixture)


def _fill_injuries_if_needed(aggregator: "DataAggregator", enriched: Dict[str, Any], fixture: Dict[str, Any]) -> None:
    if isinstance(enriched.get("fixture_injuries"), list) and enriched["fixture_injuries"]:
        return
    fx = fixture.get("fixture") if isinstance(fixture.get("fixture"), dict) else {}
    raw_fid = fx.get("id") if isinstance(fx, dict) else fixture.get("id")
    try:
        fid_int = int(raw_fid) if raw_fid not in (None, "", "0", 0) else 0
    except (TypeError, ValueError):
        fid_int = 0
    if fid_int and "api_sports" in aggregator.clients:
        try:
            enriched["fixture_injuries"] = aggregator.clients["api_sports"].fetch_injuries(fid_int)
        except Exception:
            pass


def deep_enrich_pass(
    aggregator: "DataAggregator",
    fixture: Dict[str, Any],
    league_code: str,
    enriched: Dict[str, Any],
    *,
    target_pct: float = 90.0,
    max_retries: Optional[int] = None,
    min_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Fill missing weak fields and retry until target or max_retries.

    Domestic leagues normally run only in the 75–(target-1)% band; UEFA showpieces (e.g. UECL final)
  may rescue from any raw score when min_pct is 0.
    """
    floor = DEEP_BAND_MIN if min_pct is None else float(min_pct)
    retries = max_retries if max_retries is not None else deep_enrich_max_retries(league_code)
    from hibs_predictor.config import LEAGUES
    from hibs_predictor.data_aggregator import _season_candidates

    league = LEAGUES.get(league_code, {})
    league_api_id = league.get("api_sports_id")
    fdo_comp = league.get("football_data_org_id")
    season = _season_candidates(datetime.now(), league_code=league_code)[0]
    league_strength = float(league.get("strength_factor") or 1.0)

    for _ in range(retries):
        dq = compute_fixture_data_quality(enriched)
        pct = float(dq.get("score_pct") or 0)
        if pct >= target_pct:
            break
        if pct < floor:
            break
        weak = set(_weak_block_keys(dq))
        if not weak and floor <= SHOWPIECE_DEEP_BAND_MIN and is_showpiece_league(league_code):
            weak = {
                "recent_home",
                "recent_away",
                "stats_home",
                "stats_away",
                "book_1x2",
                "side_markets",
                "xg",
            }
        if not weak:
            break

        if weak & {"recent_home", "recent_away"}:
            _fill_recent_if_needed(aggregator, enriched, fixture, league_code, fdo_comp=fdo_comp)
        if weak & {"stats_home", "stats_away"}:
            _fill_stats_if_needed(
                aggregator, enriched, league_code, league_api_id, season, fdo_comp=fdo_comp
            )
        if weak & {"stand_home", "stand_away"}:
            _fill_standings_if_needed(
                aggregator, enriched, fixture, league_code, league_api_id, season, fdo_comp=fdo_comp
            )
        if "xg" in weak:
            enriched = apply_xg_ladder(
                aggregator, fixture, league_code, enriched, league_strength=league_strength
            )
        if weak & {"book_1x2", "side_markets"}:
            _fill_odds_if_needed(aggregator, enriched, fixture, league_code)
        if weak & {"supplemental"}:
            try:
                from hibs_predictor.scrapers.supplemental import collect_supplemental

                sup = collect_supplemental(fixture, league_code, enriched)
                if isinstance(sup, dict):
                    merged = dict(enriched.get("supplemental") or {})
                    merged.update(sup)
                    enriched["supplemental"] = merged
            except Exception:
                pass
        if "injuries" in weak:
            _fill_injuries_if_needed(aggregator, enriched, fixture)

        _apply_friendlies_supplemental_rescue(aggregator, enriched, fixture, league_code)

        try:
            from hibs_predictor.scraped_xg import apply_scraped_xg_to_enriched

            enriched = apply_scraped_xg_to_enriched(fixture, league_code, enriched)
        except Exception:
            pass

    try:
        enriched["data_quality"] = compute_fixture_data_quality(enriched)
    except Exception:
        pass
    return enriched


def deep_enrich_plan(
    fixture: Dict[str, Any],
    league_code: str,
    enriched: Dict[str, Any],
) -> Optional[Tuple[float, float]]:
    """
    When a second-pass enrich is worth API calls: (target_pct, min_pct).
    Returns None when disabled, already at target, wrong day, or out of band.
    """
    target = deep_enrich_target_pct(league_code)
    if target <= 0 and is_showpiece_league(league_code) and fixture_is_today(fixture):
        target = SHOWPIECE_DEEP_TARGET
    if target <= 0:
        return None
    if not deep_enrich_applies_to_fixture(fixture, league_code):
        return None
    dq = enriched.get("data_quality") or compute_fixture_data_quality(enriched)
    pct = float(dq.get("score_pct") or 0)
    if pct >= target:
        return None
    floor = deep_band_min(league_code)
    if pct < floor:
        return None
    return (target, floor)


def maybe_deep_enrich(
    aggregator: "DataAggregator",
    fixture: Dict[str, Any],
    league_code: str,
    enriched: Dict[str, Any],
) -> Dict[str, Any]:
    """Run deep pass only when deep_enrich_plan says API spend is warranted."""
    plan = deep_enrich_plan(fixture, league_code, enriched)
    if not plan:
        return enriched
    target, floor = plan
    return deep_enrich_pass(
        aggregator,
        fixture,
        league_code,
        enriched,
        target_pct=target,
        min_pct=floor,
    )


# Leagues without Understat slug — spend API statistics-xG budget here before top-5 leagues.
# Summer daily (Nordics) immediately after WC / friendlies during domestic offseason.
_XG_GAP_LEAGUE_PRIORITY: tuple[str, ...] = (
    "WORLD_CUP",
    "INTL_FRIENDLIES",
    "NORWAY_ELITESERIEN",
    "FINLAND_VEIKKAUSLIIGA",
    "DENMARK_SL",
    "UCL",
    "EUROPA_LEAGUE",
    "UECL",
    "GREECE_SL",
    "AUSTRIA_BL",
    "BELGIUM_FIRST",
    "EREDIVISIE",
    "PRIMEIRA",
    "LA_LIGA",
    "SERIE_A",
    "BUNDESLIGA",
    "LIGUE_1",
    "EUROS",
    "NATIONS_LEAGUE",
)


def league_codes_priority_xg_gaps(codes: List[str]) -> List[str]:
    """Pull Nordic / secondary European / international cups ahead for measured-xG budget."""
    head = [c for c in _XG_GAP_LEAGUE_PRIORITY if c in codes]
    tail = [c for c in codes if c not in head]
    return head + tail


def _dashboard_row_as_enrich_fixture(row: Dict[str, Any]) -> Dict[str, Any]:
    """Rebuild minimal fixture dict for deep enrich from a dashboard row."""
    return {
        "fixture": {"id": row.get("id"), "date": row.get("date")},
        "date": row.get("date"),
        "source": row.get("source"),
        "teams": {
            "home": {"id": row.get("home_id"), "name": row.get("home")},
            "away": {"id": row.get("away_id"), "name": row.get("away")},
        },
        "competition_meta": row.get("competition_meta") if isinstance(row.get("competition_meta"), dict) else {},
    }


def _merge_enrich_into_dashboard_row(row: Dict[str, Any], enriched: Dict[str, Any]) -> None:
    """Copy enrich fields back without clobbering prediction / display labels."""
    preserve = frozenset(
        {
            "prediction",
            "home",
            "away",
            "league_name",
            "league_flag",
            "home_last10",
            "away_last10",
            "has_value_bet",
            "compact_xg_home",
            "compact_xg_away",
            "dashboard_region",
            "kickoff_time",
            "kickoff_sort",
        }
    )
    for key, val in enriched.items():
        if key in preserve:
            continue
        row[key] = val


def reboost_dashboard_data_quality(
    aggregator: "DataAggregator",
    rows: List[Dict[str, Any]],
    *,
    max_rows: Optional[int] = None,
) -> int:
    """
    Second-pass deep enrich on dashboard rows still below target (cold-cache recovery).

    Runs when ``HIBS_DEV_FULL_DQ=1`` or ``HIBS_BUNDLE_DQ_REBOOST=1``.
    """
    if deep_enrich_target_pct() <= 0:
        return 0
    if not dev_full_dq_enabled() and not _env_truthy("HIBS_BUNDLE_DQ_REBOOST"):
        return 0

    limit = max_rows
    if limit is None:
        try:
            limit = int(os.getenv("HIBS_BUNDLE_DQ_REBOOST_MAX", "0"))
        except ValueError:
            limit = 0
    if dev_full_dq_enabled() and limit <= 0:
        limit = 250

    boosted = 0
    for row in rows or []:
        if limit > 0 and boosted >= limit:
            break
        league = str(row.get("league") or "")
        if not league:
            continue
        fixture = _dashboard_row_as_enrich_fixture(row)
        if not deep_enrich_applies_to_fixture(fixture, league):
            continue
        dq = row.get("data_quality") if isinstance(row.get("data_quality"), dict) else {}
        try:
            pct = float(dq.get("score_pct") or 0)
        except (TypeError, ValueError):
            pct = 0.0
        target = deep_enrich_target_pct(league)
        if target <= 0 or pct >= target:
            continue
        enriched = dict(row)
        enriched.setdefault("teams", fixture.get("teams"))
        enriched.setdefault("fixture", fixture.get("fixture"))
        try:
            out = maybe_deep_enrich(aggregator, fixture, league, enriched)
        except Exception as exc:
            print(f"[DQ reboost] {league} {row.get('id')}: {exc!r}")
            continue
        _merge_enrich_into_dashboard_row(row, out)
        boosted += 1
    return boosted


def league_codes_priority_today(codes: List[str], fixtures_by_code: Dict[str, List[Dict[str, Any]]]) -> List[str]:
    """Leagues with a kickoff today first (API budget), then the rest."""
    ordered = list(codes)
    if _env_truthy("HIBS_ENRICH_PRIORITY_TODAY"):
        today_first: List[str] = []
        rest: List[str] = []
        for code in codes:
            rows = fixtures_by_code.get(code) or []
            if any(fixture_is_today(r) for r in rows):
                today_first.append(code)
            else:
                rest.append(code)
        ordered = today_first + rest
    return league_codes_priority_xg_gaps(ordered)
