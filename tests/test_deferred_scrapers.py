"""Deferred source probes (mocked)."""

from unittest.mock import MagicMock, patch

from hibs_predictor.scrapers import besoccer_client, transfermarkt_client, xgstat_client


def test_transfermarkt_probe():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "User-agent: *\nDisallow: /"
    with patch("hibs_predictor.scrapers.transfermarkt_client.requests.get", return_value=mock_resp):
        out = transfermarkt_client.probe_availability()
    assert out["status"] == "deferred"
    assert out.get("production_alternative") == "api_football_injuries_squads"
    assert "players/squads" in (out.get("note") or "")


def test_xgstat_probe_not_available():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "text/html"}
    with patch("hibs_predictor.scrapers.xgstat_client.requests.get", return_value=mock_resp):
        out = xgstat_client.probe_public_api()
    assert out["ok"] is False
    assert out["status"] == "deferred"
    assert out.get("production_alternative") == "understat_fotmob_api_xg"
    assert isinstance(out.get("probes"), list)


def test_besoccer_probe_deferred():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "text/html"}
    with patch("hibs_predictor.scrapers.besoccer_client.requests.get", return_value=mock_resp):
        out = besoccer_client.probe_public_api()
    assert out["status"] == "deferred"
    assert out.get("production_alternative") == "api_football_soccerstats_fotmob"
