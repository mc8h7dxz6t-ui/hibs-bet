"""Tests for rolling-window model monitor aggregation (mock SQLite rows)."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from hibs_predictor.prediction_log import (
    init_db,
    monitor_summary_dict,
    monitor_today_dict,
    monitor_yesterday_dict,
    report_summary_dict,
)


@pytest.fixture
def audit_db(tmp_path, monkeypatch):
    db = tmp_path / "audit.sqlite"
    monkeypatch.setenv("HIBS_PREDICTION_LOG_DB", str(db))
    monkeypatch.setenv("HIBS_PREDICTION_LOG_ENABLED", "1")
    monkeypatch.setenv("HIBS_MONITOR_DAYS", "28")
    monkeypatch.setenv("HIBS_CLV_LOG_ENABLED", "1")
    init_db()
    return db


def _insert_row(
    conn: sqlite3.Connection,
    *,
    captured_at: str,
    league: str,
    outcome: str | None,
    predicted: str,
    probs: dict,
    clv_pp: float | None = None,
    kickoff_iso: str | None = None,
    result_recorded_at: str | None = None,
    result_home: int | None = None,
    result_away: int | None = None,
    result_status: str | None = None,
    fixture_id: int | None = None,
    pred_extra: dict | None = None,
) -> None:
    pred = {
        "probabilities": probs,
        "predicted_outcome": predicted,
    }
    if pred_extra:
        pred.update(pred_extra)
    enrich = {}
    if clv_pp is not None:
        enrich["clv"] = {"clv_pp": clv_pp}
    fid = fixture_id if fixture_id is not None else 1000 + conn.total_changes
    ko = kickoff_iso if kickoff_iso is not None else captured_at
    conn.execute(
        """
        INSERT INTO prediction_snapshots (
            captured_at, fixture_id, league_code, kickoff_iso,
            home_name, away_name, prediction_json, enrich_summary_json,
            result_outcome, result_home, result_away, result_status, result_recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            captured_at,
            fid,
            league,
            ko,
            "Home FC",
            "Away FC",
            json.dumps(pred),
            json.dumps(enrich) if enrich else None,
            outcome,
            result_home,
            result_away,
            result_status,
            result_recorded_at,
        ),
    )


def test_monitor_empty_db(audit_db):
    rep = monitor_summary_dict()
    assert rep["ok"] is True
    assert rep["n_logged"] == 0
    assert rep["n_scored"] == 0


def test_monitor_window_metrics_and_league_buckets(audit_db):
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(days=3)).isoformat()
    old = (now - timedelta(days=40)).isoformat()

    conn = sqlite3.connect(str(audit_db))
    try:
        _insert_row(
            conn,
            captured_at=recent,
            league="EPL",
            outcome="home",
            predicted="home",
            probs={"home": 0.55, "draw": 0.25, "away": 0.2},
            clv_pp=1.5,
        )
        _insert_row(
            conn,
            captured_at=recent,
            league="EPL",
            outcome="away",
            predicted="home",
            probs={"home": 0.5, "draw": 0.25, "away": 0.25},
            clv_pp=-0.5,
        )
        _insert_row(
            conn,
            captured_at=recent,
            league="WORLD_CUP",
            outcome="draw",
            predicted="draw",
            probs={"home": 0.3, "draw": 0.4, "away": 0.3},
        )
        _insert_row(
            conn,
            captured_at=old,
            league="EPL",
            outcome="home",
            predicted="home",
            probs={"home": 0.9, "draw": 0.05, "away": 0.05},
        )
        conn.commit()
    finally:
        conn.close()

    rep = monitor_summary_dict()
    assert rep["n_logged"] == 3
    assert rep["n_scored"] == 3
    assert rep["n_used_metrics"] == 3
    assert rep["best_pick_n"] == 3
    assert rep["best_pick_correct"] == 2
    assert rep["best_pick_accuracy_pct"] == pytest.approx(66.67, abs=0.1)
    assert rep["brier_score_1x2"] is not None
    assert rep["clv_n"] == 2
    assert rep["beat_close_pct"] == 50.0

    by_league = {r["league"]: r for r in rep["by_league"]}
    assert by_league["EPL"]["n_scored"] == 2
    assert by_league["WORLD_CUP"]["n_scored"] == 1
    assert by_league["WORLD_CUP"]["best_pick_accuracy_pct"] == 100.0


