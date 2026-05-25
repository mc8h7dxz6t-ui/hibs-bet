"""scraped_xg priority and score-based upgrades."""

from unittest.mock import patch

import pytest

from hibs_predictor.scraped_xg import (
    apply_scraped_xg_to_enriched,
    apply_season_team_xg_from_stats,
    resolve_scraped_xg,
)


def _base_enriched(**kwargs) -> dict:
    base = {
        "xg_home": 1.1,
        "xg_away": 1.0,
        "xg_source": "goals_proxy",
        "league_factor": 1.0,
        "home_recent": [],
        "away_recent": [],
        "home_stats": {"played": 28, "goals_for": 42, "goals_against": 30},
        "away_stats": {"played": 28, "goals_for": 38, "goals_against": 35},
        "supplemental": {},
    }
    base.update(kwargs)
    return base


@pytest.fixture(autouse=True)
def _scrape_on(monkeypatch):
    monkeypatch.setenv("HIBS_SCRAPE_XG", "1")
    monkeypatch.delenv("HIBS_FBREF_BLOCKED", raising=False)


def test_skips_when_api_fixture_xg_present(monkeypatch):
    monkeypatch.setenv("HIBS_ALWAYS_DEEP_SCRAPE", "0")
    enriched = _base_enriched(xg_source="api_fixture_xg", xg_home=1.5, xg_away=1.2)
    fixture = {"teams": {"home": {"id": 1}, "away": {"id": 2}}}
    assert resolve_scraped_xg(fixture, "EPL", enriched) is None


def test_skips_when_api_statistics_xg_present(monkeypatch):
    monkeypatch.setenv("HIBS_ALWAYS_DEEP_SCRAPE", "0")
    enriched = _base_enriched(xg_source="api_statistics_xg", xg_home=1.4, xg_away=1.1)
    fixture = {"teams": {"home": {"id": 1}, "away": {"id": 2}}}
    assert resolve_scraped_xg(fixture, "EPL", enriched) is None


def test_recent_api_xg_beats_statsbomb_on_cup(monkeypatch):
    monkeypatch.delenv("HIBS_ENABLE_STATSBOMB_LIGHT", raising=False)
    monkeypatch.delenv("HIBS_MAX_DATA", raising=False)
    monkeypatch.setenv("HIBS_ENABLE_FOTMOB_XG", "0")
    recent_h = {
        "teams": {"home": {"id": 10}, "away": {"id": 99}},
        "statistics": [
            {"team": {"id": 10}, "expected_goals": {"value": "1.8"}},
            {"team": {"id": 99}, "expected_goals": {"value": "0.9"}},
        ],
    }
    recent_a = {
        "teams": {"home": {"id": 88}, "away": {"id": 20}},
        "statistics": [
            {"team": {"id": 88}, "expected_goals": {"value": "1.1"}},
            {"team": {"id": 20}, "expected_goals": {"value": "1.4"}},
        ],
    }
    enriched = _base_enriched(
        home_recent=[recent_h, recent_h],
        away_recent=[recent_a, recent_a],
        supplemental={
            "statsbomb_open_team_proxy": {
                "home": {"ok": True, "gf_pg": 2.1, "ga_pg": 0.9, "matches_used": 5},
                "away": {"ok": True, "gf_pg": 1.8, "ga_pg": 1.0, "matches_used": 4},
            }
        },
    )
    fixture = {"teams": {"home": {"id": 10, "name": "A"}, "away": {"id": 20, "name": "B"}}}
    out = apply_scraped_xg_to_enriched(fixture, "UCL", enriched)
    assert out["xg_source"] == "scraped_recent_xg"


def test_fotmob_from_supplemental_before_api_season():
    enriched = _base_enriched(
        supplemental={
            "fotmob_xg": {"xg_home": 1.6, "xg_away": 1.1, "home_n": 12, "away_n": 11},
        }
    )
    fixture = {"teams": {"home": {"name": "Celtic"}, "away": {"name": "Rangers"}}}
    out = apply_scraped_xg_to_enriched(fixture, "SCOTTISH_CUP", enriched)
    assert out["xg_source"] == "fotmob_league_xg"


