"""Public read-only performance tracker — pre-kickoff locks + cron settlement."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from hibs_predictor.prediction_log import (
    _clv_pp_from_enrich,
    _format_score,
    _league_cohort,
    _model_pct_for_pick,
    _parse_kickoff_iso,
    _value_pick_snapshot,
    _value_pick_result_label,
    _db_path,
    init_db,
    prediction_log_enabled,
    pred_log_sync_cron_status,
    report_summary_dict,
    scale_readiness_dict,
)


def _lock_grace_seconds() -> int:
    try:
        return max(0, min(600, int(os.getenv("HIBS_TRACKER_LOCK_GRACE_SEC", "120"))))
    except ValueError:
        return 120


def snapshot_locked_pre_kickoff(captured_at: str, kickoff_iso: str) -> bool:
    """True when the snapshot was captured at or before kickoff (with small grace)."""
    cap = _parse_kickoff_iso(str(captured_at or ""))
    ko = _parse_kickoff_iso(str(kickoff_iso or ""))
    if cap is None or ko is None:
        return False
    return cap <= ko + timedelta(seconds=_lock_grace_seconds())


def _prediction_hash(fixture_id: int, captured_at: str, prediction_json: str) -> str:
    payload = f"{fixture_id}|{captured_at}|{prediction_json}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _row_to_locked_entry(r: sqlite3.Row, *, official_lock: bool) -> Dict[str, Any]:
    try:
        pred = json.loads(r["prediction_json"])
    except Exception:
        pred = {}
    if not isinstance(pred, dict):
        pred = {}
    pick = (pred.get("predicted_outcome") or "").lower()
    value_snap = _value_pick_snapshot(pred)
    captured = str(r["captured_at"] or "")
    kickoff = str(r["kickoff_iso"] or "")
    pred_json = str(r["prediction_json"] or "")
    fid = int(r["fixture_id"])
    locked = snapshot_locked_pre_kickoff(captured, kickoff)
    settled = bool(r["result_recorded_at"])
    league = str(r["league_code"] or "")
    return {
        "snapshot_id": int(r["id"]),
        "fixture_id": fid,
        "official_lock": official_lock,
        "locked_pre_kickoff": locked,
        "captured_at_utc": captured,
        "kickoff_utc": kickoff,
        "league_code": league,
        "cohort": _league_cohort(league),
        "match": f"{r['home_name'] or pred.get('home') or '?'} v {r['away_name'] or pred.get('away') or '?'}",
        "data_quality_pct": round(float(r["data_quality_pct"] or 0), 1),
        "xg_source": str(r["xg_source"] or ""),
        "one_x2_mode": str(r["one_x2_mode"] or ""),
        "model_pick": pick if pick in ("home", "draw", "away") else None,
        "model_pct": _model_pct_for_pick(pred),
        "probabilities": pred.get("probabilities") or {},
        "has_value": bool(value_snap),
        "value_market": (value_snap or {}).get("market_label") if value_snap else None,
        "value_odds": (value_snap or {}).get("odds") if value_snap else None,
        "value_edge_pct": (value_snap or {}).get("edge_pct") if value_snap else None,
        "verification_hash": _prediction_hash(fid, captured, pred_json),
        "settled": settled,
        "result_status": r["result_status"],
        "result_outcome": r["result_outcome"],
        "score": _format_score(r["result_home"], r["result_away"]),
        "model_result": _model_result_label(pred, r),
        "value_result": _value_pick_result_label(r, pred) if value_snap else None,
        "clv_pp": _clv_pp_from_enrich(r["enrich_summary_json"]),
    }


def _model_result_label(pred: Dict[str, Any], r: sqlite3.Row) -> Optional[str]:
    from hibs_predictor.prediction_log import _best_pick_result_label

    if not r["result_outcome"]:
        return None
    return _best_pick_result_label(
        pred,
        outcome=r["result_outcome"],
        status=r["result_status"],
    )


def locked_predictions_ledger(*, limit: int = 500, days: int = 90) -> List[Dict[str, Any]]:
    """
    One official pre-kickoff lock per fixture (earliest valid snapshot).

    Additional snapshots for the same fixture are omitted from the public ledger.
    """
    if not os.path.isfile(_db_path()):
        return []
    init_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, int(days)))).isoformat()
    conn = sqlite3.connect(_db_path(), timeout=20)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT *
            FROM prediction_snapshots
            WHERE kickoff_iso >= ? OR kickoff_iso IS NULL OR kickoff_iso = ''
            ORDER BY kickoff_iso DESC, captured_at ASC, id ASC
            """,
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()

    buckets: Dict[int, List[sqlite3.Row]] = {}
    for r in rows:
        try:
            fid = int(r["fixture_id"])
        except (TypeError, ValueError):
            continue
        buckets.setdefault(fid, []).append(r)

    by_fixture: Dict[int, sqlite3.Row] = {}
    for fid, snaps in buckets.items():
        snaps.sort(key=lambda s: (str(s["captured_at"] or ""), int(s["id"])))
        locked = [
            s
            for s in snaps
            if snapshot_locked_pre_kickoff(str(s["captured_at"] or ""), str(s["kickoff_iso"] or ""))
        ]
        by_fixture[fid] = locked[0] if locked else snaps[0]

    out: List[Dict[str, Any]] = []
    for fid in sorted(by_fixture.keys(), key=lambda f: by_fixture[f]["kickoff_iso"] or "", reverse=True):
        r = by_fixture[fid]
        official = snapshot_locked_pre_kickoff(str(r["captured_at"] or ""), str(r["kickoff_iso"] or ""))
        out.append(_row_to_locked_entry(r, official_lock=official))
        if len(out) >= limit:
            break
    return out


