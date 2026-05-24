"""CLV opening capture, closing sync, beat-close reporting, calibration-fit CLI."""

import json
import sqlite3

import pytest

from hibs_predictor.prediction_log import (
    clv_beat_close_by_league,
    init_db,
    maybe_log_prediction_snapshot,
    parse_closing_1x2_from_odds_response,
    sync_finished_results,
)


def test_opening_clv_captured_on_snapshot(monkeypatch, tmp_path):
    db = tmp_path / "audit.sqlite"
    monkeypatch.setenv("HIBS_PREDICTION_LOG_DB", str(db))
    monkeypatch.setenv("HIBS_PREDICTION_LOG_ENABLED", "1")
    monkeypatch.setenv("HIBS_CLV_LOG_ENABLED", "1")
    monkeypatch.setenv("HIBS_PREDICTION_LOG_MIN_INTERVAL_SEC", "0")

    fixture = {
        "fixture": {"id": 5001},
        "date": "2026-05-20T15:00:00+00:00",
        "league": "EPL",
        "odds_cross_max_implied_diff_pct": 2.5,
        "data_quality": {"score_pct": 88},
    }
    prediction = {
        "home": "Arsenal",
        "away": "Chelsea",
        "probabilities": {"home": 0.55, "draw": 0.25, "away": 0.20},
        "bookmaker_odds": {"home": 1.95, "draw": 3.6, "away": 4.2},
        "best_bet": "home",
        "value_bets": {"home": {"odds": 1.95, "edge_pct": 6.2}},
    }
    maybe_log_prediction_snapshot(fixture, prediction)

    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT enrich_summary_json FROM prediction_snapshots WHERE fixture_id=5001"
    ).fetchone()
    conn.close()
    assert row is not None
    enrich = json.loads(row[0])
    clv = enrich["clv"]
    assert clv["opening_odds_1x2"]["home"] == 1.95
    assert clv["best_bet_outcome"] == "home"
    assert clv["best_bet_odds"] == 1.95
    assert clv["closing_odds_1x2"] is None
    assert clv["clv_pp"] is None


def test_parse_closing_1x2_best_prices():
    odds_raw = [
        {
            "bookmakers": [
                {
                    "bets": [
                        {
                            "name": "Match Winner",
                            "values": [
                                {"value": "Home", "odd": "1.90"},
                                {"value": "Draw", "odd": "3.50"},
                                {"value": "Away", "odd": "4.00"},
                            ],
                        }
                    ]
                },
                {
                    "bets": [
                        {
                            "name": "Match Winner",
                            "values": [
                                {"value": "Home", "odd": "1.95"},
                                {"value": "Draw", "odd": "3.40"},
                                {"value": "Away", "odd": "4.10"},
                            ],
                        }
                    ]
                },
            ]
        }
    ]
    closing = parse_closing_1x2_from_odds_response(odds_raw)
    assert closing["home"] == 1.95
    assert closing["draw"] == 3.50
    assert closing["away"] == 4.10


def test_clv_beat_close_by_league_after_sync(monkeypatch, tmp_path):
    db = tmp_path / "audit.sqlite"
    monkeypatch.setenv("HIBS_PREDICTION_LOG_DB", str(db))
    monkeypatch.setenv("HIBS_PREDICTION_LOG_ENABLED", "1")
    monkeypatch.setenv("HIBS_CLV_LOG_ENABLED", "1")
    init_db()
    enrich = {
        "clv": {
            "opening_odds_1x2": {"home": 2.0, "draw": 3.5, "away": 4.0},
            "best_bet_outcome": "home",
            "best_bet_odds": 2.0,
            "closing_odds_1x2": None,
            "clv_pp": None,
        }
    }
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
            8801,
            "EPL",
            "2020-01-01T15:00:00+00:00",
            "A",
            "B",
            "ensemble",
            "api_xg",
            85.0,
            "{}",
            json.dumps(enrich),
        ),
    )
    conn.commit()
    conn.close()

    def fetch_fixture(_fid):
        return {"fixture": {"status": {"short": "FT"}}, "goals": {"home": 1, "away": 0}}

    def fetch_odds(_fid):
        return [
            {
                "bookmakers": [
                    {
                        "bets": [
                            {
                                "name": "Match Winner",
                                "values": [
                                    {"value": "Home", "odd": "1.85"},
                                    {"value": "Draw", "odd": "3.6"},
                                    {"value": "Away", "odd": "4.2"},
                                ],
                            }
                        ]
                    }
                ]
            }
        ]

    sync_finished_results(fetch_fixture, fetch_odds_fn=fetch_odds, min_after_kickoff_hours=0)

    report = clv_beat_close_by_league()
    assert report["enabled"] is True
    assert report["n_clv_rows"] == 1
    assert report["beat_close_pct"] == 100.0
    assert len(report["leagues"]) == 1
    assert report["leagues"][0]["league"] == "EPL"
    assert report["leagues"][0]["avg_clv_pp"] > 0


def test_calibration_fit_cli_writes_cache(monkeypatch, tmp_path, capsys):
    from hibs_predictor import prediction_log as pl
    from hibs_predictor.main import run_calibration_fit

    db = tmp_path / "audit.sqlite"
    cache = tmp_path / "calibration_v1.json"
    monkeypatch.setenv("HIBS_PREDICTION_LOG_DB", str(db))
    monkeypatch.setenv("HIBS_PREDICTION_LOG_ENABLED", "1")
    monkeypatch.setenv("HIBS_CALIBRATION_CACHE", str(cache))
    monkeypatch.setenv("HIBS_CALIB_FIT_MIN_ROWS", "2")
    pl.init_db()
    pred = {"probabilities": {"home": 0.5, "draw": 0.28, "away": 0.22}}
    conn = sqlite3.connect(str(db))
    for i in range(3):
        conn.execute(
            """
            INSERT INTO prediction_snapshots (
                captured_at, fixture_id, league_code, kickoff_iso, home_name, away_name,
                one_x2_mode, xg_source, data_quality_pct, prediction_json, enrich_summary_json,
                result_outcome
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "2026-01-01T12:00:00+00:00",
                3000 + i,
                "EPL",
                "2026-01-01T15:00:00+00:00",
                "A",
                "B",
                "ensemble",
                "api_xg",
                85.0,
                json.dumps(pred),
                "{}",
                "home",
            ),
        )
    conn.commit()
    conn.close()

    run_calibration_fit()
    out = capsys.readouterr().out
    assert "league shrink" in out.lower() or "Wrote" in out
    assert cache.is_file()
    loaded = json.loads(cache.read_text())
    assert "EPL" in loaded.get("leagues", {})