def test_monitor_respects_custom_days(audit_db, monkeypatch):
    monkeypatch.setenv("HIBS_MONITOR_DAYS", "7")
    now = datetime.now(timezone.utc)
    conn = sqlite3.connect(str(audit_db))
    try:
        _insert_row(
            conn,
            captured_at=(now - timedelta(days=5)).isoformat(),
            league="EPL",
            outcome="home",
            predicted="home",
            probs={"home": 0.5, "draw": 0.25, "away": 0.25},
        )
        _insert_row(
            conn,
            captured_at=(now - timedelta(days=10)).isoformat(),
            league="EPL",
            outcome="home",
            predicted="home",
            probs={"home": 0.5, "draw": 0.25, "away": 0.25},
        )
        conn.commit()
    finally:
        conn.close()

    rep = monitor_summary_dict(days=7)
    assert rep["n_logged"] == 1
    assert rep["window_days"] == 7


@pytest.fixture
def today_window(monkeypatch):
    """Fixed calendar-day bounds so tests are stable regardless of run time."""
    today_start = datetime(2026, 5, 24, 0, 0, 0, tzinfo=timezone.utc)
    today_end = datetime(2026, 5, 24, 23, 59, 59, tzinfo=timezone.utc)
    noon = datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc)
    yest_start = datetime(2026, 5, 23, 0, 0, 0, tzinfo=timezone.utc)
    yest_end = datetime(2026, 5, 23, 23, 59, 59, tzinfo=timezone.utc)

    def _day_bounds(day_offset: int = 0):
        if day_offset == -1:
            return (yest_start, yest_end, "2026-05-23", "UK")
        return (today_start, today_end, "2026-05-24", "UK")

    monkeypatch.setattr("hibs_predictor.prediction_log._day_bounds_datetimes", _day_bounds)
    return today_start, today_end, noon


def test_monitor_today_empty(audit_db, today_window):
    rep = monitor_today_dict()
    assert rep["n_logged"] == 0
    assert rep["n_scored_ft"] == 0
    assert rep["date_local"] == "2026-05-24"
    assert rep["rows"] == []


def test_monitor_today_rows_wlp_and_api(audit_db, today_window):
    _start, _end, noon = today_window
    yesterday = datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc).isoformat()

    conn = sqlite3.connect(str(audit_db))
    try:
        _insert_row(
            conn,
            captured_at=noon.isoformat(),
            league="EPL",
            outcome="home",
            predicted="home",
            probs={"home": 0.6, "draw": 0.2, "away": 0.2},
            clv_pp=2.0,
            result_home=2,
            result_away=1,
            result_status="FT",
            result_recorded_at=noon.isoformat(),
            fixture_id=501,
        )
        _insert_row(
            conn,
            captured_at=noon.isoformat(),
            league="EPL",
            outcome="away",
            predicted="home",
            probs={"home": 0.55, "draw": 0.25, "away": 0.2},
            result_home=0,
            result_away=1,
            result_status="FT",
            result_recorded_at=noon.isoformat(),
            fixture_id=502,
        )
        _insert_row(
            conn,
            captured_at=noon.isoformat(),
            league="WORLD_CUP",
            outcome=None,
            predicted="draw",
            probs={"home": 0.3, "draw": 0.4, "away": 0.3},
            fixture_id=503,
        )
        _insert_row(
            conn,
            captured_at=yesterday,
            league="EPL",
            outcome="home",
            predicted="home",
            probs={"home": 0.9, "draw": 0.05, "away": 0.05},
            fixture_id=504,
        )
        conn.commit()
    finally:
        conn.close()

    today = monitor_today_dict()
    assert today["n_logged"] == 3
    assert today["n_scored_ft"] == 2
    assert today["best_pick"] == {"wins": 1, "losses": 1, "pending": 1}
    assert len(today["rows"]) == 3
    by_fid = {r["fixture_id"]: r for r in today["rows"]}
    assert by_fid[501]["result"] == "W"
    assert by_fid[501]["score"] == "2-1"
    assert by_fid[501]["model_pct"] == pytest.approx(60.0)
    assert by_fid[501]["clv_pp"] == 2.0
    assert by_fid[502]["result"] == "L"
    assert by_fid[503]["result"] == "pending"
    assert by_fid[503]["score"] is None

    summary = monitor_summary_dict()
    assert "today" in summary
    assert "yesterday" in summary
    assert summary["today"]["n_logged"] == 3
    assert summary["today"]["best_pick"]["wins"] == 1


def test_monitor_today_uses_kickoff_not_captured_at(audit_db, today_window):
    """Snapshots captured yesterday for today's KO must still appear in Today."""
    _start, _end, noon = today_window
    yesterday = datetime(2026, 5, 23, 20, 0, 0, tzinfo=timezone.utc).isoformat()
    today_ko = noon.isoformat()

    conn = sqlite3.connect(str(audit_db))
    try:
        _insert_row(
            conn,
            captured_at=yesterday,
            kickoff_iso=today_ko,
            league="EPL",
            outcome=None,
            predicted="home",
            probs={"home": 0.5, "draw": 0.25, "away": 0.25},
            fixture_id=601,
        )
        _insert_row(
            conn,
            captured_at=noon.isoformat(),
            kickoff_iso=datetime(2026, 5, 23, 15, 0, 0, tzinfo=timezone.utc).isoformat(),
            league="EPL",
            outcome="home",
            predicted="home",
            probs={"home": 0.9, "draw": 0.05, "away": 0.05},
            fixture_id=602,
        )
        conn.commit()
    finally:
        conn.close()

    today = monitor_today_dict()
    assert today["n_logged"] == 1
    assert today["rows"][0]["fixture_id"] == 601


