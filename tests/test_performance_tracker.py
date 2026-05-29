"""Public performance tracker ledger tests."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from hibs_predictor.performance_tracker import (
    build_public_tracker_dict,
    export_ledger_csv,
    locked_predictions_ledger,
    snapshot_locked_pre_kickoff,
)


def test_snapshot_locked_pre_kickoff_grace():
    ko = "2026-06-01T15:00:00+00:00"
    assert snapshot_locked_pre_kickoff("2026-06-01T14:00:00+00:00", ko) is True
    assert snapshot_locked_pre_kickoff("2026-06-01T15:01:00+00:00", ko) is True
    assert snapshot_locked_pre_kickoff("2026-06-01T16:00:00+00:00", ko) is False


def test_ledger_picks_earliest_pre_kickoff_snapshot(audit_db, monkeypatch):
    monkeypatch.setenv("HIBS_PREDICTION_LOG_ENABLED", "1")
    now = datetime.now(timezone.utc)
    ko = (now + timedelta(days=1)).isoformat()
    early = (now - timedelta(hours=2)).isoformat()
    late = (now + timedelta(minutes=30)).isoformat()
    conn = sqlite3.connect(str(audit_db))
    try:
        for cap, fid in ((early, 7001), (late, 7001), (early, 7002)):
            conn.execute(
                """
                INSERT INTO prediction_snapshots (
                    captured_at, fixture_id, league_code, kickoff_iso,
                    home_name, away_name, prediction_json, enrich_summary_json,
                    result_outcome, result_home, result_away, result_status, result_recorded_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    cap,
                    fid,
                    "WORLD_CUP" if fid == 7002 else "INTL_FRIENDLIES",
                    ko,
                    "A",
                    "B",
                    json.dumps(
                        {
                            "probabilities": {"home": 0.4, "draw": 0.3, "away": 0.3},
                            "predicted_outcome": "home",
                        }
                    ),
                    None,
                    "home" if fid == 7002 else None,
                    2 if fid == 7002 else None,
                    1 if fid == 7002 else None,
                    "FT" if fid == 7002 else None,
                    now.isoformat() if fid == 7002 else None,
                ),
            )
        conn.commit()
    finally:
        conn.close()

    ledger = locked_predictions_ledger(limit=50, days=30)
    by_fid = {r["fixture_id"]: r for r in ledger}
    assert by_fid[7001]["locked_pre_kickoff"] is True
    assert by_fid[7001]["captured_at_utc"] == early
    assert by_fid[7002]["settled"] is True
    assert len(by_fid[7001]["verification_hash"]) == 64

    payload = build_public_tracker_dict(history_days=30)
    assert payload["public"] is True
    assert payload["read_only"] is True
    assert "export_urls" in payload

    csv_text = export_ledger_csv(days=30)
    assert "verification_hash" in csv_text.splitlines()[0]
    assert "7002" in csv_text


@pytest.fixture
def audit_db(tmp_path, monkeypatch):
    db = tmp_path / "audit.sqlite"
    monkeypatch.setenv("HIBS_PREDICTION_LOG_DB", str(db))
    from hibs_predictor.prediction_log import init_db

    init_db()
    return db
