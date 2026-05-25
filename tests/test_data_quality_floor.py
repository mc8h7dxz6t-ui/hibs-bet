"""DQ floor for API-rich domestic fixtures (stats + form + odds)."""

from __future__ import annotations

from hibs_predictor.data_quality import (
    _core_api_rich_ready,
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