def test_monitor_today_disabled(monkeypatch, audit_db, today_window):
    monkeypatch.setenv("HIBS_PREDICTION_LOG_ENABLED", "0")
    rep = monitor_today_dict()
    assert rep["enabled"] is False
    assert rep["n_logged"] == 0
    assert "disabled" in (rep.get("message") or "").lower()
    summary = monitor_summary_dict()
    assert summary["enabled"] is False
    assert "yesterday" in summary
    assert "HIBS_PREDICTION_LOG_ENABLED" in (summary.get("message") or "")


def test_monitor_yesterday_rows_wlp(audit_db, today_window):
    _start, _end, noon = today_window
    yesterday_noon = datetime(2026, 5, 23, 15, 0, 0, tzinfo=timezone.utc)
    today_ko = noon.isoformat()

    conn = sqlite3.connect(str(audit_db))
    try:
        _insert_row(
            conn,
            captured_at=yesterday_noon.isoformat(),
            kickoff_iso=yesterday_noon.isoformat(),
            league="EPL",
            outcome="draw",
            predicted="draw",
            probs={"home": 0.25, "draw": 0.5, "away": 0.25},
            result_home=1,
            result_away=1,
            result_status="FT",
            result_recorded_at=yesterday_noon.isoformat(),
            fixture_id=701,
        )
        _insert_row(
            conn,
            captured_at=yesterday_noon.isoformat(),
            kickoff_iso=yesterday_noon.isoformat(),
            league="EPL",
            outcome="home",
            predicted="away",
            probs={"home": 0.2, "draw": 0.25, "away": 0.55},
            result_home=2,
            result_away=0,
            result_status="FT",
            fixture_id=702,
        )
        _insert_row(
            conn,
            captured_at=noon.isoformat(),
            kickoff_iso=today_ko,
            league="EPL",
            outcome="home",
            predicted="home",
            probs={"home": 0.6, "draw": 0.2, "away": 0.2},
            fixture_id=703,
        )
        conn.commit()
    finally:
        conn.close()

    yest = monitor_yesterday_dict()
    assert yest["date_local"] == "2026-05-23"
    assert yest["kickoff"]["n_logged"] == 2
    assert yest["n_logged"] == 2
    assert yest["kickoff"]["best_pick"] == {"wins": 1, "losses": 1, "pending": 0}
    by_fid = {r["fixture_id"]: r for r in yest["kickoff"]["rows"]}
    assert by_fid[701]["result"] == "W"
    assert by_fid[702]["result"] == "L"

    today = monitor_today_dict()
    assert today["n_logged"] == 1
    assert today["rows"][0]["fixture_id"] == 703


def test_monitor_yesterday_uses_kickoff_not_captured_at(audit_db, today_window):
    """Captured today for yesterday's KO must appear in Yesterday, not Today."""
    _start, _end, noon = today_window
    yesterday_ko = datetime(2026, 5, 23, 18, 0, 0, tzinfo=timezone.utc).isoformat()

    conn = sqlite3.connect(str(audit_db))
    try:
        _insert_row(
            conn,
            captured_at=noon.isoformat(),
            kickoff_iso=yesterday_ko,
            league="EPL",
            outcome="away",
            predicted="away",
            probs={"home": 0.2, "draw": 0.25, "away": 0.55},
            fixture_id=801,
        )
        conn.commit()
    finally:
        conn.close()

    yest = monitor_yesterday_dict()
    assert yest["kickoff"]["n_logged"] == 1
    assert yest["kickoff"]["rows"][0]["fixture_id"] == 801
    assert monitor_today_dict()["kickoff"]["n_logged"] == 0


