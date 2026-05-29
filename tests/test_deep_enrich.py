"""Unit tests for deep enrichment toward HIBS_TARGET_DQ_PCT."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hibs_predictor.data_quality import compute_fixture_data_quality
from hibs_predictor.deep_enrich import (
    DEEP_BAND_MIN,
    SHOWPIECE_DEEP_TARGET,
    analyze_dq_gaps,
    apply_xg_ladder,
    deep_band_min,
    deep_enrich_applies_to_fixture,
    deep_enrich_pass,
    deep_enrich_plan,
    deep_enrich_rescue_low_enabled,
    deep_enrich_target_pct,
    deep_enrich_today_only,
    dev_full_dq_enabled,
    fixture_is_today,
    is_showpiece_league,
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
    monkeypatch.delenv("HIBS_DEEP_ENRICH_RESCUE_LOW", raising=False)
    monkeypatch.delenv("HIBS_DEV_FULL_DQ", raising=False)
    assert deep_enrich_target_pct() == 0.0
    monkeypatch.setenv("HIBS_TARGET_DQ_PCT", "90")
    assert deep_enrich_target_pct() == 90.0
    assert deep_enrich_target_pct("INTL_FRIENDLIES") == 86.0
    assert deep_enrich_target_pct("WORLD_CUP") == SHOWPIECE_DEEP_TARGET
    monkeypatch.delenv("HIBS_TARGET_DQ_PCT", raising=False)
    monkeypatch.setenv("HIBS_DEEP_ENRICH", "1")
    assert deep_enrich_target_pct("UECL") == SHOWPIECE_DEEP_TARGET


def test_showpiece_deep_band_allows_rescue_from_thin_scores(monkeypatch):
    monkeypatch.delenv("HIBS_DEEP_ENRICH_RESCUE_LOW", raising=False)
    monkeypatch.delenv("HIBS_DEV_FULL_DQ", raising=False)
    assert is_showpiece_league("UECL")
    assert deep_band_min("UECL") == 0.0
    assert deep_band_min("EPL") == DEEP_BAND_MIN


def test_rescue_low_allows_deep_plan_for_thin_epl(monkeypatch):
    monkeypatch.setenv("HIBS_TARGET_DQ_PCT", "90")
    monkeypatch.setenv("HIBS_DEEP_ENRICH_RESCUE_LOW", "1")
    monkeypatch.delenv("HIBS_DEV_FULL_DQ", raising=False)
    assert deep_enrich_rescue_low_enabled() is True
    assert deep_band_min("EPL") == 0.0
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).date().isoformat()
    fixture = {"date": f"{today}T18:00:00+00:00"}
    thin = {
        "home_recent_n": 0,
        "away_recent_n": 0,
        "home_stats": {},
        "away_stats": {},
        "odds_available": False,
    }
    thin["data_quality"] = compute_fixture_data_quality(thin)
    assert float(thin["data_quality"]["score_pct"]) < DEEP_BAND_MIN
    assert deep_enrich_plan(fixture, "EPL", thin) is not None


def test_dev_full_dq_disables_today_only_and_sets_target(monkeypatch):
    monkeypatch.setenv("HIBS_DEV_FULL_DQ", "1")
    monkeypatch.delenv("HIBS_TARGET_DQ_PCT", raising=False)
    monkeypatch.delenv("HIBS_DEEP_ENRICH_TODAY_ONLY", raising=False)
    assert dev_full_dq_enabled() is True
    assert deep_enrich_today_only() is False
    assert deep_enrich_target_pct("EPL") == 90.0
    from datetime import datetime, timedelta, timezone

    soon = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    fixture = {"date": soon}
    assert deep_enrich_applies_to_fixture(fixture) is True


def test_deep_enrich_today_only_skips_future_kickoff(monkeypatch):
    monkeypatch.delenv("HIBS_DEV_FULL_DQ", raising=False)
    monkeypatch.delenv("HIBS_DEEP_ENRICH_RESCUE_LOW", raising=False)
    monkeypatch.setenv("HIBS_TARGET_DQ_PCT", "90")
    monkeypatch.setenv("HIBS_DEEP_ENRICH_TODAY_ONLY", "1")
    assert deep_enrich_today_only() is True
    fixture = {"fixture": {"id": 1, "date": "2099-06-01T20:00:00+00:00"}, "date": "2099-06-01T20:00:00+00:00"}
    enriched = {
        "teams": {"home": {"id": 1}, "away": {"id": 2}},
        "home_recent_n": 8,
        "away_recent_n": 8,
        "home_stats": {"played": 10, "goals_for": 10, "goals_against": 8},
        "away_stats": {"played": 10, "goals_for": 9, "goals_against": 9},
        "odds_available": True,
        "odds_home": 2.0,
        "odds_draw": 3.2,
        "odds_away": 3.5,
        "data_quality": {"score_pct": 82.0},
    }
    assert deep_enrich_plan(fixture, "EPL", enriched) is None
    aggregator = MagicMock()
    with patch("hibs_predictor.deep_enrich.deep_enrich_pass") as mock_pass:
        maybe_deep_enrich(aggregator, fixture, "EPL", enriched)
        mock_pass.assert_not_called()


def test_deep_enrich_plan_none_when_already_at_target(monkeypatch):
    monkeypatch.setenv("HIBS_TARGET_DQ_PCT", "90")
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).date().isoformat()
    fixture = {"date": f"{today}T18:00:00+00:00"}
    enriched = _rich_enriched()
    assert deep_enrich_plan(fixture, "EPL", enriched) is None


def test_maybe_deep_enrich_rescues_thin_uecl(monkeypatch):
    monkeypatch.delenv("HIBS_DEEP_ENRICH", raising=False)
    monkeypatch.delenv("HIBS_TARGET_DQ_PCT", raising=False)
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).date().isoformat()
    fixture = {
        "fixture": {"id": 848001, "date": f"{today}T20:00:00+00:00"},
        "date": f"{today}T20:00:00+00:00",
        "teams": {"home": {"id": 10, "name": "Home"}, "away": {"id": 20, "name": "Away"}},
    }
    enriched = {
        "fixture": {"id": 848001},
        "teams": {"home": {"id": 10}, "away": {"id": 20}},
        "league": "UECL",
        "home_recent_n": 0,
        "away_recent_n": 0,
        "home_stats": {},
        "away_stats": {},
        "odds_available": False,
        "market_odds": {},
    }
    before = compute_fixture_data_quality(enriched)["score_pct"]
    assert before < DEEP_BAND_MIN

    aggregator = MagicMock()
    aggregator.cache = MagicMock()
    aggregator.cache._get_cache_path = lambda k: MagicMock(exists=lambda: False)
    aggregator.clients = {"api_sports": MagicMock()}

    with patch("hibs_predictor.deep_enrich._fill_recent_if_needed") as mock_recent:
        with patch("hibs_predictor.deep_enrich._fill_odds_if_needed") as mock_odds:
            maybe_deep_enrich(aggregator, fixture, "UECL", enriched)
    assert mock_recent.call_count >= 1
    assert mock_odds.call_count >= 1


def test_analyze_dq_gaps_lists_weak_xg():
    enriched = _rich_enriched()
    gaps = analyze_dq_gaps(enriched)
    keys = [g["key"] for g in gaps["gaps"]]
    assert "xg" in keys


def test_maybe_deep_enrich_upgrades_xg(monkeypatch):
    from datetime import datetime, timezone

    monkeypatch.setenv("HIBS_TARGET_DQ_PCT", "90")
    monkeypatch.delenv("HIBS_DEEP_ENRICH_TODAY_ONLY", raising=False)
    today = datetime.now(timezone.utc).date().isoformat()
    fixture = {
        "fixture": {"id": 9001, "date": f"{today}T15:00:00+00:00"},
        "date": f"{today}T15:00:00+00:00",
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


def test_friendlies_max_data_deep_enrich_uses_fetch_window(monkeypatch):
    monkeypatch.setenv("HIBS_FRIENDLIES_MAX_DATA", "1")
    monkeypatch.setenv("HIBS_FRIENDLIES_FETCH_DAYS", "14")
    monkeypatch.setenv("HIBS_FRIENDLIES_FOCUS_START", "2026-05-20")
    monkeypatch.setenv("HIBS_TARGET_DQ_PCT", "90")
    monkeypatch.setenv("HIBS_DEEP_ENRICH_TODAY_ONLY", "1")
    monkeypatch.setenv("HIBS_DEEP_ENRICH_WINDOW_DAYS", "5")
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: __import__("datetime").date(2026, 5, 28),
    )
    kick = "2026-06-05T18:00:00+00:00"
    fixture = {"fixture": {"id": 1, "date": kick}, "date": kick}
    assert deep_enrich_applies_to_fixture(fixture, "INTL_FRIENDLIES") is True
    far_fixture = {"fixture": {"id": 2, "date": "2026-06-20T18:00:00+00:00"}, "date": "2026-06-20T18:00:00+00:00"}
    assert deep_enrich_applies_to_fixture(far_fixture, "INTL_FRIENDLIES") is False


def test_friendlies_max_data_retries_use_showpiece_default(monkeypatch):
    monkeypatch.setenv("HIBS_FRIENDLIES_MAX_DATA", "1")
    monkeypatch.setenv("HIBS_FRIENDLIES_FOCUS_START", "2026-05-20")
    monkeypatch.delenv("HIBS_DEEP_ENRICH_MAX_RETRIES", raising=False)
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: __import__("datetime").date(2026, 5, 28),
    )
    from hibs_predictor.deep_enrich import deep_enrich_max_retries

    assert deep_enrich_max_retries("INTL_FRIENDLIES") == 3


def test_apply_friendlies_supplemental_rescue_runs_thin_data(monkeypatch):
    monkeypatch.setenv("HIBS_FRIENDLIES_MAX_DATA", "1")
    monkeypatch.setenv("HIBS_FRIENDLIES_FOCUS_START", "2026-05-20")
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: __import__("datetime").date(2026, 5, 28),
    )
    from hibs_predictor.deep_enrich import _apply_friendlies_supplemental_rescue

    aggregator = MagicMock()
    aggregator.clients = {"api_sports": MagicMock()}
    fixture = {
        "fixture": {"id": 42},
        "teams": {"home": {"id": 1, "name": "Scotland"}, "away": {"id": 2, "name": "Wales"}},
    }
    enriched = {"teams": fixture["teams"], "home_recent_n": 0, "away_recent_n": 0}
    with patch("hibs_predictor.scrapers.thin_data_rescue.apply_thin_data_rescue") as mock_rescue:
        mock_rescue.return_value = {**enriched, "thin_data_rescue": {"applied": ["home_recent"]}}
        with patch("hibs_predictor.scrapers.supplemental.collect_supplemental", return_value={"fotmob_xg": {}}):
            _apply_friendlies_supplemental_rescue(aggregator, enriched, fixture, "INTL_FRIENDLIES")
    mock_rescue.assert_called_once()
    assert mock_rescue.call_args.kwargs.get("force") is True
