"""Tests for player / lineup display helpers."""

from hibs_predictor.lineup_enrich import apply_lineup_fields
from hibs_predictor.match_insight import build_player_insight_block, build_structured_insight
from hibs_predictor.team_news_enrich import apply_team_news_fields, top_scorers_listed_absent


def test_top_scorers_listed_absent_name_match():
    injuries = [
        {
            "team": {"id": 1, "name": "Hibs"},
            "player": {"name": "John Smith"},
            "type": "Missing",
        },
    ]
    scorers = [{"name": "John Smith", "goals": 14}, {"name": "Other Player", "goals": 5}]
    absent = top_scorers_listed_absent(
        scorers,
        injuries,
        side="home",
        home_name="Hibernian",
        away_name="Hearts",
        home_id=1,
        away_id=2,
    )
    assert len(absent) == 1
    assert absent[0]["name"] == "John Smith"
    assert absent[0]["goals"] == 14


def test_apply_team_news_fields_cross_refs_scorers():
    row = {
        "home": "Hibs",
        "away": "Hearts",
        "home_id": 10,
        "away_id": 20,
        "home_top_scorers": [{"name": "Striker One", "goals": 12}],
        "away_top_scorers": [],
        "fixture_injuries": [
            {"team": {"id": 10}, "type": "Missing", "player": {"name": "Striker One"}},
        ],
    }
    apply_team_news_fields(row)
    assert row["team_news_meta"]["home_scorers_absent"][0]["name"] == "Striker One"


def test_build_player_insight_block_includes_absent():
    fixture = {
        "home_top_scorers": [{"name": "A", "goals": 10}],
        "away_top_scorers": [],
        "team_news_meta": {"home_scorers_absent": [{"name": "A", "goals": 10}]},
    }
    block = build_player_insight_block(fixture)
    assert block is not None
    assert block["home_scorers_absent"][0]["name"] == "A"


def test_structured_insight_top_scorer_absence_bullet():
    fixture = {
        "home": "Hibs",
        "away": "Hearts",
        "league": "EPL",
        "home_recent_n": 5,
        "away_recent_n": 5,
        "home_top_scorers": [{"name": "Striker One", "goals": 12}],
        "team_news_meta": {
            "home_absences": 1,
            "away_absences": 0,
            "home_scorers_absent": [{"name": "Striker One", "goals": 12}],
        },
        "attack_availability_home": 0.88,
        "attack_availability_away": 1.0,
        "data_quality": {"score_pct": 85},
    }
    prediction = {
        "home": "Hibs",
        "away": "Hearts",
        "probabilities": {"home": 0.45, "draw": 0.28, "away": 0.27},
        "probabilities_pct": {"home": 45, "draw": 28, "away": 27},
        "btts_probability": 0.55,
        "over25_probability_pct": 52,
        "expected_goals_home": 1.4,
        "expected_goals_away": 1.1,
    }
    card = build_structured_insight(fixture, prediction)
    joined = " ".join(card.get("rationale") or [])
    assert "Top scorer Striker One" in joined
    assert "API absence feed" in joined


def test_apply_lineup_fields_stub():
    row: dict = {}
    apply_lineup_fields(row)
    assert row["lineup_confirmed"] is False
    assert row["fixture_lineups"] is None
