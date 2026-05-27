"""Performance page payload (daily scorecard, high-confidence filter)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from hibs_predictor.performance_analytics import (
    build_performance_page_dict,
    performance_daily_history,
)
from hibs_predictor.prediction_log import init_db


@pytest.fixture
def audit_db(tmp_path, monkeypatch):
    db = tmp_path / "audit.sqlite"
    monkeypatch.setenv("HIBS_PREDICTION_LOG_DB", str(db))
    monkeypatch.setenv("HIBS_PREDICTION_LOG_ENABLED", "1")
    init_db()
    return db


def test_build_performance_page_enabled_flag(audit_db, monkeypatch):
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: __import__("datetime").date(2026, 5, 27),
    )
    payload = build_performance_page_dict(history_days=7)
    assert payload["enabled"] is True
    assert "yesterday_scored" in payload
    assert "daily_history" in payload
    assert len(payload["daily_history"]) == 7


def test_daily_history_includes_scored_and_kickoff_keys(audit_db, monkeypatch):
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: __import__("datetime").date(2026, 5, 27),
    )
    row = performance_daily_history(days=3)[0]
    assert row["label"] == "Today"
    assert "scored" in row
    assert "kickoff" in row
    assert "model_record" in row["scored"]


def test_high_confidence_filter_on_scored_day(audit_db, monkeypatch):
    from hibs_predictor.display_tz import display_timezone

    tz = display_timezone()
    now = datetime.now(timezone.utc)
    rec_at = now.isoformat()
    ko = now.isoformat()
    conn = sqlite3.connect(str(audit_db))
    pred = {
        "probabilities": {"home": 0.62, "draw": 0.22, "away": 0.16},
        "predicted_outcome": "home",
        "value_bets": {"home": {"roi_percent": 8, "odds": 2.1, "model_probability_pct": 62}},
        "best_bet": "home",
        "has_any_value": True,
    }
    conn.execute(
        """
        INSERT INTO prediction_snapshots (
            captured_at, fixture_id, league_code, kickoff_iso,
            home_name, away_name, prediction_json,
            result_outcome, result_home, result_away, result_status, result_recorded_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            rec_at,
            9001,
            "INTL_FRIENDLIES",
            ko,
            "A",
            "B",
            json.dumps(pred),
            "home",
            2,
            1,
            "FT",
            rec_at,
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: now.astimezone(tz).date(),
    )
    payload = build_performance_page_dict(history_days=3)
    hc = payload["today_scored"]["high_confidence"]
    assert len(hc) >= 1
    assert hc[0]["model_pct"] >= 55
