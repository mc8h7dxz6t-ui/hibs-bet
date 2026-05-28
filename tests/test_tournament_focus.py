"""Tests for tournament / international focus mode."""

from __future__ import annotations

from datetime import date

import pytest

from hibs_predictor.config import ALL_LEAGUE_CODES
from hibs_predictor.tournament_focus import (
    INTL_FRIENDLIES_CODE,
    INTERNATIONAL_FOCUS_LEAGUE_CODES,
    before_world_cup_start,
    dashboard_default_region,
    domestic_offseason_active,
    effective_dashboard_league_order,
    friendlies_fetch_window_days,
    friendlies_max_data_active,
    friendlies_max_data_profile_enabled,
    friendlies_window_active,
    international_focus_league_codes,
    league_codes_for_fetch,
    prioritize_fixtures_for_focus,
    active_competition_league_codes,
    summer_active_league_codes,
    tournament_focus_active,
    tournament_focus_mode,
)


@pytest.fixture(autouse=True)
def _clear_focus_env(monkeypatch):
    monkeypatch.delenv("HIBS_TOURNAMENT_FOCUS", raising=False)
    monkeypatch.delenv("HIBS_FOCUS_INTERNATIONAL", raising=False)
    monkeypatch.delenv("HIBS_TOURNAMENT_FOCUS_START", raising=False)
    monkeypatch.delenv("HIBS_TOURNAMENT_FOCUS_END", raising=False)
    monkeypatch.delenv("HIBS_TOURNAMENT_INCLUDE_FRIENDLIES", raising=False)
    monkeypatch.delenv("HIBS_FRIENDLIES_FOCUS_START", raising=False)
    monkeypatch.delenv("HIBS_DOMESTIC_OFFSEASON", raising=False)
    monkeypatch.delenv("HIBS_DOMESTIC_OFFSEASON_START", raising=False)
    monkeypatch.delenv("HIBS_DOMESTIC_OFFSEASON_END", raising=False)
    monkeypatch.delenv("HIBS_FETCH_ALL_DOMESTIC", raising=False)


def test_focus_off_outside_auto_window(monkeypatch):
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2026, 5, 1),
    )
    assert tournament_focus_active() is False
    assert league_codes_for_fetch() == ALL_LEAGUE_CODES
    assert dashboard_default_region() == ""


def test_focus_off_before_world_cup_starts(monkeypatch):
    """Late May 2026: WC + friendlies + Nordics + cup finals; no UK/Euro leagues; LOI omitted."""
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2026, 5, 31),
    )
    assert tournament_focus_active() is False
    assert domestic_offseason_active() is True
    codes = league_codes_for_fetch()
    assert "EPL" not in codes
    assert "LA_LIGA" not in codes
    assert "NORWAY_ELITESERIEN" in codes
    assert "FINLAND_VEIKKAUSLIIGA" in codes
    assert "DENMARK_SL" in codes
    assert "WORLD_CUP" in codes
    assert INTL_FRIENDLIES_CODE in codes
    assert codes[0] == "WORLD_CUP"
    assert "UCL" in codes
    assert "FA_CUP" in codes
    assert "IRELAND_PREMIER" not in codes
    assert codes == active_competition_league_codes()


def test_focus_off_before_opening_match_day(monkeypatch):
    """1–10 Jun: friendlies + Nordics; tournament focus starts 11 Jun (opening match)."""
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2026, 6, 10),
    )
    assert tournament_focus_active() is False
    assert domestic_offseason_active() is True
    assert "WORLD_CUP" in league_codes_for_fetch()


def test_focus_auto_on_at_opening_match(monkeypatch):
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2026, 6, 11),
    )
    assert tournament_focus_mode() == "worldcup"
    assert tournament_focus_active() is True


def test_focus_off_after_world_cup_ends(monkeypatch):
    """After WC window but before August: post-WC UK + European fetch (not intl-only)."""
    monkeypatch.delenv("HIBS_POST_WC_DOMESTIC_EUROPEAN", raising=False)
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2026, 7, 19),
    )
    assert tournament_focus_active() is False
    assert domestic_offseason_active() is True
    assert "EPL" in league_codes_for_fetch()
    assert "WORLD_CUP" not in league_codes_for_fetch()


