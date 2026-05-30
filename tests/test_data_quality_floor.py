"""DQ floor for API-rich domestic fixtures (stats + form + odds)."""

from __future__ import annotations

from hibs_predictor.data_quality import (
    _core_api_rich_ready,
    _showpiece_ready,
    compute_fixture_data_quality,
    compute_fixture_data_quality_from_row,
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
        "fixture_injuries": [],
        "supplemental": {},
    }
    base.update(overrides)
    return base


def test_core_api_rich_ready_requires_odds_and_form():
    assert _core_api_rich_ready(_rich_enriched()) is True
    assert _core_api_rich_ready(_rich_enriched(odds_available=False, odds_home=None)) is False
    assert _core_api_rich_ready(_rich_enriched(home_recent_n=2)) is False


def test_domestic_floor_at_88_for_goals_proxy():
    dq = compute_fixture_data_quality(_rich_enriched(xg_source="goals_proxy"))
    assert dq["score_pct"] >= 88.0
    assert dq["weak_fields"] == ["Expected goals"] or dq["weak_fields"] == []


def test_season_xg_not_thin_weak_field():
    dq = compute_fixture_data_quality(
        _rich_enriched(xg_source="api_season_team_xg", scraped_xg_meta={"api_season_xg_measured": True})
    )
    assert dq["score_pct"] >= 88.0
    assert "Expected goals" not in dq["weak_fields"]


def test_slim_row_floor_epl_scotland_shape():
    row = {
        "id": 99,
        "home_id": 1,
        "away_id": 2,
        "home_last10": [{}] * 8,
        "away_last10": [{}] * 8,
        "home_stats": {"played": 30, "goals_for": 40, "goals_against": 30, "api_season_xg_measured": True},
        "away_stats": {"played": 30, "goals_for": 35, "goals_against": 32},
        "home_position": {"position": 3},
        "away_position": {"position": 8},
        "xg_source": "api_season_team_xg",
        "prediction": {
            "bookmaker_odds": {"home": 2.1, "draw": 3.4, "away": 3.2},
            "home_btts_rate": 0.5,
            "away_btts_rate": 0.6,
            "home_over25_rate": 0.5,
            "away_over25_rate": 0.55,
        },
        "market_odds": {"btts": {"yes": 1.8}, "totals_2_5": {"over": 1.9}},
    }
    dq = compute_fixture_data_quality_from_row(row)
    assert dq["score_pct"] >= 88.0


def test_unknown_xg_floors_when_core_rich():
    dq = compute_fixture_data_quality(_rich_enriched(xg_source="unknown", xg_home=0, xg_away=0))
    assert dq["score_pct"] >= 88.0
    assert dq["weak_fields"] == ["Expected goals"]


def test_ucl_showpiece_normalized_without_league_table():
    """FotMob league xG + form: high cup-normalized DQ, not a blind 95%% floor on thin blocks."""
    enriched = _rich_enriched(
        league="UCL",
        xg_source="fotmob_league_xg",
        home_position={},
        away_position={},
        home_recent_n=6,
        away_recent_n=6,
        scraped_xg_meta={"home_n": 8, "away_n": 8},
    )
    assert _showpiece_ready(enriched, league_code="UCL")
    dq = compute_fixture_data_quality(enriched)
    assert dq["score_pct"] >= 90.0
    assert dq["score_pct"] < 95.0
    assert dq.get("premium_scope") is False
    assert dq.get("showpiece_normalized_pct") is not None
    assert "League table" not in dq["weak_fields"]


def test_ucl_premium_95_with_measured_fixture_xg():
    enriched = _rich_enriched(
        league="UCL",
        xg_source="api_statistics_xg",
        home_position={},
        away_position={},
        home_recent_n=8,
        away_recent_n=8,
        market_odds={"btts": {"yes": 1.75}, "totals_2_5": {"over": 1.85}},
    )
    dq = compute_fixture_data_quality(enriched)
    assert dq["score_pct"] >= 95.0
    assert dq.get("premium_scope") is True


def test_coupe_showpiece_floor_domestic_stats_shape():
    enriched = _rich_enriched(
        league="COUPE_DE_FRANCE",
        xg_source="goals_proxy",
        home_position={},
        away_position={},
        competition_meta={"api_round": "2nd Leg"},
        home_recent_n=5,
        away_recent_n=5,
    )
    dq = compute_fixture_data_quality(enriched)
    assert dq["score_pct"] >= 85.0


