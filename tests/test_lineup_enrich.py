"""Tests for Phase 2 lineup enrichment (API-Football fixtures/lineups)."""

from datetime import datetime, timedelta, timezone

from hibs_predictor.lineup_enrich import (
    apply_lineup_fields,
    lineup_confidence_multiplier,
    lineup_fetch_enabled,
    parse_api_lineups,
    should_fetch_lineups,
    top_scorers_out_of_xi,
)
from hibs_predictor.match_insight import build_player_insight_block, build_structured_insight


def _sample_api_lineups():
    return [
        {
            "team": {"id": 10, "name": "Hibs"},
            "formation": "4-2-3-1",
            "startXI": [
                {"player": {"id": i, "name": f"Home Player {i}", "number": i, "pos": "M"}}
                for i in range(1, 12)
            ],
        },
        {
            "team": {"id": 20, "name": "Hearts"},
            "formation": "4-4-2",
            "startXI": [
                {"player": {"id": 100 + i, "name": f"Away Player {i}", "number": i, "pos": "M"}}
                for i in range(1, 12)
            ],
        },
    ]


def test_parse_api_lineups_confirmed():
    parsed = parse_api_lineups(
        _sample_api_lineups(),
        home_id=10,
        away_id=20,
        home_name="Hibernian",
        away_name="Hearts",
    )
    assert parsed["lineup_confirmed"] is True
    assert len(parsed["fixture_lineups"]["home"]["start_xi"]) == 11
    assert parsed["fixture_lineups"]["home"]["formation"] == "4-2-3-1"


def test_apply_lineup_fields_flags_scorer_out_of_xi():
    row = {
        "home": "Hibs",
        "away": "Hearts",
        "home_id": 10,
        "away_id": 20,
        "home_top_scorers": [
            {"name": "Striker One", "goals": 14},
            {"name": "Home Player 1", "goals": 8},
        ],
        "away_top_scorers": [{"name": "Away Player 1", "goals": 9}],
        "fixture_injuries": [
            {"team": {"id": 10}, "type": "Missing", "player": {"name": "Striker One"}},
        ],
    }
    apply_lineup_fields(row, raw_lineups=_sample_api_lineups())
    assert row["lineup_confirmed"] is True
    out = row["lineup_meta"]["home_scorers_out_of_xi"]
    assert len(out) == 1
    assert out[0]["name"] == "Striker One"
    assert out[0]["on_injury_feed"] is True


def test_top_scorers_out_of_xi_no_guess_without_xi():
    absent = top_scorers_out_of_xi(
        [{"name": "A", "goals": 10}],
        set(),
        injuries=[],
        side="home",
        home_name="H",
        away_name="A",
        home_id=1,
        away_id=2,
    )
    assert absent == []


def test_should_fetch_lineups_pre_kickoff_only(monkeypatch):
    monkeypatch.delenv("HIBS_SKIP_API_LINEUPS", raising=False)
    monkeypatch.setenv("HIBS_ENABLE_LINEUP_FETCH", "1")
    kick = datetime.now(timezone.utc) + timedelta(hours=2)
    row = {"date": kick.isoformat()}
    assert should_fetch_lineups(row) is True
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    assert should_fetch_lineups({"date": past.isoformat()}) is False


def test_lineup_fetch_disabled_by_skip(monkeypatch):
    monkeypatch.setenv("HIBS_SKIP_API_LINEUPS", "1")
    assert lineup_fetch_enabled() is False


def test_lineup_confidence_penalty_near_kickoff(monkeypatch):
    monkeypatch.setenv("HIBS_LINEUP_CONFIDENCE_PENALTY", "1")
    monkeypatch.setenv("HIBS_LINEUP_CONFIDENCE_FLOOR", "0.94")
    kick = datetime.now(timezone.utc) + timedelta(minutes=45)
    fixture = {"date": kick.isoformat(), "lineup_confirmed": False}
    assert lineup_confidence_multiplier(fixture) == 0.94
    fixture["lineup_confirmed"] = True
    assert lineup_confidence_multiplier(fixture) == 1.0


def test_build_player_insight_includes_out_of_xi():
    fixture = {
        "home_top_scorers": [{"name": "Striker One", "goals": 14}],
        "away_top_scorers": [],
        "lineup_confirmed": True,
        "fixture_lineups": {"home": {"start_xi": [{"name": "Other"}]}},
        "lineup_meta": {
            "home_scorers_out_of_xi": [{"name": "Striker One", "goals": 14, "on_injury_feed": True}],
        },
    }
    block = build_player_insight_block(fixture)
    assert block["home_scorers_out_of_xi"][0]["name"] == "Striker One"


def test_structured_insight_lineup_absence_bullet():
    kick = datetime.now(timezone.utc) + timedelta(minutes=30)
    fixture = {
        "home": "Hibs",
        "away": "Hearts",
        "date": kick.isoformat(),
        "league": "EPL",
        "home_recent_n": 5,
        "away_recent_n": 5,
        "lineup_confirmed": True,
        "home_top_scorers": [{"name": "Striker One", "goals": 12}],
        "lineup_meta": {
            "home_scorers_out_of_xi": [{"name": "Striker One", "goals": 12, "on_injury_feed": True}],
        },
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
    assert "not in confirmed XI" in joined
