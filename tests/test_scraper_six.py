"""Six-scraper plan: supplemental annotation and DQ hooks."""

from __future__ import annotations

from hibs_predictor.data_quality import _supplemental_pts, compute_fixture_data_quality
from hibs_predictor.scrapers.scraper_six import (
    SCRAPER_SIX,
    annotate_scraper_six,
    scraper_six_enabled,
    scraper_six_plan_summary,
)


def test_scraper_six_plan_has_six_sources():
    assert len(SCRAPER_SIX) == 6
    ids = {s["id"] for s in SCRAPER_SIX}
    assert ids == {
        "api_football",
        "api_statistics_xg",
        "fotmob_xg",
        "understat",
        "soccerstats",
        "statsbomb",
    }


def test_annotate_mirrors_api_statistics_xg():
    sup: dict = {}
    enriched = {
        "xg_source": "api_statistics_xg",
        "xg_home": 1.55,
        "xg_away": 0.92,
        "teams": {"home": {"id": 1}, "away": {"id": 2}},
    }
    annotate_scraper_six(sup, enriched, "EPL")
    assert sup.get("api_statistics_xg") == {"xg_home": 1.55, "xg_away": 0.92}
    six = sup.get("scraper_six") or {}
    assert six.get("hits", 0) >= 1
    assert six["sources"]["api_statistics_xg"]["hit"] is True  # data present even if env off
    assert six["sources"]["api_football"]["hit"] is True


def test_supplemental_pts_api_statistics_xg(monkeypatch):
    monkeypatch.setenv("HIBS_FETCH_FIXTURE_STATISTICS_XG", "1")
    sup = {
        "api_statistics_xg": {"xg_home": 1.2, "xg_away": 1.0},
        "fotmob_xg": {"xg_home": 1.1, "xg_away": 0.9},
        "understat_light": {"xg_home": 1.1, "xg_away": 0.9},
        "scraper_six": {"hits": 4},
    }
    assert _supplemental_pts(sup) == 3.0


def test_scraper_six_enabled_statistics_xg(monkeypatch):
    monkeypatch.setenv("HIBS_FETCH_FIXTURE_STATISTICS_XG", "1")
    assert scraper_six_enabled("api_statistics_xg") is True
    monkeypatch.setenv("HIBS_FETCH_FIXTURE_STATISTICS_XG", "0")
    assert scraper_six_enabled("api_statistics_xg") is False


def test_proxy_xg_does_not_reach_full_xg_block():
    enriched = {
        "teams": {"home": {"id": 1}, "away": {"id": 2}},
        "fixture": {"id": 99},
        "home_recent_n": 8,
        "away_recent_n": 8,
        "home_stats": {"played": 20, "goals_for": 30, "goals_against": 20},
        "away_stats": {"played": 20, "goals_for": 25, "goals_against": 22},
        "home_position": {"position": 4},
        "away_position": {"position": 7},
        "xg_source": "statsbomb_goals_proxy_xg",
        "odds_available": True,
        "odds_home": 2.1,
        "odds_draw": 3.4,
        "odds_away": 3.2,
        "fixture_injuries": [],
        "supplemental": {
            "statsbomb_open_team_proxy": {"home": {"ok": True}, "away": {"ok": True}},
            "scraper_six": {"hits": 2},
        },
    }
    dq = compute_fixture_data_quality(enriched)
    xg_block = next(b for b in dq["blocks"] if b["key"] == "xg")
    assert xg_block["earned"] <= 11.0
    assert xg_block["earned"] < 18.0


def test_plan_summary_exposes_deferred():
    summary = scraper_six_plan_summary()
    assert len(summary["six"]) == 6
    assert summary["overflow"]["id"] == "sofascore"
    assert any(d["id"] == "footystats" for d in summary["deferred"])