def test_domestic_returns_august(monkeypatch):
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2026, 8, 1),
    )
    assert domestic_offseason_active() is False
    assert league_codes_for_fetch() == ALL_LEAGUE_CODES


def test_focus_auto_on_at_window_start(monkeypatch):
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2026, 6, 11),
    )
    assert tournament_focus_mode() == "worldcup"
    assert tournament_focus_active() is True
    assert league_codes_for_fetch() == international_focus_league_codes()
    assert dashboard_default_region() == "international"


def test_focus_auto_on_in_world_cup_window(monkeypatch):
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2026, 6, 20),
    )
    assert tournament_focus_mode() == "worldcup"
    assert tournament_focus_active() is True
    assert league_codes_for_fetch() == international_focus_league_codes()
    assert dashboard_default_region() == "international"
    assert effective_dashboard_league_order() == international_focus_league_codes()


def test_focus_auto_on_at_window_end(monkeypatch):
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2026, 7, 18),
    )
    assert tournament_focus_active() is True
    assert league_codes_for_fetch() == international_focus_league_codes()


def test_include_domestic_during_focus(monkeypatch):
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2026, 6, 20),
    )
    assert tournament_focus_active() is True
    assert league_codes_for_fetch(include_domestic=True) == ALL_LEAGUE_CODES
    assert effective_dashboard_league_order(include_domestic=True) != INTERNATIONAL_FOCUS_LEAGUE_CODES


def test_focus_env_worldcup_override(monkeypatch):
    monkeypatch.setenv("HIBS_TOURNAMENT_FOCUS", "worldcup")
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2025, 1, 1),
    )
    assert tournament_focus_mode() == "worldcup"
    assert league_codes_for_fetch() == international_focus_league_codes()


def test_focus_env_disabled_in_window(monkeypatch):
    """Explicit HIBS_TOURNAMENT_FOCUS=0 opt-out — rare override during auto window."""
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
    assert "EPL" not in INTERNATIONAL_FOCUS_LEAGUE_CODES
    codes = active_competition_league_codes(today=date(2026, 6, 15))
    assert "WORLD_CUP" in codes
    assert INTL_FRIENDLIES_CODE in codes
    assert "NATIONS_LEAGUE" not in codes
    assert "EUROS" not in codes


def test_intl_friendlies_dashboard_region():
    from hibs_predictor.config import league_dashboard_region

    assert league_dashboard_region(INTL_FRIENDLIES_CODE) == "international"


def test_nordic_dashboard_region():
    from hibs_predictor.config import league_dashboard_region

    assert league_dashboard_region("NORWAY_ELITESERIEN") == "nordic"
    assert league_dashboard_region("FINLAND_VEIKKAUSLIIGA") == "nordic"
    assert league_dashboard_region("DENMARK_SL") == "nordic"
    assert league_dashboard_region("IRELAND_PREMIER") == "ireland"


def test_summer_daily_league_helper():
    from hibs_predictor.tournament_focus import is_summer_daily_league, summer_daily_league_codes

    assert "DENMARK_SL" in summer_daily_league_codes()
    assert is_summer_daily_league("denmark_sl")
    assert not is_summer_daily_league("EPL")


def test_friendlies_in_worldcup_auto_window(monkeypatch):
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2026, 6, 15),
    )
    codes = international_focus_league_codes()
    assert INTL_FRIENDLIES_CODE in codes


def test_friendlies_off_outside_worldcup(monkeypatch):
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2026, 5, 1),
    )
    assert INTL_FRIENDLIES_CODE not in international_focus_league_codes()


