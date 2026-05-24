"""API client squad fetch (mocked HTTP)."""

from unittest.mock import MagicMock, patch

from hibs_predictor.api_clients import ApiSportsFootballClient


def test_fetch_team_squad_parses_response():
    client = ApiSportsFootballClient("test-key")
    payload = {
        "response": [
            {
                "team": {"id": 50, "name": "City"},
                "players": [
                    {"id": 1, "name": "A", "position": "Goalkeeper"},
                    {"id": 2, "name": "B", "position": "Defender"},
                ],
            }
        ]
    }
    with patch.object(client, "_get_json", return_value=payload):
        rows = client.fetch_team_squad(50)
    assert len(rows) == 2
    assert rows[0]["name"] == "A"

    client.cache = MagicMock()
    client.cache.get.return_value = rows
    cached = client.fetch_team_squad(50)
    assert cached == rows
