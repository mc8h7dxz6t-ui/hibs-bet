"""Tests for rolling-window model monitor aggregation (mock SQLite rows)."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from hibs_predictor.prediction_log import init_db, monitor_summary_dict


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
) -> None:
    pred = {
        "probabilities": probs,
        "predicted_outcome": predicted,
    }
    enrich = {}
    if clv_pp is not None:
        enrich["clv"] = {"clv_pp": clv_pp}
    conn.execute(
        """
        INSERT INTO prediction_snapshots (
            captured_at, fixture_id, league_code, kickoff_iso,
            home_name, away_name, prediction_json, enrich_summary_json,
            result_outcome
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            captured_at,
            1000 + conn.total_changes,
            league,
            captured_at,
            "Home FC",
            "Away FC",
            json.dumps(pred),
            json.dumps(enrich) if enrich else None,
            outcome,
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
