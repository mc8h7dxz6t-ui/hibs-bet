"""Historic snapshot idempotency and insert behaviour."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest


def test_insert_historic_snapshot_skips_when_scored_exists(monkeypatch, tmp_path):
    from hibs_predictor import prediction_log as pl

    db = tmp_path / "audit.sqlite"
    monkeypatch.setenv("HIBS_PREDICTION_LOG_ENABLED", "1")
    monkeypatch.setattr(pl, "_db_path", lambda: str(db))
    pl.init_db()

    kick = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    cap = (datetime.now(timezone.utc) - timedelta(days=6)).isoformat()
    fid = 900001
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
            fid,
            "EPL",
            kick,
            "Home",
            "Away",
            "ensemble",
            "api",
            90.0,
            "{}",
            "{}",
            2,
            1,
            "home",
            "FT",
            cap,
        ),
    )
    conn.commit()
    conn.close()

    fixture = {
        "league": "EPL",
        "date": kick,
        "api_fixture_id": fid,
        "home": {"name": "Home"},
        "away": {"name": "Away"},
    }
    prediction = {
        "home": "Home",
        "away": "Away",
        "probabilities": {"home": 0.5, "draw": 0.25, "away": 0.25},
    }
    result = {"home": 2, "away": 1, "status": "FT"}

    assert pl.insert_historic_snapshot(fixture, prediction, result) == "skipped_scored"
    conn = sqlite3.connect(db)
    n = conn.execute("SELECT COUNT(*) FROM prediction_snapshots WHERE fixture_id = ?", (fid,)).fetchone()[0]
    conn.close()
    assert n == 1


def test_insert_historic_snapshot_updates_unscored_only(monkeypatch, tmp_path):
    from hibs_predictor import prediction_log as pl

    db = tmp_path / "audit.sqlite"
    monkeypatch.setenv("HIBS_PREDICTION_LOG_ENABLED", "1")
    monkeypatch.setattr(pl, "_db_path", lambda: str(db))
    pl.init_db()

    kick = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    cap = datetime.now(timezone.utc).isoformat()
    fid = 900002
    conn = sqlite3.connect(db)
    conn.execute(
        """
        INSERT INTO prediction_snapshots (
            captured_at, fixture_id, league_code, kickoff_iso, home_name, away_name,
            one_x2_mode, xg_source, data_quality_pct, prediction_json, enrich_summary_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (cap, fid, "SCOTLAND", kick, "H", "A", "ensemble", "api", 50.0, "{}", "{}"),
    )
    conn.commit()
    conn.close()

    fixture = {"league": "SCOTLAND", "date": kick, "api_fixture_id": fid}
    prediction = {
        "home": "H",
        "away": "A",
        "probabilities": {"home": 0.4, "draw": 0.3, "away": 0.3},
    }
    result = {"home": 1, "away": 0, "status": "FT"}

    assert pl.insert_historic_snapshot(fixture, prediction, result) == "updated_unscored"
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT result_outcome, result_home, captured_at FROM prediction_snapshots WHERE fixture_id = ?",
        (fid,),
    ).fetchone()
    conn.close()
    assert row[0] == "home"
    assert row[1] == 1
    assert row[2] != cap
