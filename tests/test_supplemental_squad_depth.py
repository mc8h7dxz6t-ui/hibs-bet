"""Supplemental mirror of API squad depth (mocked cache)."""

from unittest.mock import MagicMock, patch

from hibs_predictor.scrapers.supplemental import collect_supplemental


def test_supplemental_mirrors_api_squad_depth(monkeypatch):
    monkeypatch.setenv("HIBS_ENABLE_SUPPLEMENTAL", "1")
    monkeypatch.setenv("HIBS_ENABLE_HEAVY_SCRAPERS", "0")
    monkeypatch.setenv("HIBS_ENABLE_UNDERSTAT_LIGHT", "0")
    monkeypatch.setenv("HIBS_PREFER_SCRAPED_STANDINGS", "0")

    fixture = {
        "fixture": {"id": 12345},
        "teams": {"home": {"name": "Hibernian"}, "away": {"name": "Hearts"}},
    }
    enriched = {
        "home_squad_depth": {"size": 25, "positions": {"Defender": 10}, "source": "api_football"},
        "away_squad_depth": {"size": 24, "positions": {"Attacker": 6}, "source": "api_football"},
    }
    mock_cache = MagicMock()
    mock_cache.get.return_value = None

    with patch("hibs_predictor.scrapers.supplemental.Cache", return_value=mock_cache):
        out = collect_supplemental(fixture, "SCOTLAND", enriched)

    assert out.get("api_squad_depth", {}).get("home", {}).get("size") == 25
    assert out.get("api_squad_depth", {}).get("away", {}).get("size") == 24
    mock_cache.set.assert_called_once()