def test_intl_friendlies_floor_without_book_odds():
    enriched = _rich_enriched(
        league="INTL_FRIENDLIES",
        xg_source="api_season_team_xg",
        scraped_xg_meta={"api_season_xg_measured": True},
        home_position={},
        away_position={},
        home_recent_n=5,
        away_recent_n=5,
        odds_available=False,
        odds_home=None,
        odds_draw=None,
        odds_away=None,
    )
    enriched.pop("odds_home", None)
    enriched.pop("odds_draw", None)
    enriched.pop("odds_away", None)
    dq = compute_fixture_data_quality(enriched)
    assert dq["score_pct"] >= 85.0
    assert "Odds markets" in dq["weak_fields"]


def test_intl_friendlies_floor_90_with_odds_and_measured_xg():
    dq = compute_fixture_data_quality(
        _rich_enriched(
            league="INTL_FRIENDLIES",
            xg_source="api_season_team_xg",
            scraped_xg_meta={"api_season_xg_measured": True},
            home_position={},
            away_position={},
            home_recent_n=5,
            away_recent_n=5,
        )
    )
    assert dq["score_pct"] >= 90.0


def test_norway_calendar_floor_early_season():
    enriched = _rich_enriched(
        league="NORWAY_ELITESERIEN",
        xg_source="fbref_schedule_xg",
        home_recent_n=4,
        away_recent_n=4,
    )
    dq = compute_fixture_data_quality(enriched)
    assert dq["score_pct"] >= 90.0


def test_european_premium_floor_95_la_liga():
    enriched = _rich_enriched(
        league="LA_LIGA",
        xg_source="api_statistics_xg",
        home_recent_n=8,
        away_recent_n=8,
        home_position={"position": 4},
        away_position={"position": 9},
        market_odds={"btts": {"yes": 1.75}, "totals_2_5": {"over": 1.85}},
    )
    dq = compute_fixture_data_quality(enriched)
    assert dq["score_pct"] >= 95.0
    assert dq.get("premium_scope") is True
    assert dq["trust_label"] == "Premium data"


def test_finland_fotmob_domestic_90_early_season():
    enriched = _rich_enriched(
        league="FINLAND_VEIKKAUSLIIGA",
        xg_source="fotmob_league_xg",
        home_recent_n=4,
        away_recent_n=4,
    )
    dq = compute_fixture_data_quality(enriched)
    assert dq["score_pct"] >= 90.0
    assert "Expected goals" not in dq["weak_fields"]


def test_from_row_uses_enrich_recent_n_not_only_last10_len():
    """Bundle finalize must not cliff DQ when last10 is shorter than enrich recency."""
    row = {
        "id": 99,
        "league": "EPL",
        "home_id": 1,
        "away_id": 2,
        "home_recent_n": 8,
        "away_recent_n": 8,
        "home_last10": [{}] * 2,
        "away_last10": [{}] * 2,
        "home_stats": {"played": 30, "goals_for": 40, "goals_against": 30},
        "away_stats": {"played": 30, "goals_for": 35, "goals_against": 32},
        "home_position": {"position": 3},
        "away_position": {"position": 8},
        "xg_source": "api_season_team_xg",
        "scraped_xg_meta": {"api_season_xg_measured": True},
        "prediction": {
            "bookmaker_odds": {"home": 2.1, "draw": 3.4, "away": 3.2},
            "home_btts_rate": 0.5,
            "away_btts_rate": 0.6,
            "home_over25_rate": 0.5,
            "away_over25_rate": 0.55,
        },
        "market_odds": {"btts": {"yes": 1.8}, "totals_2_5": {"over": 1.9}},
    }
    dq = compute_fixture_data_quality_from_row(row)
    assert dq["score_pct"] >= 88.0


def test_merge_stale_fixture_row_preserves_higher_dq():
    from hibs_predictor.web import _merge_stale_fixture_row

    row = {
        "home": "Norway",
        "away": "Finland",
        "home_id": 1,
        "away_id": 2,
        "home_recent_n": 1,
        "away_recent_n": 1,
        "data_quality": {"score_pct": 35.0, "full_scope": False},
    }
    stale = {
        "home": "Norway",
        "away": "Finland",
        "home_id": 1,
        "away_id": 2,
        "home_recent_n": 8,
        "away_recent_n": 8,
        "home_last10": [{}] * 8,
        "away_last10": [{}] * 8,
        "home_stats": {"played": 12, "goals_for": 18, "goals_against": 10},
        "away_stats": {"played": 12, "goals_for": 15, "goals_against": 12},
        "data_quality": {"score_pct": 91.0, "full_scope": True},
    }
    _merge_stale_fixture_row(row, stale)
    assert float(row["data_quality"]["score_pct"]) == 91.0
    assert row["home_recent_n"] == 8
    assert row["home_stats"]["played"] == 12


