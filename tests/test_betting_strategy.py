"""Tests for line shopping, CLV, cross-book value rejection, balanced value, dual finder."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile

import pytest


def test_odds_event_matches_fixture_by_teams_and_kickoff():
    from hibs_predictor.data_aggregator import (
        _odds_event_matches_fixture,
        _odds_outcome_side,
        _odds_teams_swapped,
    )

    fixture = {
        "home": "Hibernian",
        "away": "Celtic",
        "date": "2026-05-25T15:00:00+00:00",
    }
    event_ok = {
        "home_team": "Hibernian",
        "away_team": "Celtic",
        "commence_time": "2026-05-25T15:30:00Z",
    }
    event_wrong_ko = {**event_ok, "commence_time": "2026-05-26T15:00:00Z"}
    event_wrong_teams = {**event_ok, "home_team": "Hearts", "away_team": "Rangers"}

    assert _odds_event_matches_fixture(event_ok, fixture, "Hibernian", "Celtic")
    assert not _odds_event_matches_fixture(event_wrong_ko, fixture, "Hibernian", "Celtic")
    assert not _odds_event_matches_fixture(event_wrong_teams, fixture, "Hibernian", "Celtic")

    swapped = _odds_teams_swapped("Hibernian", "Celtic", "Celtic", "Hibernian")
    assert swapped
    assert _odds_outcome_side("Celtic", "Hibernian", "Celtic", teams_swapped=swapped) == "home"
    assert _odds_outcome_side("Hibernian", "Hibernian", "Celtic", teams_swapped=swapped) == "away"


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


def test_value_not_only_outsiders(monkeypatch):
    """Short-priced favourite with strong model prob should pass value filters."""
    from hibs_predictor.betting_engine import BettingEngine, OddsAnalyzer

    monkeypatch.setenv("HIBS_VALUE_MAX_ODDS", "6")
    raw = OddsAnalyzer.identify_value_bets(
        {"home": 0.58, "draw": 0.24, "away": 0.18},
        {"home": 2.05, "draw": 3.8, "away": 5.0},
        margin=0.04,
    )
    assert "home" in raw
    fixture = {
        "league": "EPL",
        "odds_cross_book_max_implied_diff_pct": 2.0,
        "data_quality": {"score_pct": 90},
        "xg_source": "api_xg",
        "home_position": {"position": 3},
        "away_position": {"position": 8},
        "home_form": 0.7,
        "away_form": 0.5,
        "home_stats": {"played": 20},
        "away_stats": {"played": 20},
    }
    filtered, rejected = BettingEngine._filter_value_bets(
        raw,
        fixture,
        {"home": 0.58, "draw": 0.24, "away": 0.18},
        {
            "table_gap_home_worse": -5,
            "xg_gap_home_minus_away": 0.2,
            "form_gap_home_minus_away": 0.2,
            "strength_gap_home_minus_away": 0.1,
        },
        0.04,
        90.0,
        True,
        cross_pct=2.0,
    )
    assert "home" in filtered
    assert filtered["home"].get("odds", 99) < 2.5
    assert rejected.get("home") is None


def test_market_consensus_value_favorite():
    from hibs_predictor.betting_engine import OddsAnalyzer

    sharp = {"home": 0.52, "draw": 0.26, "away": 0.22}
    out = OddsAnalyzer.identify_market_consensus_value(
        {"home": 0.58, "draw": 0.24, "away": 0.18},
        sharp,
        {"home": 1.75, "draw": 3.6, "away": 4.5},
        margin=0.03,
        min_model_prob=0.52,
    )
    assert "home" in out
    assert out["home"]["source"] == "market_consensus"


def test_dual_value_finder_agreement(monkeypatch):
    from hibs_predictor.betting_engine import BettingEngine

    monkeypatch.setenv("HIBS_VALUE_CONSENSUS_MARGIN", "0.02")
    monkeypatch.setenv("HIBS_VALUE_CONSENSUS_MIN_MODEL", "0.52")
    monkeypatch.setenv("HIBS_VALUE_REQUIRE_DATA_PCT", "0")
    monkeypatch.setenv("HIBS_MIN_DATA_QUALITY_PCT", "0")

    fixture = {
        "home": {"id": 1, "name": "Team A"},
        "away": {"id": 2, "name": "Team B"},
        "league": "EPL",
        "odds_home": 1.8,
        "odds_draw": 3.6,
        "odds_away": 4.5,
        "odds_available": True,
        "best_odds_1x2": {"home": 1.8, "draw": 3.6, "away": 4.5},
        "sharp_anchor_implied": {"home": 0.52, "draw": 0.26, "away": 0.22},
        "home_stats": {
            "played": 15,
            "goals_for": 28,
            "goals_against": 18,
            "expected_goals": 27,
            "expected_goals_against": 17,
        },
        "away_stats": {
            "played": 15,
            "goals_for": 20,
            "goals_against": 22,
            "expected_goals": 19,
            "expected_goals_against": 23,
        },
        "home_form": 0.72,
        "away_form": 0.48,
        "home_home_factor": 1.1,
        "away_away_factor": 0.95,
        "xg_home": 1.55,
        "xg_away": 1.05,
        "xg_source": "stats_api_xg",
        "home_recent_n": 8,
        "away_recent_n": 8,
        "home_position": {"position": 2},
        "away_position": {"position": 9},
        "data_quality": {"score_pct": 92, "full_scope": True},
        "market_odds": {},
        "all_bookmaker_odds": [
            {"bookmaker": "Pinnacle", "home": 1.8, "draw": 3.6, "away": 4.5},
        ],
    }
    engine = BettingEngine({})
    pred = engine.predict_with_confidence(fixture)
    vb = pred.get("value_bets") or {}
    alt = pred.get("value_bets_alt") or {}
    if "home" in vb and "home" in alt:
        assert vb["home"].get("value_dual_agree") is True
        assert alt["home"].get("value_dual_agree") is True


def _minimal_team_stats() -> dict:
    return {"played": 10, "goals_for": 15, "goals_against": 12}


def test_enriched_skips_cache_when_recent_missing():
    from hibs_predictor.data_aggregator import DataAggregator

    stats = _minimal_team_stats()
    cached = {
        "home_recent": [],
        "away_recent": [{"teams": {"home": {"id": 2}, "away": {"id": 3}}, "goals": {"home": 1, "away": 0}}],
        "away_stats": stats,
    }
    assert DataAggregator._enriched_needs_recent_refetch(cached, 10, 20) is True
    assert DataAggregator._enriched_needs_recent_refetch(cached, None, 20) is False
    full = {
        "home_recent": [{"x": 1}],
        "away_recent": [{"x": 2}],
        "home_stats": stats,
        "away_stats": stats,
    }
    assert DataAggregator._enriched_needs_recent_refetch(full, 10, 20) is False


def test_enriched_cache_fresh_within_window():
    from datetime import datetime, timedelta

    from hibs_predictor.data_aggregator import DataAggregator

    stats = _minimal_team_stats()
    recent = {
        "enriched_at": datetime.now().isoformat(),
        "home_recent": [{"x": 1}],
        "away_recent": [{"x": 2}],
        "home_stats": stats,
        "away_stats": stats,
    }
    assert DataAggregator._enriched_cache_fresh(recent, 10, 20) is True
    stale = {
        "enriched_at": (datetime.now() - timedelta(hours=2)).isoformat(),
        "home_recent": [{"x": 1}],
        "away_recent": [{"x": 2}],
        "home_stats": stats,
        "away_stats": stats,
    }
    assert DataAggregator._enriched_cache_fresh(stale, 10, 20, minutes=15) is False


def test_team_recent_mem_dedupes_within_session(monkeypatch):
    from hibs_predictor.data_aggregator import DataAggregator

    calls = {"n": 0}

    class FakeApiSports:
        def fetch_team_last_matches(self, team_id, limit=10):
            calls["n"] += 1
            return [{"fixture": {"id": 1}, "teams": {"home": {"id": team_id}}}]

    agg = DataAggregator()
    agg.clients = {"api_sports": FakeApiSports()}
    agg.cache = type("C", (), {"get": lambda *a, **k: None, "set": lambda *a, **k: None})()

    first = agg._fetch_team_recent_matches(42)
    second = agg._fetch_team_recent_matches(42)
    assert len(first) == 1
    assert first == second
    assert calls["n"] == 1


def test_understat_league_fetch_cached_in_session(monkeypatch):
    from hibs_predictor.scrapers import understat_client as us

    us._league_rows_mem.clear()
    sample = [{"h": {"title": "A"}, "a": {"title": "B"}, "isResult": True, "xG": {"h": 1.1, "a": 0.9}}]
    calls = {"n": 0}

    def fake_api(slug, season_year):
        calls["n"] += 1
        return sample

    monkeypatch.setattr(us, "_fetch_league_dates_api", fake_api)
    monkeypatch.setattr(
        "hibs_predictor.cache.Cache.get",
        lambda self, key, ttl_hours=4.0: None,
    )
    monkeypatch.setattr(
        "hibs_predictor.cache.Cache.set",
        lambda self, key, value, ttl_hours=4.0: None,
    )
    r1 = us.fetch_league_matches("EPL", 2026)
    r2 = us.fetch_league_matches("EPL", 2026)
    assert r1 == sample
    assert r2 == sample
    assert calls["n"] == 1
    us._league_rows_mem.clear()


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
