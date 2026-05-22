"""Tests for historic-data calibration helpers (mocked audit rows)."""

from __future__ import annotations

import json
import sqlite3
import tempfile

import pytest


def test_shrink_multiplier_from_brier_clamped():
    from hibs_predictor.historic_calibration import shrink_multiplier_from_brier

    assert shrink_multiplier_from_brier(0.70, 0.66) <= 1.0
    assert shrink_multiplier_from_brier(0.62, 0.66) >= 1.0
    assert 0.92 <= shrink_multiplier_from_brier(0.90, 0.66) <= 1.08


def test_apply_calibration_shrink_normalises():
    from hibs_predictor.historic_calibration import apply_calibration_shrink

    probs = {"home": 0.6, "draw": 0.2, "away": 0.2}
    out = apply_calibration_shrink(probs, 0.94)
    assert sum(out.values()) == pytest.approx(1.0, abs=1e-5)
    assert out["home"] < probs["home"]


def test_proxy_xg_shrink_toward_league_avg():
    from hibs_predictor.historic_calibration import adjust_xg_for_source_quality

    xh, xa, dbg = adjust_xg_for_source_quality(2.0, 0.5, "goals_proxy", "EPL")
    assert dbg["adjusted"] is True
    assert xh < 2.0
    assert xa > 0.5


def test_h2h_blend_caps_at_five_percent():
    from hibs_predictor.historic_calibration import blend_h2h_into_1x2

    probs = {"home": 0.5, "draw": 0.25, "away": 0.25}
    h2h = {"n": 5, "probs": {"home": 0.8, "draw": 0.1, "away": 0.1}}
    out, dbg = blend_h2h_into_1x2(probs, h2h, max_shift=0.05)
    assert dbg is not None
    assert out["home"] > probs["home"]
    assert out["home"] - probs["home"] <= 0.06


def test_bet_confidence_floor():
    from hibs_predictor.historic_calibration import compute_bet_confidence, min_bet_confidence_for_value

    low = compute_bet_confidence(50.0, 2, 2, "goals_proxy")
    high = compute_bet_confidence(90.0, 10, 10, "stats_api_xg")
    assert high > low
    assert min_bet_confidence_for_value() >= 30.0


def test_bet_confidence_venue_form_depth(monkeypatch):
    from hibs_predictor.historic_calibration import compute_bet_confidence, venue_form_sample_counts

    monkeypatch.setenv("HIBS_BET_CONF_VENUE_FORM", "1")
    full = compute_bet_confidence(80.0, 10, 10, "stats_api_xg", n_home_venue=10, n_away_venue=10)
    thin_venue = compute_bet_confidence(80.0, 10, 10, "stats_api_xg", n_home_venue=2, n_away_venue=3)
    assert full > thin_venue
    nh, na = venue_form_sample_counts(
        {
            "home_last10": [{"home_away": "H"}, {"home_away": "A"}],
            "away_last10": [{"home_away": "A"}, {"home_away": "H"}, {"home_away": "A"}],
        }
    )
    assert nh == 1
    assert na == 2


def test_structured_insight_venue_form():
    from hibs_predictor.match_insight import build_structured_insight

    fixture = {
        "home": "Hibs",
        "away": "Hearts",
        "home_home_factor": 1.15,
        "away_away_factor": 0.92,
        "home_recent_n": 5,
        "away_recent_n": 5,
        "data_quality": {"score_pct": 85.0},
        "home_last10": [
            {"result": "W", "home_away": "H", "score": "2-0"},
            {"result": "L", "home_away": "A", "score": "0-1"},
        ],
        "away_last10": [{"result": "D", "home_away": "A", "score": "1-1"}],
    }
    prediction = {
        "probabilities": {"home": 0.45, "draw": 0.28, "away": 0.27},
        "probabilities_pct": {"home": 45.0, "draw": 28.0, "away": 27.0},
        "btts_probability": 0.55,
        "over25_probability_pct": 52.0,
        "expected_goals_home": 1.4,
        "expected_goals_away": 1.1,
        "form_home": 62.0,
        "form_away": 48.0,
    }
    card = build_structured_insight(fixture, prediction)
    assert card.get("venue_form")
    assert card["venue_form"]["home_at_home"]["n"] == 1
    assert card["venue_form"]["away_on_road"]["n"] == 1
    labels = [m["label"] for m in card.get("rationale_metrics") or []]
    assert "Venue form" in labels


def test_brier_by_league_from_mock_db(monkeypatch, tmp_path):
    from hibs_predictor import prediction_log as pl

    db = tmp_path / "audit.sqlite"
    monkeypatch.setenv("HIBS_PREDICTION_LOG_DB", str(db))
    pl.init_db()
    pred = {
        "probabilities": {"home": 0.55, "draw": 0.25, "away": 0.20},
        "has_any_value": False,
    }
    conn = sqlite3.connect(str(db))
    for i, outcome in enumerate(("home", "home", "away")):
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
                1000 + i,
                "EPL",
                "2026-01-01T15:00:00+00:00",
                "A",
                "B",
                "ensemble",
                "api_xg",
                85.0,
                json.dumps(pred),
                "{}",
                outcome,
            ),
        )
    conn.commit()
    conn.close()

    rows = pl.brier_by_league()
    assert len(rows) == 1
    assert rows[0]["league"] == "EPL"
    assert rows[0]["n"] == 3
    assert rows[0]["brier"] is not None


def test_calibration_fit_writes_cache(monkeypatch, tmp_path):
    from hibs_predictor import prediction_log as pl
    from hibs_predictor.calibration_fit import fit_league_shrink_factors, write_calibration_cache

    db = tmp_path / "audit.sqlite"
    cache = tmp_path / "calibration_v1.json"
    monkeypatch.setenv("HIBS_PREDICTION_LOG_DB", str(db))
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
                2000 + i,
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

    payload = fit_league_shrink_factors(min_rows=2)
    assert payload.get("ok") is True
    assert "EPL" in (payload.get("leagues") or {})
    path = write_calibration_cache(payload)
    assert path == str(cache)
    loaded = json.loads(cache.read_text())
    assert loaded["leagues"]["EPL"]["shrink"] >= 0.92


def test_engine_uses_cached_league_shrink(monkeypatch):
    from hibs_predictor.betting_engine import BettingEngine

    monkeypatch.setenv("HIBS_VALUE_REQUIRE_DATA_PCT", "0")
    monkeypatch.setenv("HIBS_MIN_DATA_QUALITY_PCT", "0")
    monkeypatch.setenv("HIBS_VALUE_MIN_BET_CONFIDENCE", "0")
    fixture = {
        "home": {"id": 10, "name": "H"},
        "away": {"id": 20, "name": "A"},
        "league": "EPL",
        "odds_home": 2.0,
        "odds_draw": 3.4,
        "odds_away": 3.8,
        "odds_available": True,
        "home_stats": {"played": 10, "goals_for": 15, "goals_against": 10},
        "away_stats": {"played": 10, "goals_for": 12, "goals_against": 14},
        "home_form": 0.6,
        "away_form": 0.5,
        "xg_home": 1.4,
        "xg_away": 1.2,
        "xg_source": "goals_proxy",
        "home_recent_n": 8,
        "away_recent_n": 8,
        "data_quality": {"score_pct": 88},
    }
    engine = BettingEngine({})
    pred = engine.predict_with_confidence(fixture)
    hist = pred.get("historic_calibration") or {}
    assert "xg_quality" in hist
    assert pred.get("bet_confidence") is not None
