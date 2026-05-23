"""Tests for tournament / international focus mode."""

from __future__ import annotations

from datetime import date

import pytest

from hibs_predictor.config import ALL_LEAGUE_CODES
from hibs_predictor.tournament_focus import (
    INTERNATIONAL_FOCUS_LEAGUE_CODES,
    dashboard_default_region,
    effective_dashboard_league_order,
    league_codes_for_fetch,
    prioritize_fixtures_for_focus,
    tournament_focus_active,
    tournament_focus_mode,
)


@pytest.fixture(autouse=True)
def _clear_focus_env(monkeypatch):
    monkeypatch.delenv("HIBS_TOURNAMENT_FOCUS", raising=False)
    monkeypatch.delenv("HIBS_FOCUS_INTERNATIONAL", raising=False)
    monkeypatch.delenv("HIBS_TOURNAMENT_FOCUS_START", raising=False)
    monkeypatch.delenv("HIBS_TOURNAMENT_FOCUS_END", raising=False)


def test_focus_off_outside_auto_window(monkeypatch):
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2026, 5, 1),
    )
    assert tournament_focus_active() is False
    assert league_codes_for_fetch() == ALL_LEAGUE_CODES
    assert dashboard_default_region() == ""


def test_focus_auto_on_in_world_cup_window(monkeypatch):
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2026, 6, 10),
    )
    assert tournament_focus_mode() == "worldcup"
    assert tournament_focus_active() is True
    assert league_codes_for_fetch() == INTERNATIONAL_FOCUS_LEAGUE_CODES
    assert dashboard_default_region() == "international"
    assert effective_dashboard_league_order() == INTERNATIONAL_FOCUS_LEAGUE_CODES


def test_focus_env_worldcup_override(monkeypatch):
    monkeypatch.setenv("HIBS_TOURNAMENT_FOCUS", "worldcup")
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2025, 1, 1),
    )
    assert tournament_focus_mode() == "worldcup"
    assert league_codes_for_fetch() == INTERNATIONAL_FOCUS_LEAGUE_CODES


def test_focus_env_disabled_in_window(monkeypatch):
    monkeypatch.setenv("HIBS_TOURNAMENT_FOCUS", "0")
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2026, 6, 20),
    )
    assert tournament_focus_active() is False
    assert league_codes_for_fetch() == ALL_LEAGUE_CODES


def test_focus_international_shorthand(monkeypatch):
    monkeypatch.setenv("HIBS_FOCUS_INTERNATIONAL", "1")
    assert tournament_focus_mode() == "international"


def test_custom_date_window(monkeypatch):
    monkeypatch.setenv("HIBS_TOURNAMENT_FOCUS_START", "2026-04-01")
    monkeypatch.setenv("HIBS_TOURNAMENT_FOCUS_END", "2026-04-30")
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2026, 4, 15),
    )
    assert tournament_focus_active() is True


def test_international_comp_codes_in_focus_list():
    assert "WORLD_CUP" in INTERNATIONAL_FOCUS_LEAGUE_CODES
    assert "NATIONS_LEAGUE" in INTERNATIONAL_FOCUS_LEAGUE_CODES
    assert "EUROS" in INTERNATIONAL_FOCUS_LEAGUE_CODES
    assert "EPL" not in INTERNATIONAL_FOCUS_LEAGUE_CODES


def test_prioritize_fixtures_for_focus():
    fixtures = [
        {"league": "EPL", "kickoff_sort": "2026-06-10T12:00:00Z"},
        {"league": "WORLD_CUP", "kickoff_sort": "2026-06-11T15:00:00Z"},
        {"league": "NATIONS_LEAGUE", "kickoff_sort": "2026-06-10T18:00:00Z"},
    ]
    ordered = prioritize_fixtures_for_focus(fixtures, today=date(2026, 6, 10))
    assert [f["league"] for f in ordered] == ["WORLD_CUP", "NATIONS_LEAGUE", "EPL"]


def test_fotmob_nations_league_comp_mapping():
    from hibs_predictor.scrapers.fotmob_client import FOTMOB_LEAGUE_IDS, primary_league_id

    assert "NATIONS_LEAGUE" in FOTMOB_LEAGUE_IDS
    assert 9806 in FOTMOB_LEAGUE_IDS["NATIONS_LEAGUE"]
    assert primary_league_id("NATIONS_LEAGUE") == 9806