def build_proof_metrics_dict() -> Dict[str, Any]:
    """
    North-star proof metrics (scale cohort only — friendlies reported separately).

    - Brier 1X2 < bookmaker baseline → calibration beats public consensus.
    - CLV beat-close > target on value-flagged picks → edge before the line moves.
    """
    try:
        baseline = float(os.getenv("HIBS_CALIB_BASELINE_BRIER", "0.66"))
    except ValueError:
        baseline = 0.66
    try:
        clv_target = float(os.getenv("HIBS_PROOF_CLV_BEAT_PCT", "60"))
    except ValueError:
        clv_target = 60.0
    try:
        min_n = max(5, int(os.getenv("HIBS_SCALE_READY_MIN_N", "25")))
    except ValueError:
        min_n = 25

    scale = scale_readiness_dict()
    cohorts = scale.get("cohorts") or {}
    sc = cohorts.get("scale") or {}
    fr = cohorts.get("friendlies") or {}

    brier = sc.get("brier_score_1x2")
    n_brier = int(sc.get("n_scored") or 0)
    clv_pct = sc.get("value_beat_close_pct")
    clv_n = int(sc.get("value_clv_n") or 0)

    brier_ok = brier is not None and n_brier >= min_n and float(brier) < baseline
    clv_ok = clv_pct is not None and clv_n >= 5 and float(clv_pct) >= clv_target

    return {
        "baseline_brier": baseline,
        "clv_beat_target_pct": clv_target,
        "min_scored_n": min_n,
        "proof_pass": bool(brier_ok and clv_ok),
        "metrics": [
            {
                "id": "brier_1x2",
                "label": "Brier score (1X2)",
                "target": f"< {baseline} (bookmaker baseline)",
                "proves": "Model calibrates 1X2 probabilities better than public consensus.",
                "cohort": "scale",
                "current": brier,
                "n": n_brier,
                "pass": brier_ok,
            },
            {
                "id": "clv_beat_rate",
                "label": "CLV beat-close rate",
                "target": f"> {clv_target}% of value-flagged picks",
                "proves": "Model spots inefficiencies before money moves the closing line.",
                "cohort": "scale",
                "current": clv_pct,
                "n": clv_n,
                "pass": clv_ok,
            },
        ],
        "friendlies_note": {
            "brier": fr.get("brier_score_1x2"),
            "n": fr.get("n_scored"),
            "note": "Friendlies audit-only — not used for scale proof (rotation / wide margins).",
        },
    }


