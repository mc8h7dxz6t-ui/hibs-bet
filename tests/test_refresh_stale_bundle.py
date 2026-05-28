"""refresh=1 should serve last disk bundle while background warm runs."""

from __future__ import annotations

from unittest.mock import patch


def test_refresh_serves_stale_disk_bundle_instead_of_cold_shell(monkeypatch):
    from hibs_predictor.web import app

    monkeypatch.setenv("HIBS_PROGRESSIVE_LOAD", "1")
    stale = {
        "all": [
            {
                "id": 9,
                "league": "EPL",
                "home": "A",
                "away": "B",
                "date": "2026-06-01T15:00:00+00:00",
                "kickoff_sort": "2026-06-01T15:00:00+00:00",
            }
        ],
        "total": 1,
        "by_region": {},
        "by_league": {},
        "dashboard_days": [],
        "value_bets": [],
        "value_bet_count": 0,
        "fixture_coverage": {},
        "upcoming": [],
    }
    with patch("hibs_predictor.web._is_complete_fixture_bundle", return_value=True), patch(
        "hibs_predictor.web.Cache.peek", return_value=stale
    ), patch("hibs_predictor.web.clear_application_caches") as clear_cache, patch(
        "hibs_predictor.web.fetch_all_fixtures",
        side_effect=AssertionError("refresh must not block on full fetch"),
    ), patch("hibs_predictor.web._schedule_dashboard_refresh"):
        resp = app.test_client().get("/?refresh=1")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert clear_cache.called
    assert "Loading fixtures" not in body
    assert "A" in body and "B" in body
