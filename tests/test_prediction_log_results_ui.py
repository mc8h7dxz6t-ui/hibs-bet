"""Auto settlement + dashboard logged results."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest


def test_recent_logged_results_dedupes_fixtures(monkeypatch, tmp_path):
    from hibs_predictor import prediction_log as pl

    db = tmp_path / "audit.sqlite"
    monkeypatch.setenv("HIBS_PREDICTION_LOG_ENABLED", "1")
    monkeypatch.setattr(pl, "_db_path", lambda: str(db))
    pl.init_db()
    kick = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    rec = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db)
    for i in range(2):
        conn.execute(
            """
            INSERT INTO prediction_snapshots (
                captured_at, fixture_id, league_code, kickoff_iso, home_name, away_name,
                one_x2_mode, xg_source, data_quality_pct, prediction_json, enrich_summary_json,
                result_home, result_away, result_outcome, result_status, result_recorded_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                kick,
                5001,
                "INTL_FRIENDLIES",
                kick,
                "Alpha",
                "Beta",
                "ensemble",
                "api",
                90.0,
                json.dumps(
                    {
                        "probabilities": {"home": 0.6, "draw": 0.22, "away": 0.18},
                        "predicted_outcome": "home",
                    }
                ),
                "{}",
                2,
                0,
                "home",
                "FT",
                rec,
            ),
        )
    conn.commit()
    conn.close()

    out = pl.recent_logged_results_dict(limit=5)
    assert out["enabled"] is True
    assert len(out["rows"]) == 1
    assert out["rows"][0]["result"] == "W"
    assert out["rows"][0]["score"] == "2-0"


def test_auto_sync_throttled(monkeypatch, tmp_path):
    from hibs_predictor import prediction_log as pl

    monkeypatch.setenv("HIBS_PREDICTION_LOG_ENABLED", "1")
    monkeypatch.setenv("HIBS_PRED_LOG_SYNC_AUTO", "1")
    state = tmp_path / "sync.last"
    monkeypatch.setattr(pl, "_auto_sync_state_path", lambda: str(state))
    state.write_text(str(datetime.now(timezone.utc).timestamp()), encoding="utf-8")
    monkeypatch.setattr(pl, "pending_settlement_count", lambda: 5)

    out = pl.maybe_auto_sync_prediction_results()
    assert out.get("skipped") is True
    assert out.get("reason") == "throttled"