def test_monitor_yesterday_scored_section(audit_db, today_window):
    """FT synced yesterday appears under scored even when kickoff was earlier."""
    _start, _end, noon = today_window
    old_ko = datetime(2026, 5, 20, 15, 0, 0, tzinfo=timezone.utc).isoformat()
    yest_sync = datetime(2026, 5, 23, 20, 0, 0, tzinfo=timezone.utc).isoformat()

    conn = sqlite3.connect(str(audit_db))
    try:
        _insert_row(
            conn,
            captured_at=old_ko,
            kickoff_iso=old_ko,
            league="EPL",
            outcome="home",
            predicted="home",
            probs={"home": 0.7, "draw": 0.2, "away": 0.1},
            result_home=2,
            result_away=0,
            result_status="FT",
            result_recorded_at=yest_sync,
            fixture_id=901,
        )
        conn.commit()
    finally:
        conn.close()

    yest = monitor_yesterday_dict()
    assert yest["kickoff"]["n_logged"] == 0
    assert yest["scored"]["n_logged"] == 1
    assert yest["scored"]["rows"][0]["fixture_id"] == 901
    assert yest["scored"]["rows"][0]["result"] == "W"


def test_report_value_hit_non_1x2_market(audit_db):
    """Value hit must settle BTTS/totals, not only 1X2 best_bet keys."""
    conn = sqlite3.connect(str(audit_db))
    try:
        _insert_row(
            conn,
            captured_at="2026-05-20T10:00:00+00:00",
            league="EPL",
            outcome="home",
            predicted="home",
            probs={"home": 0.5, "draw": 0.25, "away": 0.25},
            result_home=2,
            result_away=1,
            result_status="FT",
            pred_extra={
                "has_any_value": True,
                "best_bet": "btts_yes",
                "value_bets": {
                    "btts_yes": {
                        "market_label": "BTTS Yes",
                        "model_probability_pct": 62.0,
                        "edge_pct": 4.2,
                        "odds": 1.85,
                        "roi_percent": 4.2,
                    }
                },
            },
        )
        _insert_row(
            conn,
            captured_at="2026-05-20T11:00:00+00:00",
            league="EPL",
            outcome="home",
            predicted="home",
            probs={"home": 0.55, "draw": 0.25, "away": 0.2},
            result_home=1,
            result_away=0,
            result_status="FT",
            fixture_id=1002,
            pred_extra={
                "has_any_value": True,
                "best_bet": "over25",
                "value_bets": {
                    "over25": {
                        "market_label": "Over 2.5",
                        "model_probability_pct": 58.0,
                        "edge_pct": 3.0,
                        "odds": 1.9,
                        "roi_percent": 3.0,
                    }
                },
            },
        )
        conn.commit()
    finally:
        conn.close()

    rep = report_summary_dict()
    assert rep["value_flags_count"] == 2
    assert rep["value_settled"] == 2
    assert rep["value_best_outcome_hits"] == 1
    assert rep["value_hit_rate"] == 50.0


def test_monitor_yesterday_value_hit_rate(audit_db, today_window):
    _start, _end, noon = today_window
    yesterday_noon = datetime(2026, 5, 23, 15, 0, 0, tzinfo=timezone.utc)

    conn = sqlite3.connect(str(audit_db))
    try:
        _insert_row(
            conn,
            captured_at=yesterday_noon.isoformat(),
            kickoff_iso=yesterday_noon.isoformat(),
            league="EPL",
            outcome="home",
            predicted="away",
            probs={"home": 0.2, "draw": 0.25, "away": 0.55},
            result_home=2,
            result_away=1,
            result_status="FT",
            result_recorded_at=yesterday_noon.isoformat(),
            fixture_id=801,
            pred_extra={
                "has_any_value": True,
                "best_bet": "btts_yes",
                "value_bets": {
                    "btts_yes": {
                        "market_label": "BTTS Yes",
                        "model_probability_pct": 60.0,
                        "edge_pct": 5.0,
                        "odds": 1.8,
                        "roi_percent": 5.0,
                    }
                },
            },
        )
        conn.commit()
    finally:
        conn.close()

    yest = monitor_yesterday_dict()
    vp = yest["kickoff"]["value_pick"]
    assert vp["attempts"] == 1
    assert vp["wins"] == 1
    assert vp["hit_rate_pct"] == 100.0
    assert yest["value_hit_rate_pct"] == 100.0
    row = yest["kickoff"]["rows"][0]
    assert row["has_value"] is True
    assert row["value_result"] == "W"
    assert row["value_market"] == "BTTS Yes"


def test_run_pred_log_sync_for_web_disabled(monkeypatch, audit_db):
    from hibs_predictor.prediction_log import run_pred_log_sync_for_web

    monkeypatch.setenv("HIBS_PREDICTION_LOG_ENABLED", "0")
    out = run_pred_log_sync_for_web()
    assert out["ok"] is False
    assert out["enabled"] is False
    assert out["updated"] == 0


def test_run_pred_log_sync_for_web_no_snapshots(monkeypatch, audit_db):
    from hibs_predictor.prediction_log import run_pred_log_sync_for_web

    out = run_pred_log_sync_for_web()
    assert out["ok"] is False
    assert out["enabled"] is True
    assert "snapshots" in (out.get("message") or "").lower()
