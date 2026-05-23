"""Tests for recent finished-match results (dashboard section)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from hibs_predictor.recent_results import (
    _normalize_api_sports_result,
    _normalize_fdo_result,
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