def build_public_tracker_dict(*, history_days: int = 90, limit: int = 500) -> Dict[str, Any]:
    """Payload for /tracker and /api/tracker."""
    history_days = max(7, min(365, int(history_days)))
    limit = max(10, min(2000, int(limit)))
    cron = pred_log_sync_cron_status()
    ledger = locked_predictions_ledger(limit=limit, days=history_days)
    n_locked_ok = sum(1 for r in ledger if r.get("locked_pre_kickoff"))
    n_settled = sum(1 for r in ledger if r.get("settled"))
    n_value = sum(1 for r in ledger if r.get("has_value"))
    value_settled = [r for r in ledger if r.get("has_value") and r.get("value_result") in ("W", "L")]
    value_wins = sum(1 for r in value_settled if r.get("value_result") == "W")

    return {
        "ok": True,
        "public": True,
        "read_only": True,
        "enabled": prediction_log_enabled(),
        "history_days": history_days,
        "ledger_count": len(ledger),
        "locked_pre_kickoff_count": n_locked_ok,
        "settled_count": n_settled,
        "value_flag_count": n_value,
        "value_settled_count": len(value_settled),
        "value_win_count": value_wins,
        "value_hit_rate_pct": round(100.0 * value_wins / len(value_settled), 2) if value_settled else None,
        "methodology": {
            "lock_rule": (
                "First logged snapshot per fixture before kickoff (UTC) wins the public lock. "
                f"Grace window: {_lock_grace_seconds()}s after kickoff for clock skew."
            ),
            "settlement_rule": (
                "Full-time scores joined by daily pred-log-sync cron from API-Football; "
                "closing 1X2 stored when HIBS_CLV_LOG_ENABLED=1."
            ),
            "verification": (
                "Each row includes snapshot_id and SHA-256 verification_hash. "
                "Export CSV for third-party trackers (SBC, Betstamp, etc.)."
            ),
        },
        "pred_log_sync_cron": cron,
        "audit": report_summary_dict(),
        "scale_readiness": scale_readiness_dict(),
        "proof_metrics": build_proof_metrics_dict(),
        "ledger": ledger,
        "export_urls": {
            "csv": "/api/tracker/export.csv",
            "json": "/api/tracker",
        },
        "third_party_note": (
            "Gold standard: submit the CSV export to an independent verifier "
            "(e.g. Smart Betting Club verified tipster programme) or sync via their API if offered."
        ),
    }


def export_ledger_csv(*, days: int = 365, limit: int = 2000) -> str:
    """CSV suitable for external performance trackers."""
    rows = locked_predictions_ledger(limit=limit, days=days)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "snapshot_id",
            "fixture_id",
            "verification_hash",
            "captured_at_utc",
            "kickoff_utc",
            "locked_pre_kickoff",
            "league_code",
            "cohort",
            "match",
            "data_quality_pct",
            "model_pick",
            "model_pct",
            "prob_home",
            "prob_draw",
            "prob_away",
            "has_value",
            "value_market",
            "value_odds",
            "value_edge_pct",
            "settled",
            "score",
            "result_outcome",
            "model_result",
            "value_result",
            "clv_pp",
            "xg_source",
            "one_x2_mode",
        ]
    )
    for r in rows:
        probs = r.get("probabilities") or {}
        writer.writerow(
            [
                r.get("snapshot_id"),
                r.get("fixture_id"),
                r.get("verification_hash"),
                r.get("captured_at_utc"),
                r.get("kickoff_utc"),
                1 if r.get("locked_pre_kickoff") else 0,
                r.get("league_code"),
                r.get("cohort"),
                r.get("match"),
                r.get("data_quality_pct"),
                r.get("model_pick"),
                r.get("model_pct"),
                probs.get("home"),
                probs.get("draw"),
                probs.get("away"),
                1 if r.get("has_value") else 0,
                r.get("value_market"),
                r.get("value_odds"),
                r.get("value_edge_pct"),
                1 if r.get("settled") else 0,
                r.get("score"),
                r.get("result_outcome"),
                r.get("model_result"),
                r.get("value_result"),
                r.get("clv_pp"),
                r.get("xg_source"),
                r.get("one_x2_mode"),
            ]
        )
    return buf.getvalue()