def test_rerun_prediction_after_stale_merge_restores_probs():
    """After merge restores enrich, re-run model when block was transient (api_rate_guard)."""
    from unittest.mock import patch

    from hibs_predictor.web import (
        _maybe_rerun_prediction_after_stale_merge,
        _merge_stale_fixture_row,
        _slim_row_enrich_fresh,
    )

    row = {
        "home": "Norway",
        "away": "Finland",
        "home_id": 1,
        "away_id": 2,
        "league": "NORWAY_ELITESERIEN",
        "home_recent_n": 1,
        "away_recent_n": 1,
        "xg_home": 0.0,
        "xg_away": 0.0,
        "xg_source": "unknown",
        "prediction": {
            "prediction_unavailable": True,
            "prediction_unavailable_reason": "api_rate_guard",
        },
        "data_quality": {"score_pct": 35.0, "full_scope": False},
    }
    stale = {
        "home": "Norway",
        "away": "Finland",
        "home_id": 1,
        "away_id": 2,
        "home_recent_n": 8,
        "away_recent_n": 8,
        "home_last10": [{}] * 8,
        "away_last10": [{}] * 8,
        "home_stats": {"played": 12, "goals_for": 18, "goals_against": 10},
        "away_stats": {"played": 12, "goals_for": 15, "goals_against": 12},
        "xg_home": 1.4,
        "xg_away": 1.1,
        "xg_source": "goals_proxy",
        "best_odds_1x2": {"home": 2.1, "draw": 3.4, "away": 3.2},
        "market_odds": {"btts": {"yes": 1.8}, "totals_2_5": {"over": 1.9}},
        "data_quality": {"score_pct": 91.0, "full_scope": True},
    }
    _merge_stale_fixture_row(row, stale)
    assert _slim_row_enrich_fresh(row)

    mock_pred = {
        "home_win_prob": 0.42,
        "draw_prob": 0.28,
        "away_win_prob": 0.30,
        "probabilities": {"home": 0.42, "draw": 0.28, "away": 0.30},
        "bookmaker_odds": {"home": 2.1, "draw": 3.4, "away": 3.2},
    }
    with patch("hibs_predictor.web.betting_engine.predict_with_confidence", return_value=mock_pred):
        assert _maybe_rerun_prediction_after_stale_merge(row) is True

    assert not row["prediction"].get("prediction_unavailable")
    assert row["prediction"].get("home_win_prob") == 0.42
    assert float(row["data_quality"]["score_pct"]) >= 48.0


def test_finalize_ucl_rich_row_stays_above_90():
    """Regression: bundle finalize must not cliff UCL showpiece rows with stored premium DQ."""
    from hibs_predictor.web import _finalize_fixture_bundle

    row = {
        "id": 900100,
        "home": "Paris Saint Germain",
        "away": "Inter",
        "home_id": 85,
        "away_id": 505,
        "date": "2026-05-31T19:00:00+00:00",
        "kickoff_sort": "2026-05-31T19:00:00+00:00",
        "league": "UCL",
        "home_recent_n": 8,
        "away_recent_n": 8,
        "home_last10": [{}] * 8,
        "away_last10": [{}] * 8,
        "home_stats": {"played": 12, "goals_for": 22, "goals_against": 8},
        "away_stats": {"played": 12, "goals_for": 18, "goals_against": 11},
        "home_position": {},
        "away_position": {},
        "xg_source": "api_statistics_xg",
        "scraped_xg_meta": {"home_n": 8, "away_n": 8},
        "prediction": {
            "bookmaker_odds": {"home": 2.05, "draw": 3.5, "away": 3.4},
            "home_btts_rate": 0.55,
            "away_btts_rate": 0.5,
            "home_over25_rate": 0.6,
            "away_over25_rate": 0.55,
        },
        "market_odds": {"btts": {"yes": 1.75}, "totals_2_5": {"over": 1.85}},
        "data_quality": {"score_pct": 97.0, "full_scope": True, "premium_scope": True},
    }
    bundle = _finalize_fixture_bundle([row], include_domestic=False)
    ucl = next(r for r in bundle["all"] if r.get("league") == "UCL")
    assert float(ucl["data_quality"]["score_pct"]) >= 90.0