def test_friendlies_fixture_window_days(monkeypatch):
    from hibs_predictor.web import _fixture_window_days_for_league

    monkeypatch.setenv("HIBS_FETCH_DAYS", "7")
    monkeypatch.setenv("HIBS_FRIENDLIES_FETCH_DAYS", "14")
    monkeypatch.setenv("HIBS_FRIENDLIES_FOCUS_START", "2026-05-20")
    monkeypatch.delenv("HIBS_TOURNAMENT_FOCUS", raising=False)
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc", lambda: date(2026, 5, 26)
    )
    assert _fixture_window_days_for_league("EPL") == 7
    assert _fixture_window_days_for_league("INTL_FRIENDLIES") == 14
    assert _fixture_window_days_for_league("DENMARK_SL") == 7


def test_post_wc_domestic_european_fetch_after_world_cup(monkeypatch):
    monkeypatch.delenv("HIBS_POST_WC_DOMESTIC_EUROPEAN", raising=False)
    monkeypatch.delenv("HIBS_TOURNAMENT_FOCUS", raising=False)
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2026, 7, 25),
    )
    from hibs_predictor.tournament_focus import (
        active_competition_league_codes,
        dashboard_default_region,
        post_wc_domestic_european_active,
    )

    assert post_wc_domestic_european_active() is True
    assert dashboard_default_region() == ""
    codes = active_competition_league_codes()
    assert "EPL" in codes
    assert "UCL" in codes
    assert "WORLD_CUP" not in codes


def test_friendlies_in_window_before_worldcup_focus(monkeypatch):
    """May 2026 international friendlies block — included in intl fetch lists."""
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2026, 5, 26),
    )
    assert friendlies_window_active() is True
    assert domestic_offseason_active() is True
    assert INTL_FRIENDLIES_CODE in international_focus_league_codes()
    assert dashboard_default_region() == ""


def test_friendlies_in_international_focus_mode(monkeypatch):
    monkeypatch.setenv("HIBS_FOCUS_INTERNATIONAL", "1")
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2026, 5, 26),
    )
    codes = league_codes_for_fetch()
    assert INTL_FRIENDLIES_CODE in codes


def test_world_cup_before_friendlies_in_fetch_order(monkeypatch):
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2026, 6, 15),
    )
    codes = active_competition_league_codes()
    assert codes.index("WORLD_CUP") < codes.index(INTL_FRIENDLIES_CODE)


def test_prioritize_friendlies_window_without_tournament_focus(monkeypatch):
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2026, 5, 26),
    )
    assert tournament_focus_active() is False
    fixtures = [
        {"league": "EPL", "kickoff_sort": "2026-05-26T12:00:00Z"},
        {"league": INTL_FRIENDLIES_CODE, "kickoff_sort": "2026-05-26T15:00:00Z"},
    ]
    ordered = prioritize_fixtures_for_focus(fixtures)
    assert ordered[0]["league"] == INTL_FRIENDLIES_CODE


def test_fotmob_world_cup_and_euros_mapping():
    from hibs_predictor.scrapers.fotmob_client import FOTMOB_LEAGUE_IDS

    assert 77 in FOTMOB_LEAGUE_IDS["WORLD_CUP"]
    assert 50 in FOTMOB_LEAGUE_IDS["EUROS"]


def test_prioritize_fixtures_for_focus():
    fixtures = [
        {"league": "EPL", "kickoff_sort": "2026-06-10T12:00:00Z"},
        {"league": "WORLD_CUP", "kickoff_sort": "2026-06-11T15:00:00Z"},
        {"league": INTL_FRIENDLIES_CODE, "kickoff_sort": "2026-06-11T14:00:00Z"},
        {"league": "FA_CUP", "kickoff_sort": "2026-06-10T18:00:00Z"},
    ]
    ordered = prioritize_fixtures_for_focus(fixtures, today=date(2026, 6, 20))
    assert [f["league"] for f in ordered] == [
        "WORLD_CUP",
        INTL_FRIENDLIES_CODE,
        "FA_CUP",
        "EPL",
    ]


def test_intl_friendlies_calendar_season():
    from hibs_predictor.season import season_candidates

    now = __import__("datetime").datetime(2026, 5, 26, 12, 0, tzinfo=__import__("datetime").timezone.utc)
    seasons = season_candidates(now, league_code=INTL_FRIENDLIES_CODE)
    assert seasons[0] == 2026


