"""Eliteserien / Veikkausliiga coverage wiring."""

from datetime import datetime, timezone

from hibs_predictor.match_insight import _ODDS_ONLY_LEAGUE_DEFAULT
from hibs_predictor.scrapers.fbref_scottish_xg import FBREF_SCHEDULE_EXTRA, SCHEDULE_XG_LEAGUE_CODES
from hibs_predictor.season import CALENDAR_YEAR_LEAGUES, fbref_season_labels, season_candidates


def test_norway_in_fetch_and_fbref_schedule():
    assert "NORWAY_ELITESERIEN" in CALENDAR_YEAR_LEAGUES
    assert "NORWAY_ELITESERIEN" in FBREF_SCHEDULE_EXTRA
    assert "NORWAY_ELITESERIEN" in SCHEDULE_XG_LEAGUE_CODES
    assert "FINLAND_VEIKKAUSLIIGA" in FBREF_SCHEDULE_EXTRA


def test_norway_not_default_odds_only():
    assert "NORWAY_ELITESERIEN" not in _ODDS_ONLY_LEAGUE_DEFAULT
    assert "FINLAND_VEIKKAUSLIIGA" not in _ODDS_ONLY_LEAGUE_DEFAULT


def test_calendar_season_candidates_may_2026():
    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    seasons = season_candidates(now, league_code="NORWAY_ELITESERIEN")
    assert seasons[0] == 2026
    assert 2025 in seasons


def test_fixture_fetch_season_jul_league_may_2026():
    from hibs_predictor.web import _fixture_fetch_season_candidates

    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    seasons = _fixture_fetch_season_candidates(
        "PL", "2026-05-20", "2026-05-25", now, league_code="EPL"
    )
    assert seasons[0] == 2025
    assert 2026 not in seasons[:1]


def test_fixture_fetch_season_nordic_may_2026():
    from hibs_predictor.web import _fixture_fetch_season_candidates

    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    seasons = _fixture_fetch_season_candidates(
        None, "2026-05-20", "2026-05-25", now, league_code="NORWAY_ELITESERIEN"
    )
    assert seasons[0] == 2026


def test_fbref_calendar_season_label():
    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    labels = fbref_season_labels("NORWAY_ELITESERIEN", now)
    assert labels[0] == "2026"
    assert "2025" in labels


def test_odds_api_sport_keys():
    from hibs_predictor.api_clients import OddsApiClient

    assert OddsApiClient.SPORT_KEYS["NORWAY_ELITESERIEN"] == "soccer_norway_eliteserien"
    assert OddsApiClient.SPORT_KEYS["FINLAND_VEIKKAUSLIIGA"] == "soccer_finland_veikkausliiga"
    assert OddsApiClient.SPORT_KEYS["SCOTLAND"] == "soccer_spl"
    assert OddsApiClient.SPORT_KEYS["CHAMPIONSHIP"] == "soccer_efl_champ"
    assert "soccer_england_efl_championship" in OddsApiClient.SPORT_KEY_FALLBACKS["CHAMPIONSHIP"]