def test_finalize_ucl_rescores_thin_cached_score_when_row_is_rich():
    from hibs_predictor.web import _finalize_fixture_bundle

    row = {
        "id": 900101,
        "home": "Liverpool",
        "away": "Barcelona",
        "home_id": 40,
        "away_id": 529,
        "date": "2026-05-31T19:00:00+00:00",
        "kickoff_sort": "2026-05-31T19:00:00+00:00",
        "league": "UCL",
        "home_recent_n": 8,
        "away_recent_n": 8,
        "home_last10": [{}] * 8,
        "away_last10": [{}] * 8,
        "home_stats": {"played": 12, "goals_for": 22, "goals_against": 8, "api_season_xg_measured": True},
        "away_stats": {"played": 12, "goals_for": 18, "goals_against": 11},
        "home_position": {},
        "away_position": {},
        "xg_source": "api_statistics_xg",
        "scraped_xg_meta": {"home_n": 8, "away_n": 8},
        "prediction": {
            "bookmaker_odds": {"home": 2.05, "draw": 3.5, "away": 3.4},
            "home_btts_rate": 0.55,
            "away_btts_rate": 0.5,
            "home_over25_rate": 0.6,
            "away_over25_rate": 0.55,
        },
        "market_odds": {"btts": {"yes": 1.75}, "totals_2_5": {"over": 1.85}},
        "data_quality": {"score_pct": 42.0, "full_scope": False},
    }
    bundle = _finalize_fixture_bundle([row], include_domestic=False)
    ucl = next(r for r in bundle["all"] if r.get("league") == "UCL")
    assert float(ucl["data_quality"]["score_pct"]) >= 90.0


def test_ensure_dq_never_downgrades_existing_score():
    from hibs_predictor.web import _ensure_fixture_data_quality

    rows = [
        {
            "home": "Liverpool",
            "away": "Arsenal",
            "league": "EPL",
            "data_quality": {"score_pct": 92.0, "full_scope": True},
            "home_id": 1,
            "away_id": 2,
            "home_last10": [{}],
            "away_last10": [{}],
        }
    ]
    _ensure_fixture_data_quality(rows)
    assert float(rows[0]["data_quality"]["score_pct"]) == 92.0


def test_ensure_dq_backfills_missing_only():
    from hibs_predictor.web import _ensure_fixture_data_quality

    rows = [
        {
            "home": "Morocco",
            "away": "Burundi",
            "league": "INTL_FRIENDLIES",
            "home_id": 1,
            "away_id": 2,
            "home_recent_n": 6,
            "away_recent_n": 6,
            "home_last10": [{}] * 6,
            "away_last10": [{}] * 6,
            "home_stats": {"played": 8, "goals_for": 12, "goals_against": 9},
            "away_stats": {"played": 8, "goals_for": 10, "goals_against": 11},
            "xg_source": "api_season_team_xg",
            "scraped_xg_meta": {"api_season_xg_measured": True},
            "prediction": {"bookmaker_odds": {"home": 2.0, "draw": 3.2, "away": 3.6}},
            "market_odds": {"btts": {"yes": 1.8}, "totals_2_5": {"over": 1.9}},
        }
    ]
    _ensure_fixture_data_quality(rows)
    assert float(rows[0]["data_quality"]["score_pct"]) >= 85.0


def test_rerun_prediction_preserves_higher_dq():
    """Prediction rerun after stale merge must not downgrade an existing premium DQ score."""
    from unittest.mock import patch

    from hibs_predictor.web import (
        _maybe_rerun_prediction_after_stale_merge,
        _merge_stale_fixture_row,
        _slim_row_enrich_fresh,
    )

    row = {
        "home": "Norway",
        "away": "Finland",
        "home_id": 1,
        "away_id": 2,
        "league": "NORWAY_ELITESERIEN",
        "home_recent_n": 8,
        "away_recent_n": 8,
        "home_last10": [{}] * 8,
        "away_last10": [{}] * 8,
        "home_stats": {"played": 12, "goals_for": 18, "goals_against": 10},
        "away_stats": {"played": 12, "goals_for": 15, "goals_against": 12},
        "xg_home": 1.4,
        "xg_away": 1.1,
        "xg_source": "goals_proxy",
        "best_odds_1x2": {"home": 2.1, "draw": 3.4, "away": 3.2},
        "market_odds": {"btts": {"yes": 1.8}, "totals_2_5": {"over": 1.9}},
        "prediction": {
            "prediction_unavailable": True,
            "prediction_unavailable_reason": "api_rate_guard",
        },
        "data_quality": {"score_pct": 91.0, "full_scope": True},
    }
    stale = dict(row)
    stale["prediction"] = {
        "home_win_prob": 0.42,
        "bookmaker_odds": {"home": 2.1, "draw": 3.4, "away": 3.2},
    }
    _merge_stale_fixture_row(row, stale)
    assert _slim_row_enrich_fresh(row)

    mock_pred = {
        "home_win_prob": 0.42,
        "draw_prob": 0.28,
        "away_win_prob": 0.30,
        "probabilities": {"home": 0.42, "draw": 0.28, "away": 0.30},
        "bookmaker_odds": {"home": 2.1, "draw": 3.4, "away": 3.2},
    }
    with patch("hibs_predictor.web.betting_engine.predict_with_confidence", return_value=mock_pred):
        assert _maybe_rerun_prediction_after_stale_merge(row) is True

    assert float(row["data_quality"]["score_pct"]) >= 91.0


