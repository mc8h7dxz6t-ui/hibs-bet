from __future__ import annotations

from unittest.mock import patch


def test_players_route_returns_200(monkeypatch):
    from hibs_predictor.web import app

    fixture = {
        "id": 11,
        "home": "Hibs",
        "away": "Hearts",
        "league": "SCOTLAND_PREMIERSHIP",
        "league_name": "Scottish Premiership",
        "kickoff_time": "19:45",
        "kickoff_day_local": "2026-05-30",
        "lineup_confirmed": True,
        "home_top_scorers": [{"name": "Player A", "goals": 14}],
        "away_top_scorers": [{"name": "Player B", "goals": 11}],
        "fixture_injuries": [{"name": "Out 1"}],
        "lineup_meta": {"home_scorers_out_of_xi": [{"name": "Player A"}]},
        "prediction": {"predicted_outcome": "home"},
    }
    bundle = {
        "all": [fixture],
        "total": 1,
        "fetch_days": 5,
        "by_region": {},
        "by_league": {},
        "dashboard_days": [],
        "value_bets": [],
        "value_bet_count": 0,
        "sidebar_upcoming": [],
    }
    with patch("hibs_predictor.web.Cache.peek", return_value={"ok": True}), patch(
        "hibs_predictor.web.fetch_all_fixtures", return_value=bundle
    ):
        client = app.test_client()
        response = client.get("/players")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Players" in html
    assert "Lineups confirmed" in html
    assert "Out of XI" in html
    assert "Open fixture row" in html
