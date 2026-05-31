"""
Historic FT snapshot backfill for prediction audit calibration (UK + top European leagues).

Flow: fetch finished fixtures → chunked enrich → predict_with_confidence →
``insert_historic_snapshot`` with synthetic ``captured_at`` (kickoff − 2h) and immediate FT results.

Honest limitations
------------------
* **Not point-in-time:** ``enrich_fixture`` uses API stats as returned *today* (form, table, xG,
  injuries). Useful for engine/DQ calibration volume but **inflates** backtest optimism vs true
  pre-kickoff snapshots.
* **Odds:** historical book lines may be missing; predictions may abstain under normal DQ floors
  (never lowered here).
* **API budget:** chunked enrich pauses (``HIBS_ENRICH_CHUNK_*``) and ``HIBS_HISTORIC_MAX_FIXTURES``
  cap processed fixtures per run.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from dotenv import load_dotenv

from hibs_predictor.betting_engine import BettingEngine, prediction_unavailable_payload
from hibs_predictor.config import LEAGUES
from hibs_predictor.data_aggregator import DataAggregator
from hibs_predictor.enrich_chunk import process_in_chunks
from hibs_predictor.live_scores import stamp_api_fixture_id
from hibs_predictor.prediction_log import backtest_report_dict, insert_historic_snapshot
from hibs_predictor.recent_results import (
    _API_SPORTS_FINISHED,
    _fixture_fetch_season_candidates,
)

_DEFAULT_LEAGUES: Tuple[str, ...] = (
    "SCOTLAND",
    "EPL",
    "SCOTLAND_CHAMP",
    "CHAMPIONSHIP",
    "LA_LIGA",
    "SERIE_A",
    "BUNDESLIGA",
    "LIGUE_1",
)

_OPTIONAL_LEAGUES: Tuple[str, ...] = (
    "LEAGUE_ONE",
    "LEAGUE_TWO",
    "UCL",
    "EUROPA_LEAGUE",
    "UECL",
)


def _env_truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def _historic_max_fixtures() -> int:
    try:
        return max(1, int(os.getenv("HIBS_HISTORIC_MAX_FIXTURES", "400")))
    except ValueError:
        return 400


def default_league_codes(*, include_optional: bool = False) -> List[str]:
    """UK + top-5 Europe; optional lower English leagues and European cups via env or flag."""
    raw = (os.getenv("HIBS_HISTORIC_SNAPSHOT_LEAGUES") or "").strip()
    if raw:
        return [c.strip().upper() for c in raw.split(",") if c.strip()]
    codes = list(_DEFAULT_LEAGUES)
    if include_optional or _env_truthy("HIBS_HISTORIC_INCLUDE_OPTIONAL_LEAGUES"):
        codes.extend(_OPTIONAL_LEAGUES)
    return codes


def _api_sports_to_fixture(raw: Dict[str, Any], league_code: str) -> Optional[Dict[str, Any]]:
    fm = raw.get("fixture", {})
    home = (raw.get("teams") or {}).get("home", {})
    away = (raw.get("teams") or {}).get("away", {})
    if not fm or not home or not away:
        return None
    fid = fm.get("id")
    out: Dict[str, Any] = {
        "fixture": {"id": fid, "date": fm.get("date"), "status": fm.get("status", {})},
        "teams": {
            "home": {"id": home.get("id", 0), "name": home.get("name", "?")},
            "away": {"id": away.get("id", 0), "name": away.get("name", "?")},
        },
        "home": {"id": home.get("id", 0), "name": home.get("name", "?")},
        "away": {"id": away.get("id", 0), "name": away.get("name", "?")},
        "date": fm.get("date"),
        "league": league_code,
        "api_fixture_id": fid,
    }
    stamp_api_fixture_id(out)
    return out


def _is_finished_api_row(raw: Dict[str, Any]) -> bool:
    fm = raw.get("fixture") if isinstance(raw.get("fixture"), dict) else {}
    status = fm.get("status") if isinstance(fm.get("status"), dict) else {}
    return str(status.get("short") or "").upper() in _API_SPORTS_FINISHED


def _goals_from_api_row(raw: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    goals = raw.get("goals") or {}
    try:
        return int(goals.get("home")), int(goals.get("away"))
    except (TypeError, ValueError):
        return None


def _kickoff_in_range(kickoff_iso: str, date_from: str, date_to: str) -> bool:
    if not kickoff_iso or len(kickoff_iso) < 10:
        return False
    day = kickoff_iso[:10]
    return date_from <= day <= date_to


def _safe_enrich(aggregator: DataAggregator, fixture: Dict[str, Any], league_code: str) -> Dict[str, Any]:
    """Full enrich when possible; never invent dummy stats unless HIBS_ALLOW_DUMMY=1."""
    try:
        return aggregator.enrich_fixture(fixture, league_code)
    except Exception as exc:
        if _env_truthy("HIBS_ALLOW_DUMMY"):
            league = LEAGUES.get(league_code, {})
            out = dict(fixture)
            out.setdefault("home_recent", [])
            out.setdefault("away_recent", [])
            out.setdefault("home_stats", {})
            out.setdefault("away_stats", {})
            out.setdefault("home_form", 0.5)
            out.setdefault("away_form", 0.5)
            out.setdefault("odds_home", None)
            out.setdefault("odds_draw", None)
            out.setdefault("odds_away", None)
            out.setdefault("odds_available", False)
            out.setdefault("league_factor", league.get("strength_factor", 1.0))
            out.setdefault("xg_source", "goals_proxy")
            out.setdefault(
                "data_quality",
                {"score_pct": 0.0, "blocks": [], "full_scope": False, "strong_scope": False},
            )
            return out
        out = dict(fixture)
        out.setdefault("home_recent", [])
        out.setdefault("away_recent", [])
        out.setdefault("odds_available", False)
        out.setdefault(
            "data_quality",
            {"score_pct": 0.0, "blocks": [], "full_scope": False, "strong_scope": False},
        )
        out["_hibs_enrich_error"] = str(exc)
        return out


def fetch_finished_fixtures_for_league(
    client: Any,
    league_code: str,
    *,
    date_from: str,
    date_to: str,
    now: Optional[datetime] = None,
) -> Tuple[List[Tuple[Dict[str, Any], Dict[str, Any]]], Optional[str]]:
    """Return (normalized_fixture, raw_api_row) pairs and optional error string."""
    league = LEAGUES.get(league_code)
    if not league or not league.get("api_sports_id"):
        return [], "no_api_sports_id"
    now = now or datetime.now(timezone.utc)
    league_id = int(league["api_sports_id"])
    fdo_comp = league.get("football_data_org_id")
    seasons = _fixture_fetch_season_candidates(
        fdo_comp, date_from, date_to, now, league_code=league_code
    )
    collected: Dict[int, Tuple[Dict[str, Any], Dict[str, Any]]] = {}
    last_err: Optional[str] = None
    for season in seasons:
        try:
            raw_list = client.fetch_fixtures_by_league(
                league_id,
                int(season),
                status="FT",
                date_from=date_from,
                date_to=date_to,
            )
        except Exception as exc:
            last_err = str(exc)
            continue
        for raw in raw_list or []:
            if not isinstance(raw, dict):
                continue
            if not _is_finished_api_row(raw):
                continue
            fx = _api_sports_to_fixture(raw, league_code)
            if not fx:
                continue
            if not _kickoff_in_range(str(fx.get("date") or ""), date_from, date_to):
                continue
            fid = fx.get("api_fixture_id") or (fx.get("fixture") or {}).get("id")
            try:
                key = int(fid)
            except (TypeError, ValueError):
                continue
            collected[key] = (fx, raw)
        if collected:
            break
    pairs = list(collected.values())
    pairs.sort(key=lambda p: str(p[0].get("date") or ""))
    return pairs, last_err


def _process_one(
    item: Tuple[str, Dict[str, Any], Dict[str, Any]],
    *,
    aggregator: DataAggregator,
    engine: BettingEngine,
) -> Dict[str, Any]:
    league_code, fixture, raw = item
    goals = _goals_from_api_row(raw)
    if not goals:
        return {"status": "skipped_no_goals", "league": league_code}
    hg, ag = goals
    enriched = _safe_enrich(aggregator, fixture, league_code)
    try:
        prediction = engine.predict_with_confidence(enriched)
    except Exception:
        prediction = prediction_unavailable_payload(enriched, "model_error")
    if prediction.get("prediction_unavailable"):
        return {
            "status": "prediction_unavailable",
            "league": league_code,
            "reason": prediction.get("prediction_unavailable_reason"),
        }
    fm = raw.get("fixture") if isinstance(raw.get("fixture"), dict) else {}
    status = fm.get("status") if isinstance(fm.get("status"), dict) else {}
    short = str(status.get("short") or "FT").upper()
    result = {"home": hg, "away": ag, "status": short}
    action = insert_historic_snapshot(fixture, prediction, result)
    return {"status": action, "league": league_code, "fixture_id": fixture.get("api_fixture_id")}


def _reset_rate_limits_for_batch() -> None:
    """Clear local API guard counters so a dedicated backfill run can fetch fixtures."""
    try:
        from hibs_predictor.rate_limiter import RateLimiter

        RateLimiter().reset_all()
    except Exception:
        pass


def _api_sports_block_reason(client: Any) -> Optional[str]:
    rl = getattr(client, "rate_limiter", None)
    if rl is None:
        return None
    return rl.block_reason(getattr(client, "service_name", "api_sports"))


def run_historic_snapshot(
    *,
    date_from: str,
    date_to: str,
    league_codes: Optional[List[str]] = None,
    max_fixtures: Optional[int] = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    load_dotenv()
    _reset_rate_limits_for_batch()
    codes = league_codes or default_league_codes()
    cap = max_fixtures if max_fixtures is not None else _historic_max_fixtures()
    agg = DataAggregator()
    client = agg.clients.get("api_sports")
    if not client:
        return {
            "ok": False,
            "error": "API_SPORTS_FOOTBALL_KEY required",
            "date_from": date_from,
            "date_to": date_to,
        }

    engine = BettingEngine(agg.get_all_clients())
    now = datetime.now(timezone.utc)
    by_league_fetch: Dict[str, Dict[str, Any]] = {}
    work: List[Tuple[str, Dict[str, Any], Dict[str, Any]]] = []
    seen: Set[int] = set()
    api_errors: List[Dict[str, str]] = []

    for code in codes:
        if len(work) >= cap:
            break
        pairs, err = fetch_finished_fixtures_for_league(
            client, code, date_from=date_from, date_to=date_to, now=now
        )
        by_league_fetch[code] = {"fetched_ft": len(pairs), "api_error": err}
        if err and not pairs:
            api_errors.append({"league": code, "error": err})
        for fx, raw in pairs:
            fid = fx.get("api_fixture_id") or (fx.get("fixture") or {}).get("id")
            try:
                iid = int(fid)
            except (TypeError, ValueError):
                continue
            if iid in seen:
                continue
            seen.add(iid)
            if len(work) >= cap:
                break
            work.append((code, fx, raw))

    counts: Dict[str, int] = {
        "inserted": 0,
        "updated_unscored": 0,
        "skipped_scored": 0,
        "skipped_unavailable": 0,
        "skipped_no_goals": 0,
        "skipped_no_id": 0,
        "error": 0,
        "other": 0,
    }
    by_league_write: Dict[str, Dict[str, int]] = {}

    def worker(item: Tuple[str, Dict[str, Any], Dict[str, Any]]) -> Dict[str, Any]:
        return _process_one(item, aggregator=agg, engine=engine)

    outcomes = process_in_chunks(work, worker)
    for oc in outcomes:
        if not isinstance(oc, dict):
            counts["other"] += 1
            continue
        st = str(oc.get("status") or "other")
        lg = str(oc.get("league") or "?")
        bucket = by_league_write.setdefault(lg, {})
        bucket[st] = bucket.get(st, 0) + 1
        if st in counts:
            counts[st] += 1
        elif st == "prediction_unavailable":
            counts["skipped_unavailable"] += 1
        else:
            counts["other"] += 1

    scored_added = counts["inserted"] + counts["updated_unscored"]
    backtest = backtest_report_dict(days=120)
    rate_guard = _api_sports_block_reason(client)
    if len(work) == 0 and rate_guard:
        api_errors.append({"league": "*", "error": f"api_sports blocked: {rate_guard}"})
    limitations = [
        "Enrich uses current-season API stats fetched today, not true point-in-time pre-kickoff data.",
        "captured_at is synthetic (kickoff − 2h); backtest_report_dict dedupes on that timestamp.",
        "Historic odds may be absent; abstains count as skipped_unavailable (DQ floors unchanged).",
        f"Processed at most {cap} fixtures this run (HIBS_HISTORIC_MAX_FIXTURES).",
    ]

    summary: Dict[str, Any] = {
        "ok": True,
        "date_from": date_from,
        "date_to": date_to,
        "leagues": codes,
        "max_fixtures_cap": cap,
        "fixtures_queued": len(work),
        "by_league_fetch": by_league_fetch,
        "by_league_write": by_league_write,
        "write_counts": counts,
        "scored_snapshots_added": scored_added,
        "api_errors": api_errors,
        "backtest_120d": backtest,
        "limitations": limitations,
    }
    if verbose:
        summary["outcomes_sample"] = outcomes[:20]
    return summary


def print_summary_json(summary: Dict[str, Any]) -> None:
    print(json.dumps(summary, indent=2, default=str))
