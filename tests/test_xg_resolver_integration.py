"""Integration: scraped_xg resolver order (score-based, never downgrade api_fixture_xg)."""

from unittest.mock import patch

import pytest

from hibs_predictor.scraped_xg import _SCRAPE_RESOLVERS, apply_scraped_xg_to_enriched


def _enriched(**kwargs) -> dict:
    base = {
        "xg_home": 1.0,
        "xg_away": 1.0,
        "xg_source": "goals_proxy",
        "league_factor": 1.0,
        "home_recent": [],
        "away_recent": [],
        "home_stats": {"played": 20, "goals_for": 30, "goals_against": 22},
        "away_stats": {"played": 20, "goals_for": 28, "goals_against": 24},
        "supplemental": {},
    }
    base.update(kwargs)
    return base


@pytest.fixture(autouse=True)
def scrape_on(monkeypatch):
    monkeypatch.setenv("HIBS_SCRAPE_XG", "1")
    monkeypatch.setenv("HIBS_ENABLE_FOTMOB_XG", "0")
    monkeypatch.delenv("HIBS_FBREF_BLOCKED", raising=False)


def test_resolver_order_names():
    names = [r.__name__ for r in _SCRAPE_RESOLVERS]
    assert names.index("_try_understat") < names.index("_try_fotmob")
    assert names.index("_try_fotmob") < names.index("_try_recent_api_xg")
    assert names.index("_try_recent_api_xg") < names.index("_try_api_season")
    assert names.index("_try_api_season") < names.index("_try_statsbomb")


def test_understat_wins_over_fotmob_and_season():
    enriched = _enriched(
        supplemental={
            "understat_light": {"xg_home": 1.7, "xg_away": 0.9},
            "fotmob_xg": {"xg_home": 1.4, "xg_away": 1.3, "home_n": 10, "away_n": 10},
        }
    )
    fixture = {"teams": {"home": {"name": "Arsenal"}, "away": {"name": "Chelsea"}}}
    out = apply_scraped_xg_to_enriched(fixture, "EPL", enriched)
    assert out["xg_source"] in ("understat_xg", "understat_team_xg")


def test_fotmob_before_api_season():
    enriched = _enriched(
        supplemental={"fotmob_xg": {"xg_home": 1.55, "xg_away": 1.05, "home_n": 14, "away_n": 13}}
    )
    fixture = {"teams": {"home": {"name": "Celtic"}, "away": {"name": "Rangers"}}}
    with patch("hibs_predictor.scraped_xg._try_understat", return_value=None):
        out = apply_scraped_xg_to_enriched(fixture, "SCOTTISH_CUP", enriched)
    assert out["xg_source"] == "fotmob_league_xg"


def test_recent_before_season():
    recent = {
        "teams": {"home": {"id": 1}, "away": {"id": 2}},
        "statistics": [
            {"team": {"id": 1}, "expected_goals": {"value": "2.0"}},
            {"team": {"id": 2}, "expected_goals": {"value": "0.8"}},
        ],
    }
    enriched = _enriched(
        home_recent=[recent, recent],
        away_recent=[
            {
                "teams": {"home": {"id": 3}, "away": {"id": 4}},
                "statistics": [
                    {"team": {"id": 3}, "expected_goals": {"value": "1.0"}},
                    {"team": {"id": 4}, "expected_goals": {"value": "1.6"}},
                ],
            },
            {
                "teams": {"home": {"id": 3}, "away": {"id": 4}},
                "statistics": [
                    {"team": {"id": 3}, "expected_goals": {"value": "1.1"}},
                    {"team": {"id": 4}, "expected_goals": {"value": "1.5"}},
                ],
            },
        ],
    )
    fixture = {"teams": {"home": {"id": 1}, "away": {"id": 4}}}
    with patch("hibs_predictor.scraped_xg._try_understat", return_value=None):
        with patch("hibs_predictor.scraped_xg._try_fotmob", return_value=None):
            out = apply_scraped_xg_to_enriched(fixture, "EPL", enriched)
    assert out["xg_source"] == "scraped_recent_xg"


def test_api_fixture_xg_never_downgraded(monkeypatch):
    monkeypatch.setenv("HIBS_ALWAYS_DEEP_SCRAPE", "0")
    enriched = _enriched(xg_source="api_fixture_xg", xg_home=1.9, xg_away=0.7)
    enriched["supplemental"]["understat_light"] = {"xg_home": 2.5, "xg_away": 2.4}
    fixture = {"teams": {"home": {"id": 1}, "away": {"id": 2}}}
    out = apply_scraped_xg_to_enriched(fixture, "EPL", enriched)
    assert out["xg_source"] == "api_fixture_xg"
    assert out["xg_home"] == 1.9
