"""Unit tests for deep enrichment toward HIBS_TARGET_DQ_PCT."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hibs_predictor.data_quality import compute_fixture_data_quality
from hibs_predictor.deep_enrich import (
    DEEP_BAND_MIN,
    analyze_dq_gaps,
    apply_xg_ladder,
    deep_enrich_pass,
    deep_enrich_target_pct,
    fixture_is_today,
    maybe_deep_enrich,
)


def _rich_enriched(**overrides):
    base = {
        "fixture": {"id": 9001},
        "teams": {"home": {"id": 10}, "away": {"id": 20}},
        "home_recent_n": 8,
        "away_recent_n": 8,
        "home_stats": {"played": 20, "goals_for": 30, "goals_against": 25},
        "away_stats": {"played": 20, "goals_for": 28, "goals_against": 22},
        "home_position": {"position": 5},
        "away_position": {"position": 7},
        "xg_home": 1.4,
        "xg_away": 1.2,
        "xg_source": "goals_proxy",
        "odds_available": True,
        "odds_home": 2.1,
        "odds_draw": 3.4,
        "odds_away": 3.2,
        "market_odds": {"btts": {"yes": 1.8}, "totals_2_5": {"over": 1.9}},
        "fixture_injuries": [{"player": "Test"}],
        "supplemental": {"note": "ok"},
    }
    base.update(overrides)
    return base


def test_deep_enrich_target_pct_from_env(monkeypatch):
    monkeypatch.delenv("HIBS_TARGET_DQ_PCT", raising=False)
    monkeypatch.delenv("HIBS_DEEP_ENRICH", raising=False)
    assert deep_enrich_target_pct() == 0.0
    monkeypatch.setenv("HIBS_TARGET_DQ_PCT", "90")
    assert deep_enrich_target_pct() == 90.0


def test_analyze_dq_gaps_lists_weak_xg():
    enriched = _rich_enriched()
    gaps = analyze_dq_gaps(enriched)
    keys = [g["key"] for g in gaps["gaps"]]
    assert "xg" in keys


def test_maybe_deep_enrich_upgrades_xg(monkeypatch):
    monkeypatch.setenv("HIBS_TARGET_DQ_PCT", "90")
    fixture = {
        "fixture": {"id": 9001, "date": "2099-01-01T15:00:00+00:00"},
        "date": "2099-01-01T15:00:00+00:00",
        "teams": {"home": {"id": 10, "name": "Home"}, "away": {"id": 20, "name": "Away"}},
    }
    enriched = _rich_enriched(
        xg_source="unknown",
        xg_home=0.0,
        xg_away=0.0,
        market_odds={},
        fixture_injuries=[],
        supplemental={},
    )
    before = compute_fixture_data_quality(enriched)["score_pct"]
    assert 78 <= before < 90

    aggregator = MagicMock()
    aggregator.cache = MagicMock()
    aggregator.cache._get_cache_path = lambda k: MagicMock(exists=lambda: False)
    aggregator.clients = {"api_sports": MagicMock()}
    aggregator._fetch_expected_goals = MagicMock(return_value=(1.5, 1.3, "api_fixture_xg"))
    aggregator._fetch_team_recent_matches = MagicMock(return_value=[])
    aggregator._fetch_team_stats = MagicMock(return_value={})
    aggregator._fetch_odds_bundle = MagicMock(return_value={})

    with patch(
        "hibs_predictor.scraped_xg.apply_scraped_xg_to_enriched",
        side_effect=lambda f, lc, e: {**e, "xg_source": "understat_xg", "xg_home": 1.5, "xg_away": 1.3},
    ):
        out = maybe_deep_enrich(aggregator, fixture, "EPL", enriched)

    after = compute_fixture_data_quality(out)["score_pct"]
    assert after >= before
    assert out.get("xg_source") == "understat_xg"


def test_apply_xg_ladder_stops_at_target_points():
    aggregator = MagicMock()
    aggregator.cache = MagicMock()
    aggregator.cache._get_cache_path = lambda k: MagicMock(exists=lambda: False)
    aggregator._fetch_expected_goals = MagicMock(return_value=(1.6, 1.4, "api_fixture_xg"))
    fixture = {"fixture": {"id": 42}, "teams": {"home": {"id": 1}, "away": {"id": 2}}}
    enriched = _rich_enriched(xg_source="goals_proxy")
    out = apply_xg_ladder(aggregator, fixture, "EPL", enriched)
    xg_block = next(b for b in compute_fixture_data_quality(out)["blocks"] if b["key"] == "xg")
    assert xg_block["earned"] >= 16.0


def test_fixture_is_today_utc():
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).date().isoformat()
    assert fixture_is_today({"date": f"{today}T18:00:00+00:00"})
    assert not fixture_is_today({"date": "2099-06-01T18:00:00+00:00"})


def test_deep_enrich_pass_respects_max_retries(monkeypatch):
    monkeypatch.setenv("HIBS_DEEP_ENRICH_MAX_RETRIES", "1")
    aggregator = MagicMock()
    aggregator.cache = MagicMock()
    aggregator.cache._get_cache_path = lambda k: MagicMock(exists=lambda: False)
    aggregator.clients = {}
    fixture = {"fixture": {"id": 1}, "teams": {"home": {"id": 1}, "away": {"id": 2}}}
    enriched = _rich_enriched(
        home_recent_n=3,
        away_recent_n=3,
        xg_source="goals_proxy",
        fixture_injuries=[],
    )
    mid = compute_fixture_data_quality(enriched)["score_pct"]
    assert DEEP_BAND_MIN <= mid < 90
    with patch("hibs_predictor.deep_enrich._fill_recent_if_needed") as mock_fill:
        deep_enrich_pass(aggregator, fixture, "EPL", enriched, target_pct=90.0, max_retries=1)
        assert mock_fill.call_count >= 1
