"""API-Football squad depth enrichment (mocked)."""

from unittest.mock import MagicMock

from hibs_predictor.squad_depth_enrich import attach_api_squad_depth, summarize_squad_players


def test_summarize_squad_players():
    players = [
        {"name": "A", "position": "Goalkeeper"},
        {"name": "B", "position": "Defender"},
        {"name": "C", "position": "Defender"},
        {"name": "D", "position": "Attacker"},
    ]
    out = summarize_squad_players(players)
    assert out["size"] == 4
    assert out["positions"]["Goalkeeper"] == 1
    assert out["positions"]["Defender"] == 2
    assert out["source"] == "api_football"


def test_attach_api_squad_depth_merges_meta(monkeypatch):
    monkeypatch.setenv("HIBS_ENABLE_API_SQUAD_DEPTH", "1")
    client = MagicMock()
    client.fetch_team_squad.side_effect = [
        [{"name": "H1", "position": "Midfielder"}] * 20,
        [{"name": "A1", "position": "Attacker"}] * 22,
    ]
    enriched = {
        "home_id": 1,
        "away_id": 2,
        "fixture_injuries": [],
        "team_news_meta": {"home_absences": 2, "away_absences": 0},
    }
    attach_api_squad_depth(enriched, client, season=2025)
    assert enriched["home_squad_depth"]["size"] == 20
    assert enriched["away_squad_depth"]["size"] == 22
    assert enriched["team_news_meta"]["home_absence_pct"] == 0.1
    assert client.fetch_team_squad.call_count == 2


def test_attach_api_squad_depth_respects_skip(monkeypatch):
    monkeypatch.setenv("HIBS_SKIP_API_SQUAD_DEPTH", "1")
    client = MagicMock()
    enriched = {"home_id": 1, "away_id": 2}
    attach_api_squad_depth(enriched, client)
    client.fetch_team_squad.assert_not_called()
