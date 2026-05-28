"""HTTP routes must not block on cold-cache fixture rebuild."""

from __future__ import annotations

from unittest.mock import patch


def test_load_fixtures_for_http_returns_cold_shell_without_fetch(monkeypatch):
    from hibs_predictor.web import _load_fixtures_for_http

    monkeypatch.setenv("HIBS_PROGRESSIVE_LOAD", "1")
    with patch("hibs_predictor.web.Cache.get", return_value=None), patch(
        "hibs_predictor.web._stale_fixture_bundle_for_refresh", return_value=None
    ), patch(
        "hibs_predictor.web.fetch_all_fixtures",
        side_effect=AssertionError("request path must not rebuild"),
    ), patch("hibs_predictor.web._schedule_dashboard_refresh") as sched:
        data = _load_fixtures_for_http()
    assert data.get("cold_start") is True
    assert data.get("cache_stale") is True
    assert sched.called


def test_api_insights_content_does_not_block_on_cold_cache(monkeypatch):
    from hibs_predictor.web import app

    monkeypatch.setenv("HIBS_PROGRESSIVE_LOAD", "1")
    with patch("hibs_predictor.web._load_fixtures_for_http") as load, patch(
        "hibs_predictor.web._schedule_dashboard_refresh"
    ):
        load.return_value = {
            "all": [],
            "upcoming": [],
            "by_region": {},
            "by_league": {},
            "dashboard_days": [],
            "value_bets": [],
            "total": 0,
            "value_bet_count": 0,
            "fixture_coverage": {},
            "fetch_days": 5,
            "cold_start": True,
            "cache_stale": True,
        }
        resp = app.test_client().get("/api/insights/content")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload.get("cache_stale") is True


def test_background_refresh_uses_force_reboost(monkeypatch):
    from hibs_predictor.web import _schedule_dashboard_refresh

    monkeypatch.setenv("HIBS_WARM_FIXTURE_CACHE", "1")
    with patch("hibs_predictor.web.fetch_all_fixtures") as fetch_all:
        _schedule_dashboard_refresh()
        import time

        deadline = time.time() + 2.0
        while not fetch_all.called and time.time() < deadline:
            time.sleep(0.05)
    fetch_all.assert_called_once()
    _, kwargs = fetch_all.call_args
    assert kwargs.get("force_refresh") is True
    assert kwargs.get("reboost") is True
