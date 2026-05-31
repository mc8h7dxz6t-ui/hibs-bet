"""Settlement loop: API fixture id resolution + FT join."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest


def test_fixture_id_prefers_api_fixture_id(monkeypatch, tmp_path):
    from hibs_predictor import prediction_log as pl

    monkeypatch.setattr(pl, "_db_path", lambda: str(tmp_path / "audit.sqlite"))
    fid = pl._fixture_id(
        {
            "id": "fotmob_999001",
            "api_fixture_id": 1544371,
            "home": "A",
            "away": "B",
        }
    )
    assert fid == 1544371


def test_sync_resolves_by_team_when_stored_id_invalid(monkeypatch, tmp_path):
    from hibs_predictor import prediction_log as pl

    db = tmp_path / "audit.sqlite"
    monkeypatch.setenv("HIBS_PREDICTION_LOG_ENABLED", "1")
    monkeypatch.setattr(pl, "_db_path", lambda: str(db))
    pl.init_db()
    kick = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    conn = sqlite3.connect(db)
    conn.execute(
        """
        INSERT INTO prediction_snapshots (
            captured_at, fixture_id, league_code, kickoff_iso, home_name, away_name,
            one_x2_mode, xg_source, data_quality_pct, prediction_json, enrich_summary_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            kick,
            999001,
            "EPL",
            kick,
            "Arsenal",
            "Chelsea",
            "ensemble",
            "api",
            90.0,
            json.dumps(
                {
                    "probabilities_pct": {"home": 45, "draw": 28, "away": 27},
                    "predicted_outcome": "home",
                }
            ),
            "{}",
        ),
    )
    conn.commit()
    conn.close()

    def fetch_fixture(_fid: int):
        return {}

    def fetch_by_league(_league_id, _season, date_from=None, date_to=None):
        day = (date_from or "")[:10]
        return [
            {
                "fixture": {"id": 1544001, "status": {"short": "FT"}},
                "goals": {"home": 2, "away": 1},
                "teams": {
                    "home": {"name": "Arsenal"},
                    "away": {"name": "Chelsea"},
                },
            }
        ]

    stats = pl.sync_finished_results(
        fetch_fixture,
        fetch_by_league_fn=fetch_by_league,
        min_after_kickoff_hours=0,
    )
    assert stats["updated"] >= 1
    assert stats["resolved_by_teams"] >= 1
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT result_outcome, fixture_id FROM prediction_snapshots WHERE id=1"
    ).fetchone()
    conn.close()
    assert row[0] == "home"
    assert row[1] == 1544001
