"""
Persistent prediction audit trail + post-match result join for calibration / ROI analysis.

Enable with HIBS_PREDICTION_LOG_ENABLED=1. All logging is best-effort and must never break predictions.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_DB = os.path.join(_BASE, "data", "prediction_audit.sqlite")


def _db_path() -> str:
    load_dotenv()
    return os.getenv("HIBS_PREDICTION_LOG_DB", _DEFAULT_DB)


def _enabled() -> bool:
    load_dotenv()
    return os.getenv("HIBS_PREDICTION_LOG_ENABLED", "0").lower() in ("1", "true", "yes")


def _min_interval_sec() -> int:
    try:
        return max(0, int(os.getenv("HIBS_PREDICTION_LOG_MIN_INTERVAL_SEC", "3600")))
    except ValueError:
        return 3600


def _retain_days() -> int:
    try:
        return max(7, int(os.getenv("HIBS_PREDICTION_LOG_RETAIN_DAYS", "365")))
    except ValueError:
        return 365


def _ensure_dir(path: str) -> None:
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d, mode=0o755, exist_ok=True)


def init_db() -> None:
    path = _db_path()
    _ensure_dir(path)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS prediction_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                captured_at TEXT NOT NULL,
                fixture_id INTEGER NOT NULL,
                league_code TEXT,
                kickoff_iso TEXT,
                home_name TEXT,
                away_name TEXT,
                one_x2_mode TEXT,
                xg_source TEXT,
                data_quality_pct REAL,
                prediction_json TEXT NOT NULL,
                enrich_summary_json TEXT,
                result_home INTEGER,
                result_away INTEGER,
                result_outcome TEXT,
                result_status TEXT,
                result_recorded_at TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_predlog_fixture ON prediction_snapshots(fixture_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_predlog_captured ON prediction_snapshots(captured_at)"
        )
        conn.commit()
    finally:
        conn.close()


def _fixture_id(fixture: Dict[str, Any]) -> Optional[int]:
    fx = fixture.get("fixture")
    if isinstance(fx, dict) and fx.get("id") is not None:
        try:
            return int(fx["id"])
        except (TypeError, ValueError):
            pass
    raw = fixture.get("id")
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    return None


def _kickoff_iso(fixture: Dict[str, Any]) -> str:
    raw = fixture.get("date") or ""
    if isinstance(raw, str):
        return raw
    return ""


def _enrich_summary(fixture: Dict[str, Any]) -> Dict[str, Any]:
    dq = fixture.get("data_quality") or {}
    hp = fixture.get("home_position") or {}
    ap = fixture.get("away_position") or {}
    return {
        "home_recent_n": int(fixture.get("home_recent_n") or 0),
        "away_recent_n": int(fixture.get("away_recent_n") or 0),
        "odds_available": bool(fixture.get("odds_available")),
        "has_home_stats": bool((fixture.get("home_stats") or {}).get("played")),
        "has_away_stats": bool((fixture.get("away_stats") or {}).get("played")),
        "home_table": bool(hp.get("position")),
        "away_table": bool(ap.get("position")),
        "data_quality_pct": float(dq.get("score_pct") or 0),
        "full_scope": bool(dq.get("full_scope")),
    }


def maybe_log_prediction_snapshot(fixture: Dict[str, Any], prediction: Dict[str, Any]) -> None:
    """Append a snapshot row if logging is enabled and interval / dedupe rules pass."""
    if not _enabled():
        return
    fid = _fixture_id(fixture)
    if not fid:
        return
    try:
        init_db()
        path = _db_path()
        now_iso = datetime.now(timezone.utc).isoformat()
        interval = _min_interval_sec()
        conn = sqlite3.connect(path, timeout=15)
        try:
            if interval > 0:
                cur = conn.execute(
                    "SELECT captured_at FROM prediction_snapshots WHERE fixture_id = ? ORDER BY id DESC LIMIT 1",
                    (fid,),
                )
                r = cur.fetchone()
                if r and r[0]:
                    try:
                        raw_ts = str(r[0]).replace("Z", "+00:00")
                        last = datetime.fromisoformat(raw_ts)
                        if last.tzinfo is None:
                            last = last.replace(tzinfo=timezone.utc)
                        if (datetime.now(timezone.utc) - last).total_seconds() < float(interval):
                            return
                    except Exception:
                        pass
            league = str(fixture.get("league") or "")
            home_nm = str(prediction.get("home") or "?")
            away_nm = str(prediction.get("away") or "?")
            mode = str(prediction.get("one_x2_mode") or os.getenv("HIBS_1X2_MODE", "ensemble"))
            xg_src = str(fixture.get("xg_source") or prediction.get("xg_source") or "")
            dq = fixture.get("data_quality") or {}
            dq_pct = float(dq.get("score_pct") or 0)
            pred_json = json.dumps(prediction, default=str)
            sum_json = json.dumps(_enrich_summary(fixture), default=str)
            conn.execute(
                """
                INSERT INTO prediction_snapshots (
                    captured_at, fixture_id, league_code, kickoff_iso, home_name, away_name,
                    one_x2_mode, xg_source, data_quality_pct, prediction_json, enrich_summary_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    now_iso,
                    fid,
                    league,
                    _kickoff_iso(fixture),
                    home_nm,
                    away_nm,
                    mode,
                    xg_src,
                    dq_pct,
                    pred_json,
                    sum_json,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        # Never break the betting pipeline
        return


def _outcome_from_goals(h: int, a: int) -> str:
    if h > a:
        return "home"
    if h < a:
        return "away"
    return "draw"


def _parse_kickoff_iso(iso: str) -> Optional[datetime]:
    if not iso or len(iso) < 10:
        return None
    try:
        raw = str(iso).replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def sync_finished_results(
    fetch_fixture_fn: Any,
    *,
    max_fixtures: int = 400,
    min_after_kickoff_hours: float = 2.5,
) -> int:
    """
    For snapshots missing results, fetch fixture status via API and fill goals when FT.

    ``fetch_fixture_fn``: ``ApiSportsFootballClient.fetch_fixture`` (fixture_id -> raw response row).
    Returns number of snapshot rows updated (can be > distinct fixtures if multiple pending rows).
    """
    path = _db_path()
    if not _enabled() and not os.path.isfile(path):
        return 0
    init_db()
    conn = sqlite3.connect(path, timeout=20)
    conn.row_factory = sqlite3.Row
    updated = 0
    now = datetime.now(timezone.utc)
    min_after = timedelta(hours=float(min_after_kickoff_hours))
    try:
        rows = conn.execute(
            """
            SELECT fixture_id, MIN(kickoff_iso) AS kickoff_iso
            FROM prediction_snapshots
            WHERE result_recorded_at IS NULL
            GROUP BY fixture_id
            ORDER BY MIN(kickoff_iso)
            LIMIT ?
            """,
            (int(max_fixtures),),
        ).fetchall()
        for r in rows:
            fid = r["fixture_id"]
            kick_raw = r["kickoff_iso"] or ""
            ko = _parse_kickoff_iso(str(kick_raw))
            if ko is not None and now < ko + min_after:
                continue
            try:
                fid_int = int(fid)
            except (TypeError, ValueError):
                continue
            try:
                raw = fetch_fixture_fn(fid_int)
            except Exception:
                continue
            if not isinstance(raw, dict):
                continue
            status = ((raw.get("fixture") or {}).get("status") or {}).get("short") or ""
            goals = raw.get("goals") or {}
            gh, ga = goals.get("home"), goals.get("away")
            if status == "FT" and gh is not None and ga is not None:
                try:
                    hi, ai = int(gh), int(ga)
                except (TypeError, ValueError):
                    continue
                oc = _outcome_from_goals(hi, ai)
                rec_at = datetime.now(timezone.utc).isoformat()
                cur = conn.execute(
                    """
                    UPDATE prediction_snapshots
                    SET result_home=?, result_away=?, result_outcome=?, result_status=?, result_recorded_at=?
                    WHERE fixture_id=? AND result_recorded_at IS NULL
                    """,
                    (hi, ai, oc, status, rec_at, fid_int),
                )
                updated += cur.rowcount if cur.rowcount else 0
                conn.commit()
    finally:
        conn.close()
    return updated


def prune_old_rows(days: Optional[int] = None) -> int:
    """Delete snapshots older than retain policy. Returns deleted row count."""
    d = days if days is not None else _retain_days()
    init_db()
    path = _db_path()
    conn = sqlite3.connect(path, timeout=20)
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=int(d))).isoformat()
        cur = conn.execute("DELETE FROM prediction_snapshots WHERE captured_at < ?", (cutoff,))
        conn.commit()
        return int(cur.rowcount or 0)
    finally:
        conn.close()


