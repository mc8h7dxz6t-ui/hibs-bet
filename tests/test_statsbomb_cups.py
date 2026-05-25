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
    assert "COUPE_DE_FRANCE" in sb.STATSBOMB_CUP_LEAGUES
    assert "FA_CUP" in sb.STATSBOMB_CUP_LEAGUES


def test_cup_fixture_gets_statsbomb_xg_source(monkeypatch):
    """Cup leagues tag xg_source from supplemental proxy without STATSBOMB_LIGHT."""
    monkeypatch.delenv("HIBS_ENABLE_STATSBOMB_LIGHT", raising=False)
    monkeypatch.delenv("HIBS_MAX_DATA", raising=False)
    monkeypatch.setenv("HIBS_SCRAPE_XG", "1")
    monkeypatch.setenv("HIBS_ENABLE_FOTMOB_XG", "0")

    from hibs_predictor.scraped_xg import apply_scraped_xg_to_enriched

    fixture = {
        "teams": {"home": {"name": "Real Madrid"}, "away": {"name": "Barcelona"}},
    }
    def _enriched() -> dict:
        return {
            "xg_home": 1.1,
            "xg_away": 1.0,
            "xg_source": "goals_proxy",
            "league_factor": 1.0,
            "supplemental": {
                "statsbomb_open_team_proxy": {
                    "home": {"ok": True, "gf_pg": 2.1, "ga_pg": 0.9, "matches_used": 5},
                    "away": {"ok": True, "gf_pg": 1.8, "ga_pg": 1.0, "matches_used": 4},
                }
            },
        }

    out = apply_scraped_xg_to_enriched(fixture, "UCL", _enriched())
    assert out["xg_source"] == "statsbomb_goals_proxy_xg"

    out_domestic = apply_scraped_xg_to_enriched(fixture, "BELGIUM_FIRST", _enriched())
    assert out_domestic["xg_source"] == "goals_proxy"
