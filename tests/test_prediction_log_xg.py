"""Prediction audit log: post-match xG join and schema migration."""

import json
import sqlite3

from hibs_predictor.prediction_log import (
    init_db,
    parse_result_xg_from_statistics,
    sync_finished_results,
)


def test_parse_result_xg_from_statistics():
    stats = [
        {
            "team": {"id": 1, "name": "Home FC"},
            "statistics": [{"type": "Expected Goals", "value": "1.42"}],
        },
        {
            "team": {"id": 2, "name": "Away FC"},
            "statistics": [{"type": "Expected Goals", "value": "0.88"}],
        },
    ]
    xh, xa = parse_result_xg_from_statistics(
        stats,
        home_team_id=1,
        away_team_id=2,
        home_name="Home FC",
        away_name="Away FC",
    )
    assert xh == 1.42
    assert xa == 0.88


def test_sync_finished_results_joins_xg(monkeypatch, tmp_path):
    db = tmp_path / "audit.sqlite"
    monkeypatch.setenv("HIBS_PREDICTION_LOG_DB", str(db))
    monkeypatch.setenv("HIBS_PREDICTION_LOG_ENABLED", "1")
    init_db()
    pred = {"probabilities": {"home": 0.5, "draw": 0.28, "away": 0.22}}
    conn = sqlite3.connect(str(db))
    conn.execute(
        """
        INSERT INTO prediction_snapshots (
            captured_at, fixture_id, league_code, kickoff_iso, home_name, away_name,
            one_x2_mode, xg_source, data_quality_pct, prediction_json, enrich_summary_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            "2026-01-01T12:00:00+00:00",
            9001,
            "EPL",
            "2020-01-01T15:00:00+00:00",
            "Home FC",
            "Away FC",
            "ensemble",
            "api_fixture_xg",
            85.0,
            json.dumps(pred),
            "{}",
        ),
    )
    conn.commit()
    conn.close()

    stats = [
        {"team": {"id": 1, "name": "Home FC"}, "statistics": [{"type": "Expected Goals", "value": "2.1"}]},
        {"team": {"id": 2, "name": "Away FC"}, "statistics": [{"type": "Expected Goals", "value": "0.7"}]},
    ]

    def _fetch_fixture(fid):
        assert fid == 9001
        return {
            "fixture": {"status": {"short": "FT"}},
            "goals": {"home": 2, "away": 1},
            "teams": {"home": {"id": 1, "name": "Home FC"}, "away": {"id": 2, "name": "Away FC"}},
        }

    n = sync_finished_results(_fetch_fixture, fetch_statistics_fn=lambda _fid: stats)
    assert n == 1

    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT result_home, result_away, result_xg_home, result_xg_away FROM prediction_snapshots WHERE fixture_id=9001"
    ).fetchone()
    conn.close()
    assert row == (2, 1, 2.1, 0.7)


def test_init_db_migrates_xg_columns(tmp_path, monkeypatch):
    db = tmp_path / "legacy.sqlite"
    monkeypatch.setenv("HIBS_PREDICTION_LOG_DB", str(db))
    conn = sqlite3.connect(str(db))
    conn.execute(
        """
        CREATE TABLE prediction_snapshots (
            id INTEGER PRIMARY KEY,
            captured_at TEXT,
            fixture_id INTEGER,
            result_home INTEGER
        )
        """
    )
    conn.commit()
    conn.close()
    init_db()
    conn = sqlite3.connect(str(db))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(prediction_snapshots)")}
    conn.close()
    assert "result_xg_home" in cols
    assert "result_xg_away" in cols
