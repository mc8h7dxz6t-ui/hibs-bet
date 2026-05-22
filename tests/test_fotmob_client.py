"""FotMob client tests (mocked HTTP)."""

from datetime import date
from unittest.mock import MagicMock, patch

from hibs_predictor.scrapers import fotmob_client as fm


def test_fetch_matches_for_date_parses_leagues():
    payload = {
        "leagues": [
            {
                "id": 47,
                "primaryId": 47,
                "name": "Premier League",
                "matches": [
                    {
                        "id": 1,
                        "home": {"id": 10, "name": "Arsenal", "longName": "Arsenal"},
                        "away": {"id": 20, "name": "Chelsea", "longName": "Chelsea"},
                        "status": {"utcTime": "2025-05-18T14:00:00.000Z"},
                    }
                ],
            }
        ]
    }
    cache = MagicMock()
    cache.get.return_value = None
    with patch("hibs_predictor.scrapers.fotmob_client.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = payload
        out = fm.fetch_matches_for_date(date(2025, 5, 18), cache=cache)
    assert len(out.get("leagues") or []) == 1
    cache.set.assert_called_once()


def test_fixtures_for_league_filters_by_id():
    payload = {
        "leagues": [
            {"id": 47, "name": "Premier League", "matches": [{"id": 99, "home": {}, "away": {}}]},
            {"id": 999, "name": "Other", "matches": [{"id": 1, "home": {}, "away": {}}]},
        ]
    }
    cache = MagicMock()
    cache.get.return_value = payload
    rows = fm.fixtures_for_league("EPL", date(2025, 5, 18), date(2025, 5, 18), cache=cache)
    assert len(rows) == 1
    assert rows[0]["id"] == 99


def test_probe_matches_api_ok():
    with patch("hibs_predictor.scrapers.fotmob_client.fetch_matches_for_date") as mock_fetch:
        mock_fetch.return_value = {"leagues": [{}] * 8}
        pr = fm.probe_matches_api()
    assert pr["ok"] is True
    assert pr.get("http_status") == 200
