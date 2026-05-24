"""Finished-fixture filter, cup detection, and goal scorer parsing."""

from __future__ import annotations

from hibs_predictor.fixture_utils import (
    format_goal_scorers_line,
    goal_scorers_from_events,
    is_cup_competition,
    is_finished_fixture,
)
from hibs_predictor.web import _finalize_fixture_bundle, _upcoming_fixtures


def test_is_cup_competition():
    assert is_cup_competition("FA_CUP")
    assert is_cup_competition("UCL")
    assert is_cup_competition("WORLD_CUP")
    assert not is_cup_competition("EPL")


def test_upcoming_fixtures_drop_finished():
    rows = [
        {"id": 1, "home": "A", "away": "B", "fixture_status": "NS", "date": "2026-05-25T15:00:00Z"},
        {"id": 2, "home": "C", "away": "D", "fixture_status": "FT", "date": "2026-05-24T15:00:00Z"},
        {"id": 3, "home": "E", "away": "F", "fixture_status": "PEN", "date": "2026-05-24T18:00:00Z"},
    ]
    upcoming = _upcoming_fixtures(rows)
    assert len(upcoming) == 1
    assert upcoming[0]["id"] == 1


def test_is_finished_fixture_from_nested_status():
    assert is_finished_fixture({"fixture": {"status": {"short": "AET"}}})
    assert not is_finished_fixture({"fixture": {"status": {"short": "1H"}}})


def test_goal_scorers_from_events():
    events = [
        {"type": "Goal", "detail": "Normal Goal", "player": {"name": "Smith"}, "team": {"name": "Hibs"}, "time": {"elapsed": 12}},
        {"type": "Goal", "detail": "Normal Goal", "player": {"name": "Jones"}, "team": {"name": "Hearts"}, "time": {"elapsed": 55}},
    ]
    scorers = goal_scorers_from_events(events)
    assert len(scorers) == 2
    line = format_goal_scorers_line(scorers)
    assert "Smith" in line and "Jones" in line


def test_finalize_marks_cup_without_table(monkeypatch):
    fixtures = [
        {
            "id": 99,
            "home": "Arsenal",
            "away": "Chelsea",
            "date": "2026-05-25T15:00:00Z",
            "league": "FA_CUP",
            "league_name": "FA Cup",
            "competition_meta": {"api_round": "Semi-finals"},
            "home_last10": [{"result": "W", "score": "2-0"}],
            "away_last10": [{"result": "L", "score": "0-1"}],
            "home_position": {},
            "away_position": {},
            "prediction": {"structured_insight": {}, "line_odds": {}},
        }
    ]

    monkeypatch.setattr("hibs_predictor.web._build_league_tables", lambda *a, **k: [])
    monkeypatch.setattr("hibs_predictor.web._ensure_fixture_data_quality", lambda _rows: None)
    monkeypatch.setattr("hibs_predictor.web._ensure_fixture_pick_menus", lambda _rows: None)

    bundle = _finalize_fixture_bundle(fixtures, attach_live=False)
    fx = bundle["all"][0]
    assert fx.get("is_cup_competition") is True
    assert fx.get("league_table_rows") == []
    assert "Semi" in (fx.get("cup_round_label") or "")
