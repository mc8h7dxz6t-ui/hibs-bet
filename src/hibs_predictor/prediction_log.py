"""
Persistent prediction audit trail + post-match result join for calibration / ROI analysis.

Enable with HIBS_PREDICTION_LOG_ENABLED=1. Optional CLV: HIBS_CLV_LOG_ENABLED=1 stores opening
1X2 + best-bet odds at capture; pred-log-sync joins closing 1X2 from API-Football fixture odds
when available and computes clv_pp (stake implied vs close, percentage points).
All logging is best-effort and must never break predictions.
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


def prediction_log_enabled() -> bool:
    """Public check for audit DB features (calibration shrink, etc.)."""
    return _enabled()


def _clv_enabled() -> bool:
    load_dotenv()
    return os.getenv("HIBS_CLV_LOG_ENABLED", "0").lower() in ("1", "true", "yes")


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
                result_recorded_at TEXT,
                result_xg_home REAL,
                result_xg_away REAL
            )
            """
        )
        _migrate_prediction_log_schema(conn)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_predlog_fixture ON prediction_snapshots(fixture_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_predlog_captured ON prediction_snapshots(captured_at)"
        )
        conn.commit()
    finally:
        conn.close()


def _migrate_prediction_log_schema(conn: sqlite3.Connection) -> None:
    """Append-only schema upgrades for existing audit DBs."""
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(prediction_snapshots)").fetchall()}
    if "result_xg_home" not in cols:
        conn.execute("ALTER TABLE prediction_snapshots ADD COLUMN result_xg_home REAL")
    if "result_xg_away" not in cols:
        conn.execute("ALTER TABLE prediction_snapshots ADD COLUMN result_xg_away REAL")
    conn.commit()


def parse_result_xg_from_statistics(
    stats_response: Any,
    *,
    home_team_id: Optional[int] = None,
    away_team_id: Optional[int] = None,
    home_name: Optional[str] = None,
    away_name: Optional[str] = None,
) -> Tuple[Optional[float], Optional[float]]:
    """Extract home/away xG from API-Football fixtures/statistics response."""
    if not isinstance(stats_response, list) or len(stats_response) < 2:
        return None, None
    try:
        from hibs_predictor.live_scores import parse_live_statistics

        _, xg_h, xg_a = parse_live_statistics(
            stats_response,
            home_name=home_name,
            away_name=away_name,
        )
        if xg_h is not None and xg_a is not None:
            return float(xg_h), float(xg_a)
    except Exception:
        pass
    if home_team_id and away_team_id:
        try:
            from hibs_predictor.betting_engine import TeamStrengthCalculator

            pseudo = {"statistics": stats_response}
            xh = TeamStrengthCalculator._team_xg_from_fixture_statistics(pseudo, int(home_team_id))
            xa = TeamStrengthCalculator._team_xg_from_fixture_statistics(pseudo, int(away_team_id))
            if xh is not None and xa is not None:
                return float(xh), float(xa)
        except Exception:
            pass
    return None, None


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


def _implied_from_decimal(odds: Any) -> Optional[float]:
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if o <= 1.0:
        return None
    return 1.0 / o


def compute_clv_pp(implied_open: Optional[float], implied_close: Optional[float]) -> Optional[float]:
    """CLV in percentage points: positive when closing implied > stake (line moved toward your pick)."""
    if implied_open is None or implied_close is None:
        return None
    return round((implied_close - implied_open) * 100.0, 2)


def parse_closing_1x2_from_odds_response(odds_raw: Any) -> Dict[str, Optional[float]]:
    """Best Match Winner prices across bookmakers in API-Football odds response."""
    best: Dict[str, Optional[float]] = {"home": None, "draw": None, "away": None}
    if not isinstance(odds_raw, list):
        return best
    for entry in odds_raw:
        if not isinstance(entry, dict):
            continue
        for bm in entry.get("bookmakers", []) or []:
            for bet in bm.get("bets", []) or []:
                if bet.get("name") != "Match Winner":
                    continue
                for v in bet.get("values", []) or []:
                    val = (v.get("value") or "").lower()
                    try:
                        price = float(v.get("odd", 0) or 0)
                    except (TypeError, ValueError):
                        continue
                    if price <= 1.0:
                        continue
                    if val in best:
                        cur = best[val]
                        best[val] = price if cur is None else max(cur, price)
    return best


