"""Tests for line shopping, CLV, and cross-book value rejection."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile

import pytest


def test_compute_best_line_from_bookmakers():
    from hibs_predictor.data_aggregator import compute_best_line_from_bookmakers

    books = [
        {"bookmaker": "Bet365", "home": 2.1, "draw": 3.4, "away": 3.8},
        {"bookmaker": "Pinnacle", "home": 2.15, "draw": 3.5, "away": 3.6},
        {"bookmaker": "William Hill", "home": 2.05, "draw": 3.3, "away": 3.9},
    ]
    out = compute_best_line_from_bookmakers(books)
    best = out["best_odds_1x2"]
    assert best["home"] == 2.15
    assert best["draw"] == 3.5
    assert best["away"] == 3.9
    assert out["best_odds_source"]["home"] == "Pinnacle"
    assert out["odds_cross_book_max_implied_diff_pct"] > 0
    sharp = out.get("sharp_anchor_implied") or {}
    assert sum(sharp.values()) == pytest.approx(1.0, abs=1e-4)


def test_compute_clv_pp():
    from hibs_predictor.prediction_log import compute_clv_pp

    # Bet at 3.0 (33.3% implied); close at 2.5 (40% implied) → positive CLV
    assert compute_clv_pp(1.0 / 3.0, 0.4) == pytest.approx(6.67, abs=0.05)
    assert compute_clv_pp(None, 0.4) is None


def test_value_reject_on_high_cross_book_diff(monkeypatch):
    from hibs_predictor.betting_engine import BettingEngine

    monkeypatch.setenv("HIBS_ODDS_CROSS_REJECT_PCT", "10")
    fixture = {
        "league": "EPL",
        "odds_cross_book_max_implied_diff_pct": 15.0,
        "data_quality": {"score_pct": 90},
        "xg_source": "api_xg",
    }
    value_bets = {
        "home": {
            "model_probability": 0.55,
            "edge": 0.12,
            "odds": 2.2,
            "roi_percent": 20.0,
        }
    }
    filtered, rejected = BettingEngine._filter_value_bets(
        value_bets,
        fixture,
        {"home": 0.55, "draw": 0.22, "away": 0.23},
        {},
        0.04,
        90.0,
        True,
        cross_pct=15.0,
    )
    assert not filtered
    assert rejected.get("home") == "odds_cross_book_disagreement"


def test_clv_enrich_after_sync(tmp_path, monkeypatch):
    from hibs_predictor import prediction_log as pl

    db = tmp_path / "audit.sqlite"
    monkeypatch.setenv("HIBS_PREDICTION_LOG_DB", str(db))
    monkeypatch.setenv("HIBS_PREDICTION_LOG_ENABLED", "1")
    monkeypatch.setenv("HIBS_CLV_LOG_ENABLED", "1")
    pl.init_db()
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
            99,
            "EPL",
            "2026-01-01T15:00:00+00:00",
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
        return {
            "fixture": {"status": {"short": "FT"}},
            "goals": {"home": 1, "away": 0},
        }

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

    n = pl.sync_finished_results(fetch_fixture, fetch_odds_fn=fetch_odds, min_after_kickoff_hours=0)
    assert n >= 1

    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT enrich_summary_json FROM prediction_snapshots WHERE fixture_id=99"
    ).fetchone()
    conn.close()
    saved = json.loads(row[0])
    assert saved["clv"]["closing_odds_1x2"]["home"] == 1.85
    assert saved["clv"]["clv_pp"] is not None
    assert float(saved["clv"]["clv_pp"]) > 0
