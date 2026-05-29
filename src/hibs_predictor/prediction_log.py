"""
Persistent prediction audit trail + post-match result join for calibration / ROI analysis.

Enabled by default (set HIBS_PREDICTION_LOG_ENABLED=0 to disable). After each fixture bundle
build, log_predictions_from_fixtures runs when HIBS_PREDICTION_LOG_ALWAYS=1 (default on).
CLV: HIBS_CLV_LOG_ENABLED=1 (default when log on) stores opening
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
    raw = (os.getenv("HIBS_PREDICTION_LOG_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _always_log() -> bool:
    """When on, bundle finalization logs every fixture prediction (see min interval)."""
    load_dotenv()
    return (os.getenv("HIBS_PREDICTION_LOG_ALWAYS") or "1").strip().lower() not in ("0", "false", "no", "off")


def _auto_log_max_fixtures() -> int:
    try:
        return max(1, int(os.getenv("HIBS_PREDICTION_LOG_AUTO_MAX", "500")))
    except ValueError:
        return 500


def prediction_log_enabled() -> bool:
    """Public check for audit DB features (calibration shrink, etc.)."""
    return _enabled()


def _clv_enabled() -> bool:
    load_dotenv()
    if not _enabled():
        return False
    raw = (os.getenv("HIBS_CLV_LOG_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


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


def maybe_log_prediction_snapshot(
    fixture: Dict[str, Any],
    prediction: Dict[str, Any],
    *,
    skip_interval: bool = False,
) -> None:
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
            if interval > 0 and not skip_interval:
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


def run_pred_log_sync_for_web(
    *,
    max_fixtures: int = 400,
    min_after_kickoff_hours: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Backfill FT scores for pending audit rows (same as ``pred-log-sync`` CLI).

    Read-only for predictions/DQ — only updates result columns on existing snapshots.
    """
    if not prediction_log_enabled():
        return {
            "ok": False,
            "enabled": False,
            "updated": 0,
            "message": (
                "Model monitor off — set HIBS_PREDICTION_LOG_ENABLED=1 and restart the app."
            ),
        }
    init_db()
    path = _db_path()
    try:
        conn = sqlite3.connect(path, timeout=15)
        try:
            row = conn.execute("SELECT COUNT(*) FROM prediction_snapshots").fetchone()
            n_snap = int(row[0] if row else 0)
        finally:
            conn.close()
    except Exception:
        n_snap = 0
    if n_snap <= 0:
        return {
            "ok": False,
            "enabled": True,
            "updated": 0,
            "message": (
                "No snapshots yet — open the dashboard before kick-off so fixtures are logged."
            ),
        }
    try:
        from hibs_predictor.data_aggregator import DataAggregator

        agg = DataAggregator()
    except Exception as exc:
        return {"ok": False, "enabled": True, "updated": 0, "message": str(exc)}
    if "api_sports" not in agg.clients:
        return {
            "ok": False,
            "enabled": True,
            "updated": 0,
            "message": "API_SPORTS_FOOTBALL_KEY is required to sync finished results.",
        }
    min_h = min_after_kickoff_hours
    if min_h is None:
        try:
            min_h = float(os.getenv("HIBS_PRED_LOG_SYNC_MIN_HOURS", "2.5"))
        except ValueError:
            min_h = 2.5
    fetch_stats = getattr(agg.clients["api_sports"], "fetch_fixture_statistics", None)
    updated = sync_finished_results(
        agg.clients["api_sports"].fetch_fixture,
        fetch_odds_fn=agg.clients["api_sports"].fetch_odds,
        fetch_statistics_fn=fetch_stats,
        max_fixtures=int(max_fixtures),
        min_after_kickoff_hours=float(min_h),
    )
    msg = (
        f"Updated {updated} snapshot row(s) with full-time results."
        if updated
        else "No pending fixtures needed an update (already synced or not FT yet)."
    )
    return {
        "ok": True,
        "enabled": True,
        "updated": int(updated),
        "message": msg,
        "today": monitor_today_dict(),
        "yesterday": monitor_yesterday_dict(),
    }


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
            SELECT id, prediction_json, result_outcome, data_quality_pct,
                   result_home, result_away, result_status
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