def test_world_cup_flagship_floor_95():
    enriched = _rich_enriched(
        league="WORLD_CUP",
        xg_source="api_statistics_xg",
        home_position={},
        away_position={},
        home_recent_n=6,
        away_recent_n=6,
        competition_meta={"api_round": "Group Stage - 1"},
    )
    dq = compute_fixture_data_quality(enriched)
    assert dq["score_pct"] >= 95.0
    assert dq["trust_label"] == "Flagship data"


def test_ucl_semi_final_does_not_get_flagship_floor():
    enriched = _rich_enriched(
        league="UCL",
        xg_source="fotmob_league_xg",
        home_position={},
        away_position={},
        home_recent_n=6,
        away_recent_n=6,
        competition_meta={"api_round": "Semi-finals"},
    )
    dq = compute_fixture_data_quality(enriched)
    assert dq["score_pct"] < 95.0


def test_ucl_final_flagship_floor_95():
    enriched = _rich_enriched(
        league="UCL",
        xg_source="api_statistics_xg",
        home_position={},
        away_position={},
        home_recent_n=8,
        away_recent_n=8,
        competition_meta={"api_round": "Final"},
        market_odds={"btts": {"yes": 1.75}, "totals_2_5": {"over": 1.85}},
    )
    dq = compute_fixture_data_quality(enriched)
    assert dq["score_pct"] >= 95.0


def test_friendlies_floor_85_without_odds():
    enriched = _rich_enriched(
        league="INTL_FRIENDLIES",
        xg_source="api_season_team_xg",
        scraped_xg_meta={"api_season_xg_measured": True},
        home_position={},
        away_position={},
        odds_available=False,
        odds_home=None,
        odds_draw=None,
        odds_away=None,
        home_recent_n=4,
        away_recent_n=4,
    )
    dq = compute_fixture_data_quality(enriched)
    assert dq["score_pct"] >= 85.0
    assert dq["score_pct"] < 95.0


def test_dq_floor_constants_unchanged_for_regression_guard():
    """Hardening must not silently lower earned domestic / showpiece floors."""
    from hibs_predictor import data_quality as dq_mod

    assert dq_mod._CORE_DQ_FLOOR >= 88.0
    assert dq_mod._INTL_DQ_FLOOR >= 85.0
    assert dq_mod._PREMIUM_DQ_FLOOR >= 95.0


def test_from_row_ucl_showpiece_floor_with_league():
    row = {
        "id": 100,
        "league": "UCL",
        "home_id": 1,
        "away_id": 2,
        "home_recent_n": 6,
        "away_recent_n": 6,
        "home_last10": [{}] * 6,
        "away_last10": [{}] * 6,
        "home_stats": {"played": 12, "goals_for": 18, "goals_against": 10},
        "away_stats": {"played": 12, "goals_for": 15, "goals_against": 12},
        "home_position": {},
        "away_position": {},
        "xg_source": "fotmob_league_xg",
        "scraped_xg_meta": {"home_n": 8, "away_n": 8},
        "prediction": {
            "bookmaker_odds": {"home": 2.1, "draw": 3.4, "away": 3.2},
        },
        "market_odds": {"btts": {"yes": 1.8}, "totals_2_5": {"over": 1.9}},
    }
    dq = compute_fixture_data_quality_from_row(row)
    assert dq["score_pct"] >= 85.0
    assert "League table" not in dq["weak_fields"]
