"""Scraper health classification and probes (mocked)."""

from unittest.mock import patch

import requests

from hibs_predictor.scraper_health import scraper_error_code, scraper_row
from hibs_predictor.scrapers import fotmob_client as fm


def test_scraper_error_code_blocked_vs_error():
    assert scraper_error_code(ok=False, blocked=True) == "BLOCKED"
    assert scraper_error_code(ok=False, http_status=403) == "BLOCKED"
    assert scraper_error_code(ok=False, http_status=404) == "ERROR"
    assert scraper_error_code(ok=False, deferred=True) == "DEFERRED"
    assert scraper_error_code(ok=False, layout_broken=True) == "LAYOUT_BROKEN"
    assert scraper_error_code(ok=True) is None


def test_scraper_row_maps_fotmob_404_to_error():
    row = scraper_row(
        sid="fotmob",
        label="FotMob",
        ms=12.0,
        ok=False,
        error="HTTP 404",
        http_status=404,
    )
    assert row["error_code"] == "ERROR"


def test_probe_matches_api_http_404_hint():
    resp = requests.Response()
    resp.status_code = 404
    err = requests.HTTPError("404", response=resp)
    with patch("hibs_predictor.scrapers.fotmob_client.fetch_matches_for_date", side_effect=err):
        pr = fm.probe_matches_api()
    assert pr["ok"] is False
    assert pr.get("http_status") == 404
    assert "api/data/matches" in (pr.get("error") or "")


def test_gather_health_fotmob_uses_error_not_layout_on_404():
    with patch(
        "hibs_predictor.scrapers.fotmob_client.probe_matches_api",
        return_value={"ok": False, "http_status": 404, "error": "HTTP 404", "league_count": 0},
    ):
        from hibs_predictor.health_probe import gather_health

        h = gather_health()
    fot = next(s for s in h["scrapers"] if s["id"] == "fotmob")
    assert fot["error_code"] == "ERROR"
