"""Heavy supplemental scrapers run by default even when API inputs look strong."""

from __future__ import annotations

from hibs_predictor.scrapers.supplemental import _always_deep_scrape, _skip_heavy_when_api_strong


def _api_strong_enriched() -> dict:
    return {
        "odds_available": True,
        "xg_source": "api_fixture_xg",
        "home_recent_n": 8,
        "away_recent_n": 8,
        "home_stats": {"played": 20, "goals_for": 30, "goals_against": 25},
        "away_stats": {"played": 20, "goals_for": 28, "goals_against": 22},
        "home_position": {"position": 3},
        "away_position": {"position": 9},
    }


def test_skip_heavy_off_by_default(monkeypatch):
    monkeypatch.delenv("HIBS_SKIP_HEAVY_WHEN_API_STRONG", raising=False)
    monkeypatch.delenv("HIBS_ALWAYS_DEEP_SCRAPE", raising=False)
    skip, reason = _skip_heavy_when_api_strong(_api_strong_enriched())
    assert skip is False
    assert reason == ""


def test_skip_heavy_when_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("HIBS_SKIP_HEAVY_WHEN_API_STRONG", "1")
    monkeypatch.setenv("HIBS_ALWAYS_DEEP_SCRAPE", "0")
    skip, reason = _skip_heavy_when_api_strong(_api_strong_enriched())
    assert skip is True
    assert reason == "api_strong_skip_heavy"


def test_always_deep_overrides_skip_flag(monkeypatch):
    monkeypatch.setenv("HIBS_SKIP_HEAVY_WHEN_API_STRONG", "1")
    monkeypatch.setenv("HIBS_ALWAYS_DEEP_SCRAPE", "1")
    skip, _ = _skip_heavy_when_api_strong(_api_strong_enriched())
    assert skip is False
    assert _always_deep_scrape() is True