def _day_bounds_datetimes(day_offset: int = 0) -> Tuple[datetime, datetime, str, str]:
    """Start/end UTC for a display-TZ calendar day (0=today, -1=yesterday), plus local date and label."""
    from hibs_predictor.display_tz import display_timezone, display_tz_label, local_today

    target = local_today() + timedelta(days=int(day_offset))
    tz = display_timezone()
    start_local = datetime(target.year, target.month, target.day, 0, 0, 0, tzinfo=tz)
    end_local = datetime(target.year, target.month, target.day, 23, 59, 59, tzinfo=tz)
    return (
        start_local.astimezone(timezone.utc),
        end_local.astimezone(timezone.utc),
        target.isoformat(),
        display_tz_label(),
    )


def _today_bounds_datetimes() -> Tuple[datetime, datetime, str, str]:
    """Start/end UTC for the display-TZ calendar day, plus local date and label."""
    return _day_bounds_datetimes(0)


def _yesterday_bounds_datetimes() -> Tuple[datetime, datetime, str, str]:
    """Start/end UTC for yesterday in the display timezone."""
    return _day_bounds_datetimes(-1)


def _today_bounds_utc() -> Tuple[str, str, str, str]:
    """Start/end UTC ISO for the display-TZ calendar day, plus local date and label."""
    start, end, date_local, tz_label = _today_bounds_datetimes()
    return start.isoformat(), end.isoformat(), date_local, tz_label


def _kickoff_in_bounds(kickoff_raw: str, start: datetime, end: datetime) -> bool:
    ko = _parse_kickoff_iso(kickoff_raw)
    if not ko:
        return False
    return start <= ko <= end


def _rows_kickoff_today(
    conn: sqlite3.Connection,
    *,
    start_dt: datetime,
    end_dt: datetime,
) -> List[sqlite3.Row]:
    """Latest snapshot per fixture whose kick-off falls in today's display-TZ window."""
    conn.row_factory = sqlite3.Row
    buf_lo = (start_dt - timedelta(hours=24)).isoformat()
    buf_hi = (end_dt + timedelta(hours=24)).isoformat()
    candidates = conn.execute(
        """
        SELECT id, fixture_id, league_code, captured_at, kickoff_iso,
               home_name, away_name, prediction_json, enrich_summary_json,
               result_home, result_away, result_outcome, result_status, result_recorded_at
        FROM prediction_snapshots
        WHERE kickoff_iso IS NOT NULL AND kickoff_iso != ''
          AND kickoff_iso >= ? AND kickoff_iso <= ?
        ORDER BY captured_at DESC
        """,
        (buf_lo, buf_hi),
    ).fetchall()
    seen: set[int] = set()
    out: List[sqlite3.Row] = []
    for r in candidates:
        fid = int(r["fixture_id"])
        if fid in seen:
            continue
        if not _kickoff_in_bounds(str(r["kickoff_iso"] or ""), start_dt, end_dt):
            continue
        seen.add(fid)
        out.append(r)
    return out


