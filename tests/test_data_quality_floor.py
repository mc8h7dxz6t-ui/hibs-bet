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


def test_ucl_showpiece_floor_without_league_table():
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
    assert dq["score_pct"] >= 95.0
    assert dq.get("premium_scope") is True
    assert "League table" not in dq["weak_fields"]


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
