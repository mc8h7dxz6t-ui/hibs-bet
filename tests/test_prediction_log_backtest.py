"""Honest backtest report from prediction audit log."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest


def test_backtest_report_honest_when_no_scored(monkeypatch, tmp_path):
    from hibs_predictor import prediction_log as pl

    db = tmp_path / "audit.sqlite"
    monkeypatch.setenv("HIBS_PREDICTION_LOG_ENABLED", "1")
    monkeypatch.setattr(pl, "_db_path", lambda: str(db))
    pl.init_db()
    kick = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    conn = sqlite3.connect(db)
    conn.execute(
        """
        INSERT INTO prediction_snapshots (
            captured_at, fixture_id, league_code, kickoff_iso, home_name, away_name,
            one_x2_mode, xg_source, data_quality_pct, prediction_json, enrich_summary_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            datetime.now(timezone.utc).isoformat(),
            1001,
            "EPL",
            kick,
            "A",
            "B",
            "ensemble",
            "api",
            90.0,
            json.dumps({"probabilities": {"home": 0.5, "draw": 0.25, "away": 0.25}, "predicted_outcome": "home"}),
            "{}",
        ),
    )
    conn.commit()
    conn.close()

    rep = pl.backtest_report_dict(days=30)
    assert rep["coverage"]["future_or_too_recent"] >= 1
    assert rep["metrics"] is None
    assert "limitations" in rep


def test_backtest_metrics_on_scored_row(monkeypatch, tmp_path):
    from hibs_predictor import prediction_log as pl

    db = tmp_path / "audit.sqlite"
    monkeypatch.setenv("HIBS_PREDICTION_LOG_ENABLED", "1")
    monkeypatch.setattr(pl, "_db_path", lambda: str(db))
    pl.init_db()
    kick = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    cap = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    conn = sqlite3.connect(db)
    conn.execute(
        """
        INSERT INTO prediction_snapshots (
            captured_at, fixture_id, league_code, kickoff_iso, home_name, away_name,
            one_x2_mode, xg_source, data_quality_pct, prediction_json, enrich_summary_json,
            result_home, result_away, result_outcome, result_status, result_recorded_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            cap,
            2002,
            "INTL_FRIENDLIES",
            kick,
            "Home FC",
            "Away FC",
            "ensemble",
            "api",
            88.0,
            json.dumps(
                {
                    "probabilities": {"home": 0.55, "draw": 0.25, "away": 0.20},
                    "predicted_outcome": "home",
                    "bookmaker_odds": {"home": 2.0, "draw": 3.5, "away": 4.0},
                }
            ),
            "{}",
            2,
            1,
            "home",
            "FT",
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    rep = pl.backtest_report_dict(days=30)
    assert rep["metrics"]["n_scored"] == 1
    assert rep["metrics"]["brier_score_1x2"] is not None
    assert rep["metrics"]["best_pick_accuracy_pct"] == 100.0
