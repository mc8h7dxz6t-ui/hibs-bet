"""StatsBomb open-data cup league mapping."""

from unittest.mock import patch

from hibs_predictor.scrapers import statsbomb_open as sb


def test_latest_open_season_meta_ucl():
    comps = [
        {
            "competition_id": 16,
            "season_id": 4,
            "competition_name": "Champions League",
            "country_name": "Europe",
            "season_name": "2018/2019",
            "competition_gender": "male",
            "competition_youth": False,
        },
        {
            "competition_id": 99,
            "season_id": 1,
            "competition_name": "Champions League",
            "country_name": "Europe",
            "season_name": "2010/2011",
            "competition_gender": "male",
            "competition_youth": False,
        },
    ]
    with patch.object(sb, "load_competitions", return_value=comps):
        meta = sb.latest_open_season_meta("UCL")
    assert meta.get("competition_id") == 16
    assert "2018" in str(meta.get("season_name"))


def test_cup_leagues_in_open_map():
    assert "UCL" in sb.STATSBOMB_LEAGUE_OPEN
    assert "WORLD_CUP" in sb.STATSBOMB_LEAGUE_OPEN
    assert "UCL" in sb.STATSBOMB_CUP_LEAGUES