def test_api_season_team_xg_when_stats_deep():
    enriched = _base_enriched()
    fixture = {"teams": {"home": {"name": "H"}, "away": {"name": "A"}}}
    with patch("hibs_predictor.scraped_xg._try_fotmob", return_value=None):
        with patch("hibs_predictor.scraped_xg._try_understat", return_value=None):
            with patch("hibs_predictor.scraped_xg._try_recent_api_xg", return_value=None):
                out = apply_scraped_xg_to_enriched(fixture, "NORWAY_ELITESERIEN", enriched)
    assert out["xg_source"] in ("api_season_team_xg", "team_season_xg")
    assert out.get("xg_source_label")


def test_api_season_uses_measured_xg_per_match():
    enriched = _base_enriched(
        home_stats={
            "played": 20,
            "goals_for": 30,
            "goals_against": 22,
            "xg_for_pg": 1.55,
            "xg_against_pg": 1.1,
            "api_season_xg_measured": True,
        },
        away_stats={
            "played": 20,
            "goals_for": 28,
            "goals_against": 24,
            "xg_for_pg": 1.4,
            "xg_against_pg": 1.2,
            "api_season_xg_measured": True,
        },
    )
    from hibs_predictor.scraped_xg import _api_season_team_xg

    hit = _api_season_team_xg(enriched, 1.0)
    assert hit is not None
    xh, xa, meta = hit
    assert meta.get("api_season_xg_measured") is True
    assert meta.get("home_xg_per_match") == 1.55
    assert xh > 0.5 and xa > 0.5


def test_fbref_skipped_when_blocked(monkeypatch):
    monkeypatch.setenv("HIBS_FBREF_BLOCKED", "1")
    enriched = _base_enriched(
        supplemental={
            "fbref_schedule": {"xg_home": 1.5, "xg_away": 1.2, "source": "fbref_schedule_xg"},
        }
    )
    fixture = {"teams": {"home": {"name": "Hibs"}, "away": {"name": "Hearts"}}}
    with patch("hibs_predictor.scraped_xg._try_fotmob", return_value=None):
        with patch("hibs_predictor.scraped_xg._try_understat", return_value=None):
            with patch("hibs_predictor.scraped_xg._try_recent_api_xg", return_value=None):
                out = apply_scraped_xg_to_enriched(fixture, "SCOTLAND", enriched)
    assert out["xg_source"] in ("api_season_team_xg", "team_season_xg")


def test_apply_season_before_goals_proxy():
    enriched = _base_enriched(xg_source="goals_proxy")
    assert apply_season_team_xg_from_stats(enriched, 1.0) is True
    assert enriched["xg_source"] in ("api_season_team_xg", "team_season_xg")
    assert enriched.get("scraped_xg_meta", {}).get("home_xg_per_match") is not None


def test_apply_season_skips_api_fixture_xg():
    enriched = _base_enriched(xg_source="api_fixture_xg", xg_home=1.9, xg_away=0.8)
    assert apply_season_team_xg_from_stats(enriched, 1.0) is False
    assert enriched["xg_source"] == "api_fixture_xg"


def test_team_season_xg_tag_when_goals_only_rates():
    enriched = _base_enriched(
        home_stats={"played": 12, "goals_for": 18, "goals_against": 14},
        away_stats={"played": 12, "goals_for": 16, "goals_against": 15},
    )
    assert apply_season_team_xg_from_stats(enriched, 1.0) is True
    assert enriched["xg_source"] == "team_season_xg"


def test_attach_display_fields_on_apply():
    enriched = _base_enriched()
    fixture = {"teams": {"home": {"name": "H"}, "away": {"name": "A"}}}
    out = apply_scraped_xg_to_enriched(fixture, "EPL", enriched)
    assert out.get("xg_confidence_tier") in ("proxy", "usable", "thin", "strong")
    assert out.get("xg_source_hint")
