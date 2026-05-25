"""Targeted second-pass enrichment for fixtures below a data-quality target (e.g. 90%)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from hibs_predictor.data_quality import (
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


def _env_truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def deep_enrich_target_pct() -> float:
    """Return target DQ %% when deep pass is enabled; 0 disables."""
    raw = (os.getenv("HIBS_TARGET_DQ_PCT") or "").strip()
    if raw:
        try:
            return max(DEEP_BAND_MIN, min(100.0, float(raw)))
        except ValueError:
            pass
    if _env_truthy("HIBS_DEEP_ENRICH"):
        return 90.0
    return 0.0


def deep_enrich_max_retries() -> int:
    try:
        return max(1, min(4, int(os.getenv("HIBS_DEEP_ENRICH_MAX_RETRIES", "2"))))
    except ValueError:
        return 2


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
    from hibs_predictor.data_aggregator import _recent_match_rates

    if home_id and float(enriched.get("home_recent_n") or 0) < 8:
        try:
            enriched["home_recent"] = aggregator._fetch_team_recent_matches(home_id, fdo_comp=fdo_comp)
            rates = _recent_match_rates(enriched["home_recent"], home_id)
            enriched["home_recent_n"] = int(rates["n"])
            enriched["home_btts_rate"] = rates["btts_rate"]
            enriched["home_over25_rate"] = rates["over25_rate"]
            enriched["home_over15_rate"] = rates["over15_rate"]
        except Exception:
            pass
    if away_id and float(enriched.get("away_recent_n") or 0) < 8:
        try:
            enriched["away_recent"] = aggregator._fetch_team_recent_matches(away_id, fdo_comp=fdo_comp)
            rates = _recent_match_rates(enriched["away_recent"], away_id)
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
    from hibs_predictor.data_aggregator import _recent_match_rates

    home_rates = _recent_match_rates(enriched.get("home_recent") or [], home_id or 0)
    away_rates = _recent_match_rates(enriched.get("away_recent") or [], away_id or 0)
    if home_id and not _has_stats(enriched.get("home_stats")):
        try:
            enriched["home_stats"] = aggregator._fetch_team_stats(
                home_id, league_code, league_api_id, season, home_rates, fdo_comp=fdo_comp
            )
        except Exception:
            pass
    if away_id and not _has_stats(enriched.get("away_stats")):
        try:
            enriched["away_stats"] = aggregator._fetch_team_stats(
                away_id, league_code, league_api_id, season, away_rates, fdo_comp=fdo_comp
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
) -> Dict[str, Any]:
    """
    Fill only missing weak fields for fixtures in the 75–(target-1)% band; retry until target or max_retries.
    """
    retries = max_retries if max_retries is not None else deep_enrich_max_retries()
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
        if pct < DEEP_BAND_MIN:
            break
        weak = set(_weak_block_keys(dq))
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


def maybe_deep_enrich(
    aggregator: "DataAggregator",
    fixture: Dict[str, Any],
    league_code: str,
    enriched: Dict[str, Any],
) -> Dict[str, Any]:
    """Run deep pass when HIBS_TARGET_DQ_PCT / HIBS_DEEP_ENRICH is set and score is below target."""
    target = deep_enrich_target_pct()
    if target <= 0:
        return enriched
    dq = enriched.get("data_quality") or compute_fixture_data_quality(enriched)
    pct = float(dq.get("score_pct") or 0)
    if pct >= target or pct < DEEP_BAND_MIN:
        return enriched
    return deep_enrich_pass(aggregator, fixture, league_code, enriched, target_pct=target)


def league_codes_priority_today(codes: List[str], fixtures_by_code: Dict[str, List[Dict[str, Any]]]) -> List[str]:
    """Leagues with a kickoff today first (API budget), then the rest."""
    if not _env_truthy("HIBS_ENRICH_PRIORITY_TODAY"):
        return list(codes)
    today_first: List[str] = []
    rest: List[str] = []
    for code in codes:
        rows = fixtures_by_code.get(code) or []
        if any(fixture_is_today(r) for r in rows):
            today_first.append(code)
        else:
            rest.append(code)
    return today_first + rest
