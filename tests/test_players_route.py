from __future__ import annotations

from unittest.mock import patch

from hibs_predictor.config import players_panel_league_order_index
from hibs_predictor.web import _players_page_groups, _players_page_rows


def _player_fixture(
    *,
    fid: int,
    league: str,
    league_name: str,
    kickoff_sort: str = "2026-05-30T12:00:00",
) -> dict:
    return {
        "id": fid,
        "home": f"Home {fid}",
        "away": f"Away {fid}",
        "league": league,
        "league_name": league_name,
        "kickoff_time": "15:00",
        "kickoff_day_local": "2026-05-30",
        "kickoff_sort": kickoff_sort,
        "lineup_confirmed": False,
        "home_top_scorers": [],
        "away_top_scorers": [],
        "fixture_injuries": [],
        "lineup_meta": {},
    }


def test_players_page_rows_league_order_epl_before_spl():
    fixtures = [
        _player_fixture(fid=1, league="SCOTLAND", league_name="Scottish Premiership"),
        _player_fixture(fid=2, league="EPL", league_name="Premier League"),
        _player_fixture(
            fid=3,
            league="CHAMPIONSHIP",
            league_name="Championship",
            kickoff_sort="2026-05-30T14:00:00",
        ),
        _player_fixture(
            fid=4,
            league="LA_LIGA",
            league_name="La Liga",
            kickoff_sort="2026-05-30T16:00:00",
        ),
    ]
    rows = _players_page_rows(fixtures)
    assert [r["league"] for r in rows] == ["EPL", "SCOTLAND", "LA_LIGA", "CHAMPIONSHIP"]


def test_players_page_groups_emit_league_section_headers():
    fixtures = [
        _player_fixture(fid=1, league="SCOTLAND", league_name="Scottish Premiership"),
        _player_fixture(fid=2, league="EPL", league_name="Premier League"),
        _player_fixture(fid=3, league="EPL", league_name="Premier League", kickoff_sort="2026-05-30T18:00:00"),
    ]
    groups = _players_page_groups(fixtures)
    assert [g["section_title"] for g in groups] == ["Premier League", "Scottish Premiership"]
    assert len(groups[0]["rows"]) == 2
    assert len(groups[1]["rows"]) == 1


def test_players_panel_league_order_index_matches_priority_buckets():
    order = players_panel_league_order_index()
    assert order["EPL"] < order["SCOTLAND"]
    assert order["SCOTLAND"] < order["LA_LIGA"]
    assert order["LA_LIGA"] < order["CHAMPIONSHIP"]
    assert order["CHAMPIONSHIP"] < order["SCOTLAND_CHAMP"]


def test_players_route_returns_200(monkeypatch):
    from hibs_predictor.web import app

    fixture = {
        "id": 11,
        "home": "Hibs",
        "away": "Hearts",
        "league": "SCOTLAND",
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
    assert 'data-league-section="SCOTLAND"' in html
    assert "SCOTTISH PREMIERSHIP" in html


def test_dashboard_players_panel_is_always_visible(monkeypatch):
    from hibs_predictor.web import app

    fixture = {
        "id": 11,
        "home": "Hibs",
        "away": "Hearts",
        "league": "SCOTLAND",
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
        "total": 0,
        "fetch_days": 5,
        "by_region": {},
        "by_league": {"SCOTLAND": [fixture]},
        "dashboard_days": [],
        "value_bets": [],
        "value_bet_count": 0,
        "sidebar_upcoming": [],
    }
    with patch("hibs_predictor.web.Cache.peek", return_value={"ok": True}), patch(
        "hibs_predictor.web.fetch_all_fixtures", return_value=bundle
    ):
        client = app.test_client()
        response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="dashboard-players-panel"' in html
    assert "Players Snapshot" in html
    assert "Open Players" in html
    assert "Lineups confirmed" in html
    assert "dashboard-players-league-hd" in html