def _rows_scored_ft_today(
    conn: sqlite3.Connection,
    *,
    start_iso: str,
    end_iso: str,
) -> List[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return list(
        conn.execute(
            """
            SELECT id FROM prediction_snapshots
            WHERE result_recorded_at >= ? AND result_recorded_at <= ?
              AND result_outcome IS NOT NULL AND result_outcome != ''
            """,
            (start_iso, end_iso),
        ).fetchall()
    )


def _rows_result_recorded_in_day(
    conn: sqlite3.Connection,
    *,
    start_iso: str,
    end_iso: str,
) -> List[sqlite3.Row]:
    """Latest snapshot per fixture whose FT result was recorded in the display-TZ day window."""
    conn.row_factory = sqlite3.Row
    candidates = conn.execute(
        """
        SELECT id, fixture_id, league_code, captured_at, kickoff_iso,
               home_name, away_name, prediction_json, enrich_summary_json,
               result_home, result_away, result_outcome, result_status, result_recorded_at
        FROM prediction_snapshots
        WHERE result_recorded_at IS NOT NULL AND result_recorded_at != ''
          AND result_recorded_at >= ? AND result_recorded_at <= ?
          AND result_outcome IS NOT NULL AND result_outcome != ''
        ORDER BY result_recorded_at DESC
        """,
        (start_iso, end_iso),
    ).fetchall()
    seen: set[int] = set()
    out: List[sqlite3.Row] = []
    for r in candidates:
        fid = int(r["fixture_id"])
        if fid in seen:
            continue
        seen.add(fid)
        out.append(r)
    return out


def log_predictions_from_fixtures(
    fixtures: List[Dict[str, Any]],
    *,
    max_rows: Optional[int] = None,
) -> int:
    """
    Automated audit logging after each fixture bundle build.

    With HIBS_PREDICTION_LOG_ALWAYS=1 (default): log every row with a prediction, respecting
    HIBS_PREDICTION_LOG_MIN_INTERVAL_SEC per fixture (0 = new row on every bundle pass).
    Otherwise only backfill fixtures missing any snapshot row.
    """
    if not _enabled() or not fixtures:
        return 0
    cap = max_rows if max_rows is not None else _auto_log_max_fixtures()
    if not _always_log():
        return backfill_snapshots_from_fixtures(fixtures, max_rows=min(cap, 80))

    logged = 0
    force_each_pass = _min_interval_sec() <= 0
    for fixture in fixtures:
        if logged >= cap:
            break
        pred = fixture.get("prediction")
        if not isinstance(pred, dict) or pred.get("prediction_unavailable"):
            continue
        if not _fixture_id(fixture):
            continue
        maybe_log_prediction_snapshot(
            fixture,
            pred,
            skip_interval=force_each_pass,
        )
        logged += 1
    return logged


def backfill_snapshots_from_fixtures(
    fixtures: List[Dict[str, Any]],
    *,
    max_rows: int = 80,
) -> int:
    """Log snapshots for fixtures that already have predictions but no audit row yet (best-effort)."""
    if not _enabled() or not fixtures:
        return 0
    try:
        init_db()
        conn = sqlite3.connect(_db_path(), timeout=15)
        try:
            existing = {
                int(r[0])
                for r in conn.execute(
                    "SELECT DISTINCT fixture_id FROM prediction_snapshots"
                ).fetchall()
            }
        finally:
            conn.close()
    except Exception:
        return 0
    logged = 0
    for fixture in fixtures:
        if logged >= max_rows:
            break
        pred = fixture.get("prediction")
        if not isinstance(pred, dict) or pred.get("prediction_unavailable"):
            continue
        fid = _fixture_id(fixture)
        if not fid or fid in existing:
            continue
        maybe_log_prediction_snapshot(fixture, pred, skip_interval=True)
        existing.add(fid)
        logged += 1
    return logged


# value_bets keys (engine) → acca market keys for FT settlement
_VALUE_BET_TO_MARKET_KEY: Dict[str, str] = {
    "home": "home_win",
    "away": "away_win",
    "draw": "draw",
    "btts_yes": "btts_yes",
    "btts_no": "btts_no",
    "over15": "over_15",
    "under15": "under_15",
    "over25": "over_25",
    "under25": "under_25",
    "over35": "over_35",
    "under35": "under_35",
}


def _snapshot_has_value(pred: Dict[str, Any]) -> bool:
    """True when the logged snapshot flagged at least one value bet."""
    if pred.get("has_any_value"):
        return True
    return bool(pred.get("value_bets")) or bool(pred.get("value_bets_alt"))


def _value_bet_row(pred: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
    vb = pred.get("value_bets") or {}
    row = vb.get(key) if isinstance(vb, dict) else None
    if isinstance(row, dict):
        return row
    alt = pred.get("value_bets_alt") or {}
    row = alt.get(key) if isinstance(alt, dict) else None
    return row if isinstance(row, dict) else None


def _value_pick_snapshot(pred: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Top logged value leg (best_bet ROI) with display + settlement keys."""
    if not _snapshot_has_value(pred):
        return None
    key = pred.get("best_bet")
    if not key:
        merged: Dict[str, Any] = {}
        for src in (pred.get("value_bets"), pred.get("value_bets_alt")):
            if isinstance(src, dict):
                merged.update(src)
        if not merged:
            return None
        key = max(
            merged.keys(),
            key=lambda k: float((merged.get(k) or {}).get("roi_percent") or 0),
        )
    row = _value_bet_row(pred, str(key))
    if not row:
        return None
    market_key = str(key)
    settle_key = _VALUE_BET_TO_MARKET_KEY.get(market_key)
    label = row.get("market_label") or market_key.replace("_", " ").title()
    model_pct = row.get("model_probability_pct")
    if model_pct is None:
        try:
            model_pct = round(float(row.get("model_probability") or 0) * 100.0, 1)
        except (TypeError, ValueError):
            model_pct = None
    edge = row.get("edge_pct")
    if edge is None:
        edge = row.get("roi_percent")
    odds = row.get("odds")
    try:
        odds_f = round(float(odds), 2) if odds is not None else None
    except (TypeError, ValueError):
        odds_f = None
    try:
        edge_f = round(float(edge), 1) if edge is not None else None
    except (TypeError, ValueError):
        edge_f = None
    return {
        "market_key": market_key,
        "market_label": label,
        "settle_key": settle_key,
        "model_pct": model_pct,
        "odds": odds_f,
        "edge_pct": edge_f,
    }


def _row_result_packet(row: sqlite3.Row) -> Dict[str, Any]:
    status = str(row["result_status"] or "").upper()
    ft = status == "FT" or (
        row["result_home"] is not None
        and row["result_away"] is not None
        and bool(row["result_outcome"])
    )
    return {
        "fixture_status": "FT" if ft else "NS",
        "live_score_home": row["result_home"],
        "live_score_away": row["result_away"],
    }


def _value_pick_result_label(row: sqlite3.Row, pred: Dict[str, Any]) -> Optional[str]:
    """W / L / pending for the logged value leg; None when snapshot had no value flag."""
    snap = _value_pick_snapshot(pred)
    if not snap:
        return None
    settle_key = snap.get("settle_key")
    if not settle_key:
        return "pending"
    from hibs_predictor.acca_recommender import market_leg_result_label

    return market_leg_result_label(_row_result_packet(row), settle_key)


def _value_pick_tally(rows: List[sqlite3.Row]) -> Dict[str, Any]:
    wins = losses = pending = attempts = 0
    for r in rows:
        try:
            pred = json.loads(r["prediction_json"])
        except Exception:
            continue
        if not isinstance(pred, dict) or not _value_pick_snapshot(pred):
            continue
        attempts += 1
        label = _value_pick_result_label(r, pred)
        if label == "W":
            wins += 1
        elif label == "L":
            losses += 1
        else:
            pending += 1
    settled = wins + losses
    out: Dict[str, Any] = {
        "attempts": attempts,
        "wins": wins,
        "losses": losses,
        "pending": pending,
        "settled": settled,
    }
    if settled:
        out["hit_rate_pct"] = round(100.0 * wins / settled, 2)
    return out


def _best_pick_result_label(
    pred: Dict[str, Any],
    *,
    outcome: Optional[str],
    status: Optional[str],
) -> str:
    pick = (pred.get("predicted_outcome") or "").lower()
    if pick not in ("home", "draw", "away"):
        return "pending"
    oc = (outcome or "").lower()
    if not oc or (status and str(status).upper() != "FT"):
        return "pending"
    return "W" if pick == oc else "L"


def _model_pct_for_pick(pred: Dict[str, Any]) -> Optional[float]:
    pick = (pred.get("predicted_outcome") or "").lower()
    probs = pred.get("probabilities") or {}
    if pick not in ("home", "draw", "away"):
        return None
    return round(_safe_prob(probs.get(pick)) * 100.0, 1)


def _format_score(home: Any, away: Any) -> Optional[str]:
    if home is None or away is None:
        return None
    try:
        return f"{int(home)}-{int(away)}"
    except (TypeError, ValueError):
        return None


def _clv_pp_from_enrich(enrich_raw: Any) -> Optional[float]:
    try:
        enrich = json.loads(enrich_raw or "")
    except Exception:
        return None
    if not isinstance(enrich, dict):
        return None
    clv = enrich.get("clv")
    if not isinstance(clv, dict) or clv.get("clv_pp") is None:
        return None
    try:
        return round(float(clv["clv_pp"]), 2)
    except (TypeError, ValueError):
        return None


def _monitor_rows_to_table(rows: List[sqlite3.Row]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    wins = losses = pending = 0
    table_rows: List[Dict[str, Any]] = []
    for r in rows:
        fid = int(r["fixture_id"])
        try:
            pred = json.loads(r["prediction_json"])
        except Exception:
            pred = {}
        if not isinstance(pred, dict):
            pred = {}
        pick = (pred.get("predicted_outcome") or "").lower()
        label = _best_pick_result_label(
            pred,
            outcome=r["result_outcome"],
            status=r["result_status"],
        )
        if pick in ("home", "draw", "away"):
            if label == "W":
                wins += 1
            elif label == "L":
                losses += 1
            else:
                pending += 1
        value_snap = _value_pick_snapshot(pred)
        value_label = _value_pick_result_label(r, pred) if value_snap else None
        home_nm = str(r["home_name"] or pred.get("home") or "?")
        away_nm = str(r["away_name"] or pred.get("away") or "?")
        table_rows.append(
            {
                "fixture_id": fid,
                "match": f"{home_nm} v {away_nm}",
                "league": str(r["league_code"] or ""),
                "kickoff_iso": r["kickoff_iso"] or "",
                "pick": pick if pick in ("home", "draw", "away") else None,
                "model_pct": _model_pct_for_pick(pred),
                "result": label,
                "score": _format_score(r["result_home"], r["result_away"]),
                "clv_pp": _clv_pp_from_enrich(r["enrich_summary_json"]),
                "has_value": bool(value_snap),
                "value_market": (value_snap or {}).get("market_label"),
                "value_model_pct": (value_snap or {}).get("model_pct"),
                "value_odds": (value_snap or {}).get("odds"),
                "value_edge_pct": (value_snap or {}).get("edge_pct"),
                "value_result": value_label,
            }
        )
    table_rows.sort(
        key=lambda r: (
            0 if r.get("result") == "W" else (2 if r.get("result") == "L" else 1),
            (r.get("match") or "").lower(),
        )
    )
    meta = {
        "best_pick": {"wins": wins, "losses": losses, "pending": pending},
        "value_pick": _value_pick_tally(rows),
    }
    vp = meta["value_pick"]
    if vp.get("hit_rate_pct") is not None:
        meta["value_hit_rate_pct"] = vp["hit_rate_pct"]
    return meta, table_rows


def _monitor_day_dict(
    *,
    day_offset: int,
    empty_label: str,
    window_mode: str = "kickoff",
) -> Dict[str, Any]:
    """One calendar slice: kickoff window or FT results recorded that day (display TZ)."""
    start_dt, end_dt, date_local, tz_label = _day_bounds_datetimes(day_offset)
    start_iso, end_iso = start_dt.isoformat(), end_dt.isoformat()
    from hibs_predictor.display_tz import display_timezone

    tz_key = getattr(display_timezone(), "key", "UTC")
    mode = "scored" if window_mode == "scored" else "kickoff"
    out: Dict[str, Any] = {
        "ok": True,
        "enabled": prediction_log_enabled(),
        "section": mode,
        "date_local": date_local,
        "display_tz": tz_key,
        "display_tz_label": tz_label,
        "window_start_utc": start_iso[:19],
        "window_end_utc": end_iso[:19],
        "n_logged": 0,
        "n_scored_ft": 0,
        "best_pick": {"wins": 0, "losses": 0, "pending": 0},
        "rows": [],
    }
    if not prediction_log_enabled():
        out["message"] = (
            "Model monitor off — prediction log disabled. Set HIBS_PREDICTION_LOG_ENABLED=1."
        )
        return out
    if not os.path.isfile(_db_path()):
        out["message"] = (
            "Model monitor waiting for audit DB — set HIBS_PREDICTION_LOG_ENABLED=1 and use the dashboard."
        )
        return out

    init_db()
    conn = sqlite3.connect(_db_path(), timeout=20)
    try:
        if mode == "scored":
            day_rows = _rows_result_recorded_in_day(conn, start_iso=start_iso, end_iso=end_iso)
            scored_ft = day_rows
        else:
            day_rows = _rows_kickoff_today(conn, start_dt=start_dt, end_dt=end_dt)
            scored_ft = _rows_scored_ft_today(conn, start_iso=start_iso, end_iso=end_iso)
    finally:
        conn.close()

    out["n_logged"] = len(day_rows)
    out["n_scored_ft"] = len(scored_ft)
    table_meta, table_rows = _monitor_rows_to_table(day_rows)
    out["best_pick"] = table_meta.get("best_pick") or {"wins": 0, "losses": 0, "pending": 0}
    out["value_pick"] = table_meta.get("value_pick") or {
        "attempts": 0,
        "wins": 0,
        "losses": 0,
        "pending": 0,
        "settled": 0,
    }
    if table_meta.get("value_hit_rate_pct") is not None:
        out["value_hit_rate_pct"] = table_meta["value_hit_rate_pct"]
    out["rows"] = table_rows
    if not day_rows:
        if mode == "scored":
            out["message"] = (
                f"No FT results recorded {empty_label} ({date_local}) — run pred-log-sync after matches finish."
            )
        else:
            out["message"] = (
                f"No fixtures kicking off {empty_label} ({date_local}) — load the dashboard before kick-off to log predictions."
            )
    return out


def _monitor_combined_day(*, day_offset: int, empty_label: str) -> Dict[str, Any]:
    """Kickoff-day and results-recorded-day slices for templates/API."""
    kickoff = _monitor_day_dict(day_offset=day_offset, empty_label=empty_label, window_mode="kickoff")
    scored = _monitor_day_dict(day_offset=day_offset, empty_label=empty_label, window_mode="scored")
    return {
        "ok": kickoff.get("ok", True),
        "enabled": kickoff.get("enabled"),
        "date_local": kickoff.get("date_local"),
        "display_tz": kickoff.get("display_tz"),
        "display_tz_label": kickoff.get("display_tz_label"),
        "window_start_utc": kickoff.get("window_start_utc"),
        "window_end_utc": kickoff.get("window_end_utc"),
        "kickoff": kickoff,
        "scored": scored,
        "n_logged": kickoff.get("n_logged", 0),
        "n_scored_ft": kickoff.get("n_scored_ft", 0),
        "best_pick": kickoff.get("best_pick") or {"wins": 0, "losses": 0, "pending": 0},
        "value_pick": kickoff.get("value_pick")
        or {"attempts": 0, "wins": 0, "losses": 0, "pending": 0, "settled": 0},
        "value_hit_rate_pct": kickoff.get("value_hit_rate_pct"),
        "rows": kickoff.get("rows") or [],
        "message": kickoff.get("message"),
    }


def monitor_today_dict() -> Dict[str, Any]:
    """Today in display timezone: kickoff window + results recorded today."""
    return _monitor_combined_day(day_offset=0, empty_label="today")


def monitor_yesterday_dict() -> Dict[str, Any]:
    """Yesterday in display timezone: kickoff window + results recorded yesterday."""
    return _monitor_combined_day(day_offset=-1, empty_label="yesterday")


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
    yesterday = monitor_yesterday_dict()
    today = monitor_today_dict()
    base: Dict[str, Any] = {
        "ok": True,
        "enabled": enabled,
        "window_days": window_days,
        "window_start_utc": cutoff[:10],
        "db_path": _db_path(),
        "prediction_log_enabled": enabled,
        "clv_log_enabled": _clv_enabled(),
        "pred_log_sync_cron": pred_log_sync_cron_status(),
        "yesterday": yesterday,
        "today": today,
    }
    if not enabled:
        base.update(
            {
                "ok": False,
                "n_logged": 0,
                "n_scored": 0,
                "message": (
                    "Model monitor off — set HIBS_PREDICTION_LOG_ENABLED=1 "
                    "(monitor follows the prediction log)."
                ),
                "by_league": [],
            }
        )
        return base
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
    value_losses = 0
    value_pending = 0
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

        if _value_pick_snapshot(pred):
            value_attempts += 1
            vlabel = _value_pick_result_label(r, pred)
            if vlabel == "W":
                value_wins += 1
            elif vlabel == "L":
                value_losses += 1
            else:
                value_pending += 1

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
        "value_losses": value_losses,
        "value_pending": value_pending,
        "brier_by_data_quality_bucket": brier_by_data_quality_bucket(),
    }
    value_settled = value_wins + value_losses
    out["value_settled"] = value_settled
    if value_settled:
        out["value_hit_rate"] = round(100.0 * value_wins / value_settled, 2)
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
