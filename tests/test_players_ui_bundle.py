"""Players UI must follow dashboard fixture rows and survive refresh."""

from __future__ import annotations

from unittest.mock import patch

from hibs_predictor.web import (
    _fixtures_from_dashboard_bundle,
    _players_groups_for_ui_data,
)


def _fx(*, fid: int, league: str = "EPL", league_name: str = "Premier League") -> dict:
    return {
        "id": fid,
        "home": f"Home {fid}",
        "away": f"Away {fid}",
        "league": league,
        "league_name": league_name,
        "kickoff_time": "15:00",
        "kickoff_day_local": "2026-05-30",
        "kickoff_sort": f"2026-05-30T12:{fid:02d}:00",
        "lineup_confirmed": True,
        "home_top_scorers": [{"name": "Striker", "goals": 10}],
        "away_top_scorers": [],
        "fixture_injuries": [],
        "lineup_meta": {},
    }


def test_fixtures_from_dashboard_bundle_prefers_dashboard_days():
    fx = _fx(fid=1)
    data = {
        "upcoming": [],
        "all": [],
        "dashboard_days": [
            {
                "date_iso": "2026-05-30",
                "leagues": [{"code": "EPL", "fixtures": [fx]}],
            }
        ],
    }
    assert _fixtures_from_dashboard_bundle(data) == [fx]


def test_players_groups_stale_disk_when_cold_shell():
    fx = _fx(fid=2, league="SCOTLAND", league_name="Scottish Premiership")
    stale = {
        "all": [fx],
        "dashboard_days": [
            {
                "date_iso": "2026-05-30",
                "leagues": [{"code": "SCOTLAND", "fixtures": [fx]}],
            }
        ],
    }
    cold = {"all": [], "dashboard_days": [], "cold_start": True, "cache_stale": True}
    with patch("hibs_predictor.web.Cache.peek", return_value=stale):
        groups = _players_groups_for_ui_data(cold, limit=8, include_domestic=False)
    assert len(groups) == 1
    assert groups[0]["league"] == "SCOTLAND"
    assert groups[0]["rows"][0]["home"] == "Home 2"


def test_refresh_non_progressive_returns_200_without_blocking_fetch(monkeypatch):
    from hibs_predictor.web import app

    monkeypatch.setenv("HIBS_PROGRESSIVE_LOAD", "0")
    with patch("hibs_predictor.web.clear_application_caches") as clear_cache, patch(
        "hibs_predictor.web.fetch_all_fixtures",
        side_effect=AssertionError("refresh must not block on full fetch"),
    ), patch("hibs_predictor.web._schedule_dashboard_refresh"):
        resp = app.test_client().get("/?refresh=1")
    assert resp.status_code == 200
    assert clear_cache.called
    body = resp.get_data(as_text=True)
    assert "Loading fixtures" in body
    assert resp.headers.get("Cache-Control") == "no-store, private"