def _clv_opening_capture(fixture: Dict[str, Any], prediction: Dict[str, Any]) -> Dict[str, Any]:
    """Opening-line capture for CLV analysis."""
    bo = prediction.get("bookmaker_odds") or {}
    opening: Dict[str, Optional[float]] = {}
    for side in ("home", "draw", "away"):
        raw = bo.get(side)
        try:
            opening[side] = float(raw) if raw is not None and float(raw) > 1.0 else None
        except (TypeError, ValueError):
            opening[side] = None
    best = prediction.get("best_bet")
    best_row = (prediction.get("value_bets") or {}).get(best) if best else None
    best_odds = None
    if isinstance(best_row, dict):
        try:
            o = best_row.get("odds")
            best_odds = float(o) if o is not None and float(o) > 1.0 else None
        except (TypeError, ValueError):
            best_odds = None
    return {
        "opening_odds_1x2": opening,
        "best_bet_outcome": best,
        "best_bet_odds": best_odds,
        "best_bet_edge_pct": (best_row or {}).get("edge_pct") if isinstance(best_row, dict) else None,
        "odds_cross_max_implied_diff_pct": float(fixture.get("odds_cross_max_implied_diff_pct") or 0.0),
        "closing_odds_1x2": None,
        "clv_pp": None,
    }


