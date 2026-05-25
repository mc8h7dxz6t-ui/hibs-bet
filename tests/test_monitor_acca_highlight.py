"""Monitor row ordering and acca leg result labelling (display-only)."""

from __future__ import annotations

import json
import sqlite3

import pytest

from hibs_predictor.acca_recommender import (
    _annotate_acca_results,
    build_acca_recommendations,
    market_leg_result_label,
)
from hibs_predictor.prediction_log import _monitor_rows_to_table, init_db


def test_market_leg_result_from_ft_scores():
    pkt = {
        "fixture_status": "FT",
        "live_score_home": 2,
        "live_score_away": 1,
    }
    assert market_leg_result_label(pkt, "home_win") == "W"
    assert market_leg_result_label(pkt, "away_win") == "L"
    assert market_leg_result_label(pkt, "btts_yes") == "W"
    assert market_leg_result_label(pkt, "over_25") == "W"
    assert market_leg_result_label({"fixture_status": "NS"}, "home_win") == "pending"
    assert market_leg_result_label(pkt, "unknown_market") == "pending"


def test_monitor_rows_sort_wins_first():
    rows = [
        {
            "match": "B v C",
            "pick": "home",
            "model_pct": 50.0,
            "result": "L",
            "score": "0-1",
            "clv_pp": None,
        },
        {
            "match": "A v B",
            "pick": "away",
            "model_pct": 40.0,
            "result": "W",
            "score": "0-2",
            "clv_pp": 1.2,
        },
        {
            "match": "C v D",
            "pick": "draw",
            "model_pct": 30.0,
            "result": "pending",
            "score": None,
            "clv_pp": None,
        },
    ]
    # Re-sort using same key as production helper
    rows.sort(
        key=lambda r: (
            0 if r.get("result") == "W" else (2 if r.get("result") == "L" else 1),
            (r.get("match") or "").lower(),
        )
    )
    assert [r["result"] for r in rows] == ["W", "pending", "L"]


def test_monitor_rows_to_table_sorts_wins_first(audit_db):
    conn = sqlite3.connect(str(audit_db))
    conn.row_factory = sqlite3.Row
    try:
        pred = {
            "predicted_outcome": "home",
            "probabilities": {"home": 0.55, "draw": 0.25, "away": 0.2},
        }
        conn.execute(
            """
            INSERT INTO prediction_snapshots (
                captured_at, fixture_id, league_code, kickoff_iso,
                home_name, away_name, prediction_json,
                result_outcome, result_home, result_away, result_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-24T12:00:00+00:00",
                901,
                "EPL",
                "2026-05-24T15:00:00+00:00",
                "Winners",
                "Losers",
                json.dumps(pred),
                "home",
                2,
                0,
                "FT",
            ),
        )
        conn.execute(
            """
            INSERT INTO prediction_snapshots (
                captured_at, fixture_id, league_code, kickoff_iso,
                home_name, away_name, prediction_json,
                result_outcome, result_home, result_away, result_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-24T12:00:00+00:00",
                902,
                "EPL",
                "2026-05-24T15:00:00+00:00",
                "Alpha",
                "Beta",
                json.dumps(
                    {
                        "predicted_outcome": "away",
                        "probabilities": {"home": 0.3, "draw": 0.3, "away": 0.4},
                    }
                ),
                "home",
                1,
                0,
                "FT",
            ),
        )
        conn.commit()
        db_rows = conn.execute("SELECT * FROM prediction_snapshots ORDER BY fixture_id").fetchall()
    finally:
        conn.close()

    _bp, table_rows = _monitor_rows_to_table(db_rows)
    assert _bp["wins"] == 1
    assert _bp["losses"] == 1
    assert table_rows[0]["result"] == "W"
    assert table_rows[-1]["result"] == "L"


@pytest.fixture
def audit_db(tmp_path, monkeypatch):
    db = tmp_path / "audit.sqlite"
    monkeypatch.setenv("HIBS_PREDICTION_LOG_DB", str(db))
    monkeypatch.setenv("HIBS_PREDICTION_LOG_ENABLED", "1")
    init_db()
    return db


def test_insights_template_highlight_markup():
    from pathlib import Path

    text = Path(__file__).resolve().parents[1].joinpath("templates/insights.html").read_text()
    assert "monitor-win" in text
    assert "acca-win-card" in text
    assert "monitor-tally" in text
    assert "result-badge-w" in text


def test_annotate_acca_all_legs_won():
    acca = {
        "name": "Test 2-fold",
        "legs": [
            {"fixture_id": 1, "market_key": "home_win", "reasoning": "Home edge."},
            {"fixture_id": 2, "market_key": "btts_yes", "reasoning": "Open game."},
        ],
    }
    packets = {
        1: {"fixture_status": "FT", "live_score_home": 2, "live_score_away": 0},
        2: {"fixture_status": "FT", "live_score_home": 1, "live_score_away": 2},
    }
    winning, other = _annotate_acca_results([acca], packets)
    assert len(winning) == 1
    assert winning[0]["is_winning"] is True
    assert all(leg["result"] == "W" for leg in winning[0]["legs"])
    assert other == []
