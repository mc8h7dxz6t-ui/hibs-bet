"""Route-level stability: cold cache shells must not 500 or block on full refetch."""

from __future__ import annotations

from unittest.mock import patch


def _cold_client(monkeypatch):
    from hibs_predictor.web import app

    monkeypatch.setenv("HIBS_PROGRESSIVE_LOAD", "1")
    return app.test_client()


def test_players_page_cold_cache_non_blocking(monkeypatch):
    client = _cold_client(monkeypatch)
    with patch("hibs_predictor.web.Cache.peek", return_value=None), patch(
        "hibs_predictor.web._schedule_dashboard_refresh"
    ) as sched, patch(
        "hibs_predictor.web.fetch_all_fixtures",
        side_effect=AssertionError("players must not block on cold cache"),
    ):
        resp = client.get("/players")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Loading players data" in body
    assert sched.called


def test_insights_page_cold_cache_non_blocking(monkeypatch):
    client = _cold_client(monkeypatch)
    with patch("hibs_predictor.web.Cache.peek", return_value=None), patch(
        "hibs_predictor.web._schedule_dashboard_refresh"
    ) as sched, patch(
        "hibs_predictor.web.fetch_all_fixtures",
        side_effect=AssertionError("insights must not block on cold cache"),
    ):
        resp = client.get("/insights")
    assert resp.status_code == 200
    assert sched.called


def test_status_page_renders_without_fixture_fetch():
    from hibs_predictor.web import app

    with patch("hibs_predictor.web.fetch_all_fixtures", side_effect=AssertionError("status must not fetch fixtures")):
        resp = app.test_client().get("/status")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "API" in body or "status" in body.lower()


def test_performance_page_renders():
    from hibs_predictor.web import app

    with patch("hibs_predictor.performance_analytics.build_performance_page_dict") as build:
        build.return_value = {
            "display_tz_label": "Europe/London",
            "history_days": 14,
            "slices": [],
        }
        resp = app.test_client().get("/performance")
    assert resp.status_code == 200
    build.assert_called_once()


def test_fetch_all_fixtures_stale_fallback_on_empty_fetch(monkeypatch, tmp_path):
    from hibs_predictor.cache import Cache
    from hibs_predictor.web import _all_fixtures_cache_key, fetch_all_fixtures

    monkeypatch.chdir(tmp_path)
    ck = _all_fixtures_cache_key(include_domestic=False)
    stale_bundle = {
        "all": [{"id": 1, "league": "EPL", "home": "A", "away": "B", "date": "2026-06-01T15:00:00+00:00"}],
        "total": 1,
        "by_region": {},
        "by_league": {},
        "dashboard_days": [],
        "value_bets": [],
        "value_bet_count": 0,
        "fixture_coverage": {},
    }
    cache = Cache()
    cache.set(ck, stale_bundle, ttl_hours=24)

    with patch.object(cache, "get", return_value=None), patch(
        "hibs_predictor.web.Cache",
        return_value=cache,
    ), patch("hibs_predictor.web._fetch_all_league_fixtures_parallel", return_value=[]):
        data = fetch_all_fixtures(allow_stale=True, include_domestic=False)
    assert data.get("total") == 1
    assert data.get("cache_stale") is True
