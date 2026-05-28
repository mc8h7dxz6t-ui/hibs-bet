from __future__ import annotations

from unittest.mock import patch


def test_api_fixtures_live_returns_cold_shell_on_cache_miss():
    from hibs_predictor.web import app

    with patch("hibs_predictor.web.Cache.peek", return_value=None), patch(
        "hibs_predictor.web._schedule_dashboard_refresh"
    ) as sched:
        client = app.test_client()
        resp = client.get("/api/fixtures/live?ids=1,2")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload.get("cold_start") is True
    assert payload.get("cache_stale") is True
    assert payload.get("fixtures") == {}
    assert sched.called


def test_tables_route_shows_loading_banner_on_cold_cache():
    from hibs_predictor.web import app

    with patch("hibs_predictor.web.Cache.peek", return_value=None), patch(
        "hibs_predictor.web._schedule_dashboard_refresh"
    ) as sched:
        client = app.test_client()
        resp = client.get("/tables")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Loading tables" in body
    assert 'href="/players"' in body
    assert sched.called


def test_dashboard_refresh_progressive_returns_cold_shell(monkeypatch):
    from hibs_predictor.web import app

    monkeypatch.setenv("HIBS_PROGRESSIVE_LOAD", "1")
    with patch("hibs_predictor.web.clear_application_caches") as clear_cache, patch(
        "hibs_predictor.web.fetch_all_fixtures", side_effect=AssertionError("should not block on refresh")
    ), patch("hibs_predictor.web._schedule_dashboard_refresh") as sched:
        client = app.test_client()
        resp = client.get("/?refresh=1")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Loading fixtures" in body
    assert clear_cache.called
    assert sched.called
    assert resp.headers.get("Cache-Control") == "no-store, private"
    assert "ETag" not in resp.headers


def test_dashboard_cold_shell_keeps_mobile_sky_players_links(monkeypatch):
    from hibs_predictor.web import app

    monkeypatch.setenv("HIBS_PROGRESSIVE_LOAD", "1")
    monkeypatch.setenv("HIBS_SHOW_SKY_PANEL", "1")
    with patch("hibs_predictor.web.clear_application_caches"), patch(
        "hibs_predictor.web.fetch_all_fixtures", side_effect=AssertionError("should not block on refresh")
    ), patch("hibs_predictor.web._schedule_dashboard_refresh"):
        client = app.test_client()
        resp = client.get("/?refresh=1")
    body = resp.get_data(as_text=True)
    assert "Sky panel is available on desktop." in body
    assert "Players</a>" in body
