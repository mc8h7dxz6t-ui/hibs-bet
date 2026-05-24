"""Tests for recent finished-match results (dashboard section)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from hibs_predictor.recent_results import (
    _apply_goal_scorers_from_events,
    _enrich_goal_scorers,
    _normalize_api_sports_result,
    _normalize_fdo_result,
    _results_fetch_events,
    fetch_league_recent_results,
    fetch_recent_results,
    finalize_results_bundle,
    results_days,
    results_window_utc,
)


def test_results_days_default(monkeypatch):
    monkeypatch.delenv("HIBS_RESULTS_DAYS", raising=False)
    assert results_days() == 3


def test_results_days_env(monkeypatch):
    monkeypatch.setenv("HIBS_RESULTS_DAYS", "5")
    assert results_days() == 5


def test_normalize_api_sports_result_finished_with_xg():
    raw = {
        "fixture": {
            "id": 99,
            "date": "2026-05-22T18:00:00+00:00",
            "status": {"short": "FT"},
        },
        "teams": {
            "home": {"id": 1, "name": "Hibs"},
            "away": {"id": 2, "name": "Hearts"},
        },
        "goals": {"home": 2, "away": 1},
        "league": {"name": "Scottish Premiership", "round": "Regular Season - 38"},
        "statistics": [
            {
                "team": {"id": 1},
                "expected_goals": {"total": "1.8"},
            },
            {
                "team": {"id": 2},
                "expected_goals": {"total": "0.9"},
            },
        ],
    }
    row = _normalize_api_sports_result(raw, "SCOTLAND")
    assert row is not None
    assert row["scoreline"] == "2–1"
    assert row["status"] == "FT"
    assert row["has_xg"] is True
    assert row["xg_home"] == 1.8
    assert row["xg_away"] == 0.9


def test_normalize_api_sports_skips_non_finished():
    raw = {
        "fixture": {"id": 1, "date": "2026-05-23T12:00:00+00:00", "status": {"short": "NS"}},
        "teams": {"home": {"id": 1, "name": "A"}, "away": {"id": 2, "name": "B"}},
        "goals": {"home": None, "away": None},
    }
    assert _normalize_api_sports_result(raw, "EPL") is None


def test_normalize_fdo_finished():
    match = {
        "id": 55,
        "utcDate": "2026-05-21T19:00:00Z",
        "status": "FINISHED",
        "homeTeam": {"id": 10, "name": "France"},
        "awayTeam": {"id": 11, "name": "Germany"},
        "score": {"fullTime": {"home": 3, "away": 2}},
        "competition": {"name": "UEFA Nations League"},
    }
    row = _normalize_fdo_result(match, "NATIONS_LEAGUE")
    assert row is not None
    assert row["scoreline"] == "3–2"
    assert row["status"] == "FT"
    assert row["has_xg"] is False


def test_finalize_results_bundle_sorts_newest_first():
    rows = [
        {
            "id": 1,
            "home": "A",
            "away": "B",
            "date": "2026-05-20T15:00:00+00:00",
            "league": "EPL",
            "league_name": "Premier League",
            "scoreline": "1–0",
            "score_home": 1,
            "score_away": 0,
            "status": "FT",
            "has_xg": False,
        },
        {
            "id": 2,
            "home": "C",
            "away": "D",
            "date": "2026-05-22T15:00:00+00:00",
            "league": "SCOTLAND",
            "league_name": "Scottish Premiership",
            "scoreline": "2–2",
            "score_home": 2,
            "score_away": 2,
            "status": "FT",
            "has_xg": False,
        },
    ]
    bundle = finalize_results_bundle(rows)
    assert bundle["total"] == 2
    assert bundle["all"][0]["home"] == "C"
    assert len(bundle["days"]) == 2
    assert bundle["all"][0]["kickoff_time"]


def test_fetch_league_recent_results_uses_cache(monkeypatch):
    monkeypatch.setenv("HIBS_RESULTS_DAYS", "3")
    cache = MagicMock()
    cache.get.return_value = [{"id": 1, "home": "X", "away": "Y", "date": "2026-05-22T12:00:00+00:00"}]
    agg = MagicMock()
    rows = fetch_league_recent_results("EPL", agg, cache=cache)
    assert len(rows) == 1
    agg.clients.__getitem__.assert_not_called()


def test_fetch_recent_results_merges_leagues(monkeypatch):
    monkeypatch.setenv("HIBS_RESULTS_DAYS", "3")
    monkeypatch.setenv("HIBS_RESULTS_FETCH_EVENTS", "0")
    monkeypatch.setattr(
        "hibs_predictor.recent_results.league_codes_for_fetch",
        lambda **_: ["EPL", "SCOTLAND"],
    )

    def fake_league(code, agg, *, cache=None):
        return [
            {
                "id": 1 if code == "EPL" else 2,
                "home": f"{code} Home",
                "away": f"{code} Away",
                "date": "2026-05-22T12:00:00+00:00",
                "league": code,
                "league_name": code,
                "scoreline": "1–0",
                "score_home": 1,
                "score_away": 0,
                "status": "FT",
                "has_xg": False,
            }
        ]

    monkeypatch.setattr("hibs_predictor.recent_results.fetch_league_recent_results", fake_league)
    cache = MagicMock()
    cache.get.return_value = None
    bundle = fetch_recent_results(MagicMock(), cache=cache)
    assert bundle["total"] == 2
    cache.set.assert_called_once()


def test_results_window_three_calendar_days(monkeypatch):
    from hibs_predictor.display_tz import display_timezone

    monkeypatch.setenv("HIBS_RESULTS_DAYS", "3")
    now = datetime(2026, 5, 23, 15, 0, tzinfo=timezone.utc)
    start, end = results_window_utc(now)
    assert end == now
    local_start = start.astimezone(display_timezone()).date()
    assert (now.astimezone(display_timezone()).date() - local_start).days == 2


def test_results_fetch_events_default_on(monkeypatch):
    monkeypatch.delenv("HIBS_RESULTS_FETCH_EVENTS", raising=False)
    assert _results_fetch_events() is True


def test_results_fetch_events_explicit_off(monkeypatch):
    monkeypatch.setenv("HIBS_RESULTS_FETCH_EVENTS", "0")
    assert _results_fetch_events() is False


def test_normalize_api_sports_preserves_embedded_events():
    raw = {
        "fixture": {
            "id": 100,
            "date": "2026-05-22T18:00:00+00:00",
            "status": {"short": "FT"},
        },
        "teams": {
            "home": {"id": 1, "name": "Hibs"},
            "away": {"id": 2, "name": "Hearts"},
        },
        "goals": {"home": 1, "away": 0},
        "events": [
            {
                "type": "Goal",
                "detail": "Normal Goal",
                "player": {"name": "Shaw"},
                "team": {"name": "Hibs"},
                "time": {"elapsed": 33},
            }
        ],
    }
    row = _normalize_api_sports_result(raw, "SCOTLAND")
    assert row is not None
    assert isinstance(row.get("events"), list)
    assert len(row["events"]) == 1


def test_apply_goal_scorers_from_events_mock_json():
    row: dict = {"score_home": 2, "score_away": 1}
    events = [
        {
            "type": "Goal",
            "detail": "Normal Goal",
            "player": {"name": "Shaw"},
            "team": {"name": "Hibs"},
            "time": {"elapsed": 12},
        },
        {
            "type": "Goal",
            "detail": "Normal Goal",
            "player": {"name": "Newell"},
            "team": {"name": "Hibs"},
            "time": {"elapsed": 78},
        },
        {
            "type": "Goal",
            "detail": "Normal Goal",
            "player": {"name": "Shankland"},
            "team": {"name": "Hearts"},
            "time": {"elapsed": 55},
        },
    ]
    assert _apply_goal_scorers_from_events(row, events) is True
    assert "Shaw" in row["goal_scorers_line"]
    assert "Shankland" in row["goal_scorers_line"]


def test_enrich_goal_scorers_uses_cache_and_respects_budget(monkeypatch):
    monkeypatch.setenv("HIBS_RESULTS_FETCH_EVENTS", "1")
    monkeypatch.setenv("HIBS_RESULTS_MAX_EVENT_FETCHES", "1")
    cache = MagicMock()
    cache.get.return_value = None
    client = MagicMock()
    client.rate_limiter.check_rate_limit.return_value = True
    client._get_json.return_value = {
        "response": [
            {
                "type": "Goal",
                "detail": "Normal Goal",
                "player": {"name": "Doku"},
                "team": {"name": "Man City"},
                "time": {"elapsed": 4},
            }
        ]
    }
    agg = MagicMock()
    agg.clients = {"api_sports": client}
    rows = [
        {
            "id": 501,
            "status": "FT",
            "score_home": 2,
            "score_away": 0,
            "home": "Man City",
            "away": "Arsenal",
        },
        {
            "id": 502,
            "status": "FT",
            "score_home": 1,
            "score_away": 1,
            "home": "Liverpool",
            "away": "Chelsea",
        },
    ]
    _enrich_goal_scorers(rows, agg, cache)
    assert client._get_json.call_count == 1
    assert "Doku" in (rows[0].get("goal_scorers_line") or "")
    assert "goal_scorers_line" not in rows[1]


def test_enrich_goal_scorers_skips_when_rate_limited(monkeypatch):
    monkeypatch.setenv("HIBS_RESULTS_FETCH_EVENTS", "1")
    cache = MagicMock()
    cache.get.return_value = None
    client = MagicMock()
    client.rate_limiter.check_rate_limit.return_value = False
    agg = MagicMock()
    agg.clients = {"api_sports": client}
    rows = [
        {"id": 601, "status": "FT", "score_home": 1, "score_away": 0, "home": "A", "away": "B"},
    ]
    _enrich_goal_scorers(rows, agg, cache)
    client._get_json.assert_not_called()
    assert "goal_scorers_line" not in rows[0]


def test_enrich_goal_scorers_skips_zero_goal_draws(monkeypatch):
    monkeypatch.setenv("HIBS_RESULTS_FETCH_EVENTS", "1")
    cache = MagicMock()
    client = MagicMock()
    agg = MagicMock()
    agg.clients = {"api_sports": client}
    rows = [
        {"id": 701, "status": "FT", "score_home": 0, "score_away": 0, "home": "A", "away": "B"},
    ]
    _enrich_goal_scorers(rows, agg, cache)
    client._get_json.assert_not_called()
    cache.get.assert_not_called()
