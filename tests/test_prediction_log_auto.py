"""Automated prediction audit logging on bundle finalize."""

from __future__ import annotations

import sqlite3

from hibs_predictor.prediction_log import _db_path, init_db, log_predictions_from_fixtures


def _fixture(fid: int) -> dict:
    return {
        "id": fid,
        "fixture": {"id": fid, "date": "2099-06-01T15:00:00+00:00"},
        "date": "2099-06-01T15:00:00+00:00",
        "league": "EPL",
        "prediction": {
            "home": "Home",
            "away": "Away",
            "probabilities": {"home": 0.4, "draw": 0.3, "away": 0.3},
            "one_x2_mode": "ensemble",
        },
    }


def test_log_predictions_from_fixtures_always_mode(monkeypatch, tmp_path):
    db = tmp_path / "audit.sqlite"
    monkeypatch.setenv("HIBS_PREDICTION_LOG_DB", str(db))
    monkeypatch.setenv("HIBS_PREDICTION_LOG_ENABLED", "1")
    monkeypatch.setenv("HIBS_PREDICTION_LOG_ALWAYS", "1")
    monkeypatch.setenv("HIBS_PREDICTION_LOG_MIN_INTERVAL_SEC", "0")

    fixtures = [_fixture(101), _fixture(102)]
    n = log_predictions_from_fixtures(fixtures)
    assert n == 2
    init_db()
    conn = sqlite3.connect(_db_path())
    try:
        count = conn.execute("SELECT COUNT(*) FROM prediction_snapshots").fetchone()[0]
    finally:
        conn.close()
    assert count == 2


def test_log_predictions_backfill_when_always_off(monkeypatch, tmp_path):
    db = tmp_path / "audit.sqlite"
    monkeypatch.setenv("HIBS_PREDICTION_LOG_DB", str(db))
    monkeypatch.setenv("HIBS_PREDICTION_LOG_ENABLED", "1")
    monkeypatch.setenv("HIBS_PREDICTION_LOG_ALWAYS", "0")

    fx = _fixture(201)
    n = log_predictions_from_fixtures([fx])
    assert n == 1
    n2 = log_predictions_from_fixtures([fx])
    assert n2 == 0