def _safe_prob(p: Any) -> float:
    try:
        x = float(p)
    except (TypeError, ValueError):
        return 1.0 / 3.0
    return max(1e-6, min(1.0 - 1e-6, x))


def _rows_with_results(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return list(
        conn.execute(
            """
            SELECT id, prediction_json, result_outcome, data_quality_pct
            FROM prediction_snapshots
            WHERE result_outcome IS NOT NULL AND result_outcome != ''
            """
        ).fetchall()
    )


def report_summary_dict() -> Dict[str, Any]:
    """Brier score (1X2), log loss, counts, optional value-hit — for API + CLI."""
    if not os.path.isfile(_db_path()):
        return {"ok": False, "error": "no_database", "path": _db_path()}
    init_db()
    conn = sqlite3.connect(_db_path(), timeout=20)
    try:
        rows = _rows_with_results(conn)
    finally:
        conn.close()
    n = len(rows)
    if n == 0:
        return {
            "ok": True,
            "n_scored_rows": 0,
            "n_used_metrics": 0,
            "message": "No rows with recorded results yet. Run pred-log-sync.",
            "brier_by_data_quality_bucket": brier_by_data_quality_bucket(),
        }

    brier_sum = 0.0
    logloss_sum = 0.0
    value_attempts = 0
    value_wins = 0
    n_used = 0

    for r in rows:
        try:
            pred = json.loads(r["prediction_json"])
        except Exception:
            continue
        probs = pred.get("probabilities") or {}
        ph = _safe_prob(probs.get("home"))
        pd = _safe_prob(probs.get("draw"))
        pa = _safe_prob(probs.get("away"))
        out = (r["result_outcome"] or "").lower()
        if out not in ("home", "draw", "away"):
            continue
        yh, yd, ya = (1.0, 0.0, 0.0) if out == "home" else ((0.0, 1.0, 0.0) if out == "draw" else (0.0, 0.0, 1.0))
        brier_sum += (ph - yh) ** 2 + (pd - yd) ** 2 + (pa - ya) ** 2
        p_correct = ph if out == "home" else (pd if out == "draw" else pa)
        logloss_sum += -math.log(p_correct)
        n_used += 1

        vb = pred.get("best_bet")
        if pred.get("has_any_value") and vb in ("home", "draw", "away"):
            value_attempts += 1
            if str(vb).lower() == out:
                value_wins += 1

    if n_used == 0:
        return {
            "ok": True,
            "n_scored_rows": n,
            "n_used_metrics": 0,
            "message": "No rows with parseable 1X2 results yet. Run pred-log-sync after matches finish.",
            "brier_by_data_quality_bucket": brier_by_data_quality_bucket(),
        }

    n_eff = max(1, n_used)
    out: Dict[str, Any] = {
        "ok": True,
        "n_scored_rows": n,
        "n_used_metrics": n_used,
        "brier_score_1x2": round(brier_sum / n_eff, 5),
        "log_loss_1x2": round(logloss_sum / n_eff, 5),
        "value_flags_count": value_attempts,
        "value_best_outcome_hits": value_wins,
        "brier_by_data_quality_bucket": brier_by_data_quality_bucket(),
    }
    if value_attempts:
        out["value_hit_rate"] = round(100.0 * value_wins / value_attempts, 2)
    return out


def export_scored_csv(target_path: str) -> int:
    """Write one row per scored snapshot. Returns row count written."""
    init_db()
    conn = sqlite3.connect(_db_path(), timeout=20)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT captured_at, fixture_id, league_code, kickoff_iso, home_name, away_name,
                   data_quality_pct, one_x2_mode, xg_source, prediction_json,
                   result_home, result_away, result_outcome, result_recorded_at
            FROM prediction_snapshots
            WHERE result_outcome IS NOT NULL AND result_outcome != ''
            ORDER BY kickoff_iso
            """
        ).fetchall()
    finally:
        conn.close()
    _ensure_dir(target_path)
    import csv

    n = 0
    with open(target_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "captured_at",
                "fixture_id",
                "league",
                "kickoff",
                "home",
                "away",
                "dq_pct",
                "mode",
                "xg_source",
                "p_home",
                "p_draw",
                "p_away",
                "pred_outcome",
                "res_home",
                "res_away",
                "res_outcome",
                "result_at",
            ]
        )
        for r in rows:
            try:
                pred = json.loads(r["prediction_json"])
            except Exception:
                pred = {}
            pr = pred.get("probabilities") or {}
            w.writerow(
                [
                    r["captured_at"],
                    r["fixture_id"],
                    r["league_code"],
                    r["kickoff_iso"],
                    r["home_name"],
                    r["away_name"],
                    r["data_quality_pct"],
                    r["one_x2_mode"],
                    r["xg_source"],
                    pr.get("home"),
                    pr.get("draw"),
                    pr.get("away"),
                    pred.get("predicted_outcome"),
                    r["result_home"],
                    r["result_away"],
                    r["result_outcome"],
                    r["result_recorded_at"],
                ]
            )
            n += 1
    return n


def brier_by_data_quality_bucket() -> List[Dict[str, Any]]:
    """Mean Brier for buckets of data_quality_pct (quartile-style bins)."""
    init_db()
    conn = sqlite3.connect(_db_path(), timeout=20)
    conn.row_factory = sqlite3.Row
    try:
        rows = _rows_with_results(conn)
    finally:
        conn.close()

    bins = [
        ("0-60", 0, 60),
        ("60-75", 60, 75),
        ("75-85", 75, 85),
        ("85-100", 85, 100.1),
    ]
    out: List[Dict[str, Any]] = []
    for label, lo, hi in bins:
        sub = [r for r in rows if lo <= float(r["data_quality_pct"] or 0) < hi]
        if not sub:
            out.append({"bucket": label, "n": 0, "brier": None})
            continue
        s = 0.0
        n_bin = 0
        for r in sub:
            try:
                pred = json.loads(r["prediction_json"])
            except Exception:
                continue
            probs = pred.get("probabilities") or {}
            ph, pd, pa = _safe_prob(probs.get("home")), _safe_prob(probs.get("draw")), _safe_prob(probs.get("away"))
            oc = (r["result_outcome"] or "").lower()
            if oc not in ("home", "draw", "away"):
                continue
            yh, yd, ya = (1, 0, 0) if oc == "home" else ((0, 1, 0) if oc == "draw" else (0, 0, 1))
            s += (ph - yh) ** 2 + (pd - yd) ** 2 + (pa - ya) ** 2
            n_bin += 1
        if n_bin == 0:
            out.append({"bucket": label, "n": 0, "brier": None})
        else:
            out.append({"bucket": label, "n": n_bin, "brier": round(s / n_bin, 5)})
    return out