def _enrich_summary(fixture: Dict[str, Any], prediction: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    dq = fixture.get("data_quality") or {}
    hp = fixture.get("home_position") or {}
    ap = fixture.get("away_position") or {}
    out: Dict[str, Any] = {
        "home_recent_n": int(fixture.get("home_recent_n") or 0),
        "away_recent_n": int(fixture.get("away_recent_n") or 0),
        "odds_available": bool(fixture.get("odds_available")),
        "has_home_stats": bool((fixture.get("home_stats") or {}).get("played")),
        "has_away_stats": bool((fixture.get("away_stats") or {}).get("played")),
        "home_table": bool(hp.get("position")),
        "away_table": bool(ap.get("position")),
        "data_quality_pct": float(dq.get("score_pct") or 0),
        "full_scope": bool(dq.get("full_scope")),
        "injuries_n": len(fixture.get("fixture_injuries") or []),
        "lineup_confirmed": bool(fixture.get("lineup_confirmed")),
    }
    meta = fixture.get("team_news_meta") or {}
    if meta.get("home_absences") or meta.get("away_absences"):
        out["team_news_absences"] = {
            "home": int(meta.get("home_absences") or 0),
            "away": int(meta.get("away_absences") or 0),
        }
    lmeta = fixture.get("lineup_meta") or {}
    if lmeta.get("home_scorers_out_of_xi") or lmeta.get("away_scorers_out_of_xi"):
        out["lineup_scorers_out"] = {
            "home": len(lmeta.get("home_scorers_out_of_xi") or []),
            "away": len(lmeta.get("away_scorers_out_of_xi") or []),
        }
    if lmeta.get("home_xi_n") or lmeta.get("away_xi_n"):
        out["lineup_xi_n"] = {
            "home": int(lmeta.get("home_xi_n") or 0),
            "away": int(lmeta.get("away_xi_n") or 0),
        }
    if fixture.get("attack_availability_home") is not None:
        out["attack_availability_home"] = fixture.get("attack_availability_home")
    if fixture.get("attack_availability_away") is not None:
        out["attack_availability_away"] = fixture.get("attack_availability_away")
    if _clv_enabled() and prediction:
        out["clv"] = _clv_opening_capture(fixture, prediction)
    return out


def maybe_log_prediction_snapshot(fixture: Dict[str, Any], prediction: Dict[str, Any]) -> None:
    """Append a snapshot row if logging is enabled and interval / dedupe rules pass."""
    if not _enabled():
        return
    if prediction.get("prediction_unavailable"):
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
            sum_json = json.dumps(_enrich_summary(fixture, prediction), default=str)
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


def _apply_clv_to_enrich_summary(
    enrich: Dict[str, Any],
    closing: Dict[str, Optional[float]],
) -> Dict[str, Any]:
    clv = enrich.get("clv")
    if not isinstance(clv, dict):
        return enrich
    opening = clv.get("opening_odds_1x2") or {}
    clv["closing_odds_1x2"] = closing
    outcome = clv.get("best_bet_outcome")
    open_odds = clv.get("best_bet_odds")
    close_side = closing.get(str(outcome)) if outcome else None
    impl_open = _implied_from_decimal(open_odds)
    impl_close = _implied_from_decimal(close_side)
    clv["clv_pp"] = compute_clv_pp(impl_open, impl_close)
    enrich["clv"] = clv
    return enrich


def sync_finished_results(
    fetch_fixture_fn: Any,
    *,
    fetch_odds_fn: Any = None,
    fetch_statistics_fn: Any = None,
    max_fixtures: int = 400,
    min_after_kickoff_hours: float = 2.5,
) -> int:
    """
    For snapshots missing results, fetch fixture status via API and fill goals when FT.

    ``fetch_fixture_fn``: ``ApiSportsFootballClient.fetch_fixture`` (fixture_id -> raw response row).
    ``fetch_odds_fn``: optional ``fetch_odds`` for closing 1X2 when ``HIBS_CLV_LOG_ENABLED=1``.
    ``fetch_statistics_fn``: optional ``fetch_fixture_statistics`` for post-match xG join.
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
                res_xg_h: Optional[float] = None
                res_xg_a: Optional[float] = None
                if fetch_statistics_fn is not None:
                    try:
                        stats_raw = fetch_statistics_fn(fid_int)
                        teams = raw.get("teams") or {}
                        hid = ((teams.get("home") or {}).get("id"))
                        aid = ((teams.get("away") or {}).get("id"))
                        hnm = ((teams.get("home") or {}).get("name"))
                        anm = ((teams.get("away") or {}).get("name"))
                        res_xg_h, res_xg_a = parse_result_xg_from_statistics(
                            stats_raw,
                            home_team_id=int(hid) if hid is not None else None,
                            away_team_id=int(aid) if aid is not None else None,
                            home_name=str(hnm) if hnm else None,
                            away_name=str(anm) if anm else None,
                        )
                    except Exception:
                        res_xg_h = res_xg_a = None
                cur = conn.execute(
                    """
                    UPDATE prediction_snapshots
                    SET result_home=?, result_away=?, result_outcome=?, result_status=?, result_recorded_at=?,
                        result_xg_home=?, result_xg_away=?
                    WHERE fixture_id=? AND result_recorded_at IS NULL
                    """,
                    (hi, ai, oc, status, rec_at, res_xg_h, res_xg_a, fid_int),
                )
                updated += cur.rowcount if cur.rowcount else 0
                conn.commit()
                if _clv_enabled() and fetch_odds_fn is not None:
                    try:
                        odds_raw = fetch_odds_fn(fid_int)
                        closing = parse_closing_1x2_from_odds_response(odds_raw)
                    except Exception:
                        closing = {"home": None, "draw": None, "away": None}
                    snap_rows = conn.execute(
                        """
                        SELECT id, enrich_summary_json FROM prediction_snapshots
                        WHERE fixture_id=? AND enrich_summary_json IS NOT NULL
                        """,
                        (fid_int,),
                    ).fetchall()
                    for sr in snap_rows:
                        try:
                            enrich = json.loads(sr["enrich_summary_json"])
                        except Exception:
                            continue
                        if not isinstance(enrich, dict) or "clv" not in enrich:
                            continue
                        enrich = _apply_clv_to_enrich_summary(enrich, closing)
                        conn.execute(
                            "UPDATE prediction_snapshots SET enrich_summary_json=? WHERE id=?",
                            (json.dumps(enrich, default=str), sr["id"]),
                        )
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


def _monitor_days() -> int:
    try:
        return max(1, int(os.getenv("HIBS_MONITOR_DAYS", "28")))
    except ValueError:
        return 28


def _monitor_cutoff_iso(*, days: Optional[int] = None) -> str:
    d = days if days is not None else _monitor_days()
    return (datetime.now(timezone.utc) - timedelta(days=int(d))).isoformat()


def pred_log_sync_cron_status() -> Dict[str, Any]:
    """Whether pred-log-sync appears scheduled (crontab) and log freshness."""
    log_path = (os.getenv("HIBS_PRED_LOG_SYNC_LOG") or "/var/log/hibs-bet/pred-log-sync.log").strip()
    marker = "pred-log-sync"
    scheduled = False
    cron_user = ""
    try:
        import subprocess

        for user in ("www-data", "root"):
            proc = subprocess.run(
                ["crontab", "-u", user, "-l"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if proc.returncode == 0 and marker in (proc.stdout or ""):
                scheduled = True
                cron_user = user
                break
    except Exception:
        pass

    log_exists = os.path.isfile(log_path)
    log_age_hours: Optional[float] = None
    if log_exists:
        log_age_hours = round((datetime.now(timezone.utc).timestamp() - os.path.getmtime(log_path)) / 3600.0, 1)

    needs_reminder = prediction_log_enabled() and not scheduled
    message = ""
    if needs_reminder:
        message = (
            "Install daily pred-log-sync: sudo bash /opt/hibs-bet/deploy/cron-hibs-calibration.sh --install"
        )
    elif scheduled and log_exists and log_age_hours is not None and log_age_hours > 48:
        message = f"Cron present but log stale ({log_age_hours}h) — check {log_path}"

    return {
        "scheduled": scheduled,
        "cron_user": cron_user or None,
        "log_path": log_path,
        "log_exists": log_exists,
        "log_age_hours": log_age_hours,
        "needs_reminder": needs_reminder,
        "message": message,
    }


def _rows_in_monitor_window(
    conn: sqlite3.Connection,
    *,
    days: Optional[int] = None,
    scored_only: bool = False,
) -> List[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cutoff = _monitor_cutoff_iso(days=days)
    sql = """
        SELECT id, league_code, prediction_json, result_outcome, data_quality_pct,
               enrich_summary_json, captured_at
        FROM prediction_snapshots
        WHERE captured_at >= ?
    """
    if scored_only:
        sql += " AND result_outcome IS NOT NULL AND result_outcome != ''"
    sql += " ORDER BY captured_at"
    return list(conn.execute(sql, (cutoff,)).fetchall())


def monitor_summary_dict(*, days: Optional[int] = None) -> Dict[str, Any]:
    """Rolling-window prediction vs outcome metrics (default HIBS_MONITOR_DAYS=28)."""
    window_days = days if days is not None else _monitor_days()
    cutoff = _monitor_cutoff_iso(days=window_days)
    enabled = prediction_log_enabled()
    base: Dict[str, Any] = {
        "ok": True,
        "enabled": enabled,
        "window_days": window_days,
        "window_start_utc": cutoff[:10],
        "db_path": _db_path(),
        "prediction_log_enabled": enabled,
        "clv_log_enabled": _clv_enabled(),
        "pred_log_sync_cron": pred_log_sync_cron_status(),
    }
    if not os.path.isfile(_db_path()):
        base.update(
            {
                "ok": False,
                "error": "no_database",
                "n_logged": 0,
                "n_scored": 0,
                "message": "No audit database yet — enable HIBS_PREDICTION_LOG_ENABLED=1 and use the dashboard.",
            }
        )
        return base

    init_db()
    conn = sqlite3.connect(_db_path(), timeout=20)
    try:
        rows_all = _rows_in_monitor_window(conn, days=window_days, scored_only=False)
        rows_scored = _rows_in_monitor_window(conn, days=window_days, scored_only=True)
    finally:
        conn.close()

    n_logged = len(rows_all)
    n_scored = len(rows_scored)
    base["n_logged"] = n_logged
    base["n_scored"] = n_scored

    if n_scored == 0:
        base["message"] = (
            "No scored rows in window yet — run pred-log-sync after matches finish."
            if n_logged
            else "No snapshots in window — predictions accumulate when the dashboard runs."
        )
        base["by_league"] = []
        return base

    brier_sum = 0.0
    logloss_sum = 0.0
    pick_correct = 0
    pick_attempts = 0
    n_metrics = 0
    clv_n = 0
    clv_beat = 0
    clv_pp_sum = 0.0
    by_league: Dict[str, Dict[str, Any]] = {}

    for r in rows_scored:
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
        brier = (ph - yh) ** 2 + (pd - yd) ** 2 + (pa - ya) ** 2
        p_correct = ph if out == "home" else (pd if out == "draw" else pa)
        brier_sum += brier
        logloss_sum += -math.log(p_correct)
        n_metrics += 1

        pick = (pred.get("predicted_outcome") or "").lower()
        if pick in ("home", "draw", "away"):
            pick_attempts += 1
            if pick == out:
                pick_correct += 1

        lg = str(r["league_code"] or "unknown")
        bucket = by_league.setdefault(
            lg,
            {"league": lg, "n_scored": 0, "brier_sum": 0.0, "pick_correct": 0, "pick_attempts": 0, "clv_n": 0, "clv_beat": 0},
        )
        bucket["n_scored"] += 1
        bucket["brier_sum"] += brier
        if pick in ("home", "draw", "away"):
            bucket["pick_attempts"] += 1
            if pick == out:
                bucket["pick_correct"] += 1

        try:
            enrich = json.loads(r["enrich_summary_json"] or "")
        except Exception:
            enrich = {}
        clv = enrich.get("clv") if isinstance(enrich, dict) else None
        if isinstance(clv, dict) and clv.get("clv_pp") is not None:
            try:
                pp_f = float(clv["clv_pp"])
            except (TypeError, ValueError):
                pp_f = None
            if pp_f is not None:
                clv_n += 1
                clv_pp_sum += pp_f
                bucket["clv_n"] += 1
                if pp_f > 0:
                    clv_beat += 1
                    bucket["clv_beat"] += 1

    if n_metrics == 0:
        base["message"] = "Scored rows in window lack parseable 1X2 results."
        base["by_league"] = []
        return base

    n_eff = max(1, n_metrics)
    base.update(
        {
            "n_used_metrics": n_metrics,
            "brier_score_1x2": round(brier_sum / n_eff, 5),
            "log_loss_1x2": round(logloss_sum / n_eff, 5),
            "best_pick_accuracy_pct": round(100.0 * pick_correct / pick_attempts, 2) if pick_attempts else None,
            "best_pick_n": pick_attempts,
            "best_pick_correct": pick_correct,
        }
    )
    if clv_n:
        base["clv_n"] = clv_n
        base["beat_close_pct"] = round(100.0 * clv_beat / clv_n, 2)
        base["avg_clv_pp"] = round(clv_pp_sum / clv_n, 2)

    league_rows: List[Dict[str, Any]] = []
    for lg, b in sorted(by_league.items(), key=lambda x: -x[1]["n_scored"]):
        ns = int(b["n_scored"])
        pa = int(b["pick_attempts"])
        cn = int(b["clv_n"])
        row: Dict[str, Any] = {
            "league": lg,
            "n_scored": ns,
            "brier": round(b["brier_sum"] / ns, 5) if ns else None,
            "best_pick_accuracy_pct": round(100.0 * b["pick_correct"] / pa, 2) if pa else None,
        }
        if cn:
            row["clv_n"] = cn
            row["beat_close_pct"] = round(100.0 * b["clv_beat"] / cn, 2)
        league_rows.append(row)
    base["by_league"] = league_rows
    return base


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
            "clv_by_league": clv_beat_close_by_league(),
            "brier_by_league": brier_by_league(),
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
            "clv_by_league": clv_beat_close_by_league(),
            "brier_by_league": brier_by_league(),
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
    out["clv_by_league"] = clv_beat_close_by_league()
    out["brier_by_league"] = brier_by_league()
    return out


def brier_by_league() -> List[Dict[str, Any]]:
    """Mean 1X2 Brier per league_code for scored snapshots (calibration shrink input)."""
    if not os.path.isfile(_db_path()):
        return []
    init_db()
    conn = sqlite3.connect(_db_path(), timeout=20)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT league_code, prediction_json, result_outcome
            FROM prediction_snapshots
            WHERE result_outcome IS NOT NULL AND result_outcome != ''
            """
        ).fetchall()
    finally:
        conn.close()

    by_league: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        try:
            pred = json.loads(r["prediction_json"])
        except Exception:
            continue
        probs = pred.get("probabilities") or {}
        ph = _safe_prob(probs.get("home"))
        pd = _safe_prob(probs.get("draw"))
        pa = _safe_prob(probs.get("away"))
        oc = (r["result_outcome"] or "").lower()
        if oc not in ("home", "draw", "away"):
            continue
        yh, yd, ya = (1.0, 0.0, 0.0) if oc == "home" else ((0.0, 1.0, 0.0) if oc == "draw" else (0.0, 0.0, 1.0))
        brier = (ph - yh) ** 2 + (pd - yd) ** 2 + (pa - ya) ** 2
        lg = str(r["league_code"] or "unknown")
        bucket = by_league.setdefault(lg, {"n": 0, "brier_sum": 0.0})
        bucket["n"] += 1
        bucket["brier_sum"] += brier

    out: List[Dict[str, Any]] = []
    for lg, b in sorted(by_league.items(), key=lambda x: -x[1]["n"]):
        n = int(b["n"])
        out.append(
            {
                "league": lg,
                "n": n,
                "brier": round(b["brier_sum"] / n, 5) if n else None,
            }
        )
    return out


