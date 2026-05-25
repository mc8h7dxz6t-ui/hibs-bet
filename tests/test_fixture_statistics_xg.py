"""API-Football fixtures/statistics xG path (budgeted per refresh)."""

from unittest.mock import MagicMock

import pytest

from hibs_predictor.fixture_statistics_xg import (
    fetch_fixture_statistics_xg,
    needs_statistics_xg_fetch,
    reset_statistics_xg_budget,
)


def test_needs_statistics_xg_fetch():
    assert needs_statistics_xg_fetch("goals_proxy") is True
    assert needs_statistics_xg_fetch("api_fixture_xg") is False
    assert needs_statistics_xg_fetch("api_statistics_xg") is False
    assert needs_statistics_xg_fetch("api_season_team_xg") is False
    assert needs_statistics_xg_fetch("team_season_xg") is False


def test_fetch_fixture_statistics_xg_parses_and_caches(monkeypatch):
    monkeypatch.setenv("HIBS_FETCH_FIXTURE_STATISTICS_XG", "1")
    monkeypatch.setenv("HIBS_FETCH_FIXTURE_STATISTICS_XG_MAX", "2")
    reset_statistics_xg_budget()

    stats_response = [
        {
            "team": {"id": 10, "name": "Home FC"},
            "statistics": [{"type": "Expected Goals", "value": "1.55"}],
        },
        {
            "team": {"id": 20, "name": "Away FC"},
            "statistics": [{"type": "Expected Goals", "value": "0.92"}],
        },
    ]
    api = MagicMock()
    api.fetch_fixture_statistics.return_value = stats_response
    cache = MagicMock()
    cache.get.return_value = None

    hit = fetch_fixture_statistics_xg(
        api,
        cache,
        999,
        home_team_id=10,
        away_team_id=20,
        current_source="goals_proxy",
    )
    assert hit == (1.55, 0.92, "api_statistics_xg")
    cache.set.assert_called_once()
    api.fetch_fixture_statistics.assert_called_once_with(999, ttl_hours=12.0)


def test_fetch_respects_per_refresh_budget(monkeypatch):
    monkeypatch.setenv("HIBS_FETCH_FIXTURE_STATISTICS_XG", "1")
    monkeypatch.setenv("HIBS_FETCH_FIXTURE_STATISTICS_XG_MAX", "1")
    reset_statistics_xg_budget()

    api = MagicMock()
    api.fetch_fixture_statistics.return_value = [
        {"team": {"id": 1}, "statistics": [{"type": "Expected Goals", "value": "1.0"}]},
        {"team": {"id": 2}, "statistics": [{"type": "Expected Goals", "value": "1.0"}]},
    ]
    cache = MagicMock()
    cache.get.return_value = None

    first = fetch_fixture_statistics_xg(api, cache, 1, home_team_id=1, away_team_id=2, current_source="goals_proxy")
    second = fetch_fixture_statistics_xg(api, cache, 2, home_team_id=3, away_team_id=4, current_source="goals_proxy")
    assert first is not None
    assert second is None
    assert api.fetch_fixture_statistics.call_count == 1


def test_disabled_when_env_off(monkeypatch):
    monkeypatch.delenv("HIBS_FETCH_FIXTURE_STATISTICS_XG", raising=False)
    reset_statistics_xg_budget()
    api = MagicMock()
    cache = MagicMock()
    assert fetch_fixture_statistics_xg(api, cache, 1, current_source="goals_proxy") is None
    api.fetch_fixture_statistics.assert_not_called()
