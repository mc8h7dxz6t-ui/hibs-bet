"""Live score polling and dashboard fixture id helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from hibs_predictor.live_scores import (
    api_fixture_id_for_row,
    dashboard_fixture_id,
    fixture_ids_likely_in_play,
    fixture_in_kickoff_poll_window,
    live_payload_for_dashboard_rows,
    merge_live_into_fixtures,
    parse_fixture_id_int,
)


def test_parse_fixture_id_int_numeric_and_fotmob():
    assert parse_fixture_id_int(12345) == 12345
    assert parse_fixture_id_int("999") == 999
    assert parse_fixture_id_int("fotmob_42") is None
    assert parse_fixture_id_int(None) is None


def test_api_fixture_id_prefers_explicit_field():
    row = {"id": "fotmob_1", "api_fixture_id": 555}
    assert api_fixture_id_for_row(row) == 555
    assert dashboard_fixture_id(row) == "fotmob_1"


def test_merge_live_stamps_api_fixture_id_for_fotmob_row():
    live_by_id = {
        9001: {
            "fixture_id": 9001,
            "is_live": True,
            "live_status": "1H",
            "live_minute": 12,
            "live_score": "1-0",
            "_match_home": "hibernian",
            "_match_away": "celtic",
            "_match_league_code": "SCOTLAND",
        }
    }
    row = {
        "id": "fotmob_99",
        "home": "Hibernian",
        "away": "Celtic",
        "league": "SCOTLAND",
    }
    merge_live_into_fixtures([row], live_by_id)
    assert row.get("is_live") is True
    assert row.get("api_fixture_id") == 9001
    assert row.get("live_score") == "1-0"


def test_live_payload_keys_by_dashboard_id(monkeypatch):
    monkeypatch.setenv("HIBS_LIVE_MAX_EVENT_FETCHES", "0")
    monkeypatch.setenv("HIBS_LIVE_MAX_STATS_FETCHES", "0")
    live_row = {
        "fixture_id": 42,
        "is_live": True,
        "live_status": "1H",
        "live_minute": 5,
        "live_score": "0-0",
        "_match_home": "arsenal",
        "_match_away": "chelsea",
        "_match_league_code": "EPL",
    }
    client = MagicMock()
    client.rate_limiter.check_rate_limit.return_value = True
    aggregator = MagicMock()
    aggregator.clients = {"api_sports": client}

    import hibs_predictor.live_scores as mod

    monkeypatch.setattr(mod, "fetch_live_by_id", lambda *a, **k: {42: live_row})
    monkeypatch.setattr(mod.Cache, "get", lambda *a, **k: None)

    dash_row = {
        "id": "fotmob_7",
        "home": "Arsenal",
        "away": "Chelsea",
        "league": "EPL",
        "kickoff_sort": datetime.now(timezone.utc).isoformat(),
    }
    payload = live_payload_for_dashboard_rows(
        aggregator,
        ["fotmob_7"],
        [dash_row],
        include_events=False,
        include_stats=False,
    )
    assert "fotmob_7" in payload["fixtures"]
    assert payload["fixtures"]["fotmob_7"]["live_score"] == "0-0"


def test_fixture_ids_likely_in_play_includes_fotmob_near_kickoff():
    ko = datetime.now(timezone.utc) - timedelta(minutes=30)
    rows = [
        {
            "id": "fotmob_12",
            "kickoff_sort": ko.isoformat(),
            "home": "A",
            "away": "B",
        }
    ]
    ids = fixture_ids_likely_in_play(rows)
    assert ids == ["fotmob_12"]


def test_fixture_in_kickoff_poll_window_before_start():
    ko = datetime.now(timezone.utc) + timedelta(minutes=10)
    row = {"kickoff_sort": ko.isoformat()}
    assert fixture_in_kickoff_poll_window(row) is True
