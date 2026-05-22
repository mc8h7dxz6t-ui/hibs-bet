"""Tests for injury → attack availability (Phase 1)."""

from hibs_predictor.team_news_enrich import apply_team_news_fields, compute_attack_availability


def test_compute_attack_availability_sides():
    injuries = [
        {
            "team": {"id": 1, "name": "Hibs"},
            "player": {"name": "A"},
            "type": "Missing",
        },
        {
            "team": {"id": 2, "name": "Hearts"},
            "player": {"name": "B"},
            "type": "Doubtful",
        },
    ]
    h, a, meta = compute_attack_availability(
        injuries,
        home_name="Hibernian",
        away_name="Hearts",
        home_id=1,
        away_id=2,
    )
    assert h < 1.0
    assert a < 1.0
    assert meta["home_absences"] == 1
    assert meta["away_absences"] == 1


def test_apply_team_news_fields_on_fixture():
    row = {
        "home": "Hibs",
        "away": "Hearts",
        "home_id": 10,
        "away_id": 20,
        "fixture_injuries": [
            {"team": {"id": 10}, "type": "Missing", "player": {"name": "X"}},
        ],
    }
    apply_team_news_fields(row)
    assert 0.5 <= row["attack_availability_home"] <= 1.0
    assert row["attack_availability_away"] == 1.0


def test_structured_insight_injury_rationale_line():
    from hibs_predictor.match_insight import build_structured_insight

    fixture = {
        "home": "Hibs",
        "away": "Hearts",
        "league": "EPL",
        "home_recent_n": 5,
        "away_recent_n": 5,
        "team_news_meta": {"home_absences": 2, "away_absences": 0},
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
    assert "Squad news" in joined