def clv_beat_close_by_league() -> Dict[str, Any]:
    """CLV beat-close rate and mean clv_pp grouped by league (requires HIBS_CLV_LOG_ENABLED snapshots)."""
    if not os.path.isfile(_db_path()):
        return {"enabled": False, "leagues": []}
    init_db()
    conn = sqlite3.connect(_db_path(), timeout=20)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT league_code, enrich_summary_json
            FROM prediction_snapshots
            WHERE enrich_summary_json IS NOT NULL AND enrich_summary_json != ''
            """
        ).fetchall()
    finally:
        conn.close()

    by_league: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        try:
            enrich = json.loads(r["enrich_summary_json"])
        except Exception:
            continue
        clv = enrich.get("clv") if isinstance(enrich, dict) else None
        if not isinstance(clv, dict):
            continue
        pp = clv.get("clv_pp")
        if pp is None:
            continue
        try:
            pp_f = float(pp)
        except (TypeError, ValueError):
            continue
        lg = str(r["league_code"] or "unknown")
        bucket = by_league.setdefault(lg, {"n": 0, "beat_close": 0, "clv_pp_sum": 0.0})
        bucket["n"] += 1
        bucket["clv_pp_sum"] += pp_f
        if pp_f > 0:
            bucket["beat_close"] += 1

    leagues_out: List[Dict[str, Any]] = []
    total_n = 0
    total_beat = 0
    for lg, b in sorted(by_league.items(), key=lambda x: -x[1]["n"]):
        n = int(b["n"])
        beat = int(b["beat_close"])
        total_n += n
        total_beat += beat
        leagues_out.append(
            {
                "league": lg,
                "n_clv": n,
                "beat_close_pct": round(100.0 * beat / n, 2) if n else None,
                "avg_clv_pp": round(b["clv_pp_sum"] / n, 2) if n else None,
            }
        )
    return {
        "enabled": _clv_enabled(),
        "n_clv_rows": total_n,
        "beat_close_pct": round(100.0 * total_beat / total_n, 2) if total_n else None,
        "leagues": leagues_out,
    }


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
                   result_home, result_away, result_outcome, result_recorded_at,
                   result_xg_home, result_xg_away
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
                "res_xg_home",
                "res_xg_away",
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
                    r["result_xg_home"] if "result_xg_home" in r.keys() else None,
                    r["result_xg_away"] if "result_xg_away" in r.keys() else None,
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