def test_fotmob_nations_league_comp_mapping():
    from hibs_predictor.scrapers.fotmob_client import FOTMOB_LEAGUE_IDS, primary_league_id

    assert "NATIONS_LEAGUE" in FOTMOB_LEAGUE_IDS
    assert 9806 in FOTMOB_LEAGUE_IDS["NATIONS_LEAGUE"]
    assert primary_league_id("NATIONS_LEAGUE") == 9806


def test_friendlies_max_data_active_pre_wc(monkeypatch):
    monkeypatch.setenv("HIBS_FRIENDLIES_MAX_DATA", "1")
    monkeypatch.setenv("HIBS_FRIENDLIES_FOCUS_START", "2026-05-20")
    monkeypatch.delenv("HIBS_TOURNAMENT_FOCUS", raising=False)
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2026, 5, 28),
    )
    assert friendlies_window_active() is True
    assert before_world_cup_start() is True
    assert friendlies_max_data_profile_enabled() is True
    assert friendlies_max_data_active(league_code=INTL_FRIENDLIES_CODE) is True
    assert friendlies_max_data_active(league_code="EPL") is False


def test_friendlies_max_data_inactive_after_wc_start(monkeypatch):
    monkeypatch.setenv("HIBS_FRIENDLIES_MAX_DATA", "1")
    monkeypatch.setenv("HIBS_TOURNAMENT_FOCUS_START", "2026-06-11")
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2026, 6, 12),
    )
    assert friendlies_max_data_profile_enabled() is False


def test_friendlies_fetch_window_days_respects_env(monkeypatch):
    monkeypatch.setenv("HIBS_FRIENDLIES_FETCH_DAYS", "14")
    monkeypatch.setenv("HIBS_FRIENDLIES_FOCUS_START", "2026-05-20")
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2026, 5, 28),
    )
    assert friendlies_fetch_window_days(dashboard_days=5) == 14


def test_dashboard_display_clips_friendlies_to_user_window(monkeypatch):
    """Friendlies may fetch 14d internally; dashboard upcoming list uses 5/7-day display window."""
    from datetime import datetime, timezone

    from hibs_predictor.web import (
        _finalize_fixture_bundle,
        _fixture_window_days_for_league,
        _fixtures_within_dashboard_window,
        app,
    )

    monkeypatch.setenv("HIBS_FETCH_DAYS", "5")
    monkeypatch.setenv("HIBS_FRIENDLIES_FETCH_DAYS", "14")
    monkeypatch.setenv("HIBS_FRIENDLIES_FOCUS_START", "2026-05-20")
    monkeypatch.setattr(
        "hibs_predictor.tournament_focus._today_utc",
        lambda: date(2026, 5, 28),
    )
    assert _fixture_window_days_for_league("INTL_FRIENDLIES") == 14

    now = datetime.now(timezone.utc)
    inside = (now + __import__("datetime").timedelta(days=2)).replace(
        hour=15, minute=0, second=0, microsecond=0
    )
    outside = (now + __import__("datetime").timedelta(days=10)).replace(
        hour=15, minute=0, second=0, microsecond=0
    )

    def _row(kickoff: datetime, fid: int) -> dict:
        iso = kickoff.isoformat()
        return {
            "fixture": {"id": fid, "date": iso},
            "date": iso,
            "league": "INTL_FRIENDLIES",
            "status": "NS",
            "teams": {"home": {"name": "A"}, "away": {"name": "B"}},
        }

    rows = [_row(inside, 1), _row(outside, 2)]
    with app.test_request_context("/?days=5"):
        clipped = _fixtures_within_dashboard_window(rows)
        bundle = _finalize_fixture_bundle(rows, include_domestic=False)

    assert len(clipped) == 1
    assert clipped[0]["fixture"]["id"] == 1
    assert bundle["fetch_days"] == 5
    assert bundle["total"] == 1
    assert len(bundle["upcoming"]) == 1
    assert len(bundle["all"]) == 2
