"""FotMob client tests (mocked HTTP)."""

from datetime import date
from unittest.mock import MagicMock, patch

from hibs_predictor.scrapers import fotmob_client as fm


def test_fetch_matches_for_date_parses_leagues():
    payload = {
        "leagues": [
            {
                "id": 47,
                "primaryId": 47,
                "name": "Premier League",
                "matches": [
                    {
                        "id": 1,
                        "home": {"id": 10, "name": "Arsenal", "longName": "Arsenal"},
                        "away": {"id": 20, "name": "Chelsea", "longName": "Chelsea"},
                        "status": {"utcTime": "2025-05-18T14:00:00.000Z"},
                    }
                ],
            }
        ]
    }
    cache = MagicMock()
    cache.get.return_value = None
    with patch("hibs_predictor.scrapers.fotmob_client.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = payload
        out = fm.fetch_matches_for_date(date(2025, 5, 18), cache=cache)
    assert len(out.get("leagues") or []) == 1
    cache.set.assert_called_once()


def test_fixtures_for_league_filters_by_id():
    payload = {
        "leagues": [
            {"id": 47, "name": "Premier League", "matches": [{"id": 99, "home": {}, "away": {}}]},
            {"id": 999, "name": "Other", "matches": [{"id": 1, "home": {}, "away": {}}]},
        ]
    }
    cache = MagicMock()
    cache.get.return_value = payload
    rows = fm.fixtures_for_league("EPL", date(2025, 5, 18), date(2025, 5, 18), cache=cache)
    assert len(rows) == 1
    assert rows[0]["id"] == 99


def test_probe_matches_api_ok():
    with patch("hibs_predictor.scrapers.fotmob_client.fetch_matches_for_date") as mock_fetch:
        mock_fetch.return_value = {"leagues": [{}] * 8}
        pr = fm.probe_matches_api()
    assert pr["ok"] is True
    assert pr.get("http_status") == 200


UCL_XG_PAYLOAD = {
    "table": [
        {
            "data": {
                "table": {
                    "xg": [
                        {
                            "name": "Arsenal",
                            "shortName": "Arsenal",
                            "id": 9825,
                            "played": 8,
                            "xg": 20.0,
                            "xgConceded": 6.0,
                        },
                        {
                            "name": "Aston Villa",
                            "shortName": "Aston Villa",
                            "id": 10252,
                            "played": 8,
                            "xg": 14.0,
                            "xgConceded": 10.0,
                        },
                    ]
                }
            }
        }
    ]
}


def test_parse_league_xg_table():
    rows = fm.parse_league_xg_table(UCL_XG_PAYLOAD)
    assert len(rows) == 2
    assert rows[0]["name"] == "Arsenal"


def test_fixture_xg_from_league_table():
    rows = fm.parse_league_xg_table(UCL_XG_PAYLOAD)
    hp = fm.row_to_xg_profile(fm.find_team_xg_row(rows, "Arsenal FC"))
    ap = fm.row_to_xg_profile(fm.find_team_xg_row(rows, "Aston Villa"))
    assert hp and ap
    pair = fm.fixture_xg_from_profiles(hp, ap)
    assert pair
    xh, xa = pair
    assert 0.35 <= xh <= 3.2
    assert 0.35 <= xa <= 3.2


def test_fotmob_xg_enabled_cups_default():
    import os

    old = os.environ.pop("HIBS_ENABLE_FOTMOB_XG", None)
    old_md = os.environ.pop("HIBS_MAX_DATA", None)
    try:
        assert fm.fotmob_xg_enabled("UCL") is True
        assert fm.fotmob_xg_enabled("EPL") is False
        os.environ["HIBS_MAX_DATA"] = "1"
        assert fm.fotmob_xg_enabled("EPL") is True
    finally:
        if old is not None:
            os.environ["HIBS_ENABLE_FOTMOB_XG"] = old
        else:
            os.environ.pop("HIBS_ENABLE_FOTMOB_XG", None)
        if old_md is not None:
            os.environ["HIBS_MAX_DATA"] = old_md
        else:
            os.environ.pop("HIBS_MAX_DATA", None)


def test_cup_league_fallback_codes():
    assert fm.effective_xg_league_code("DFB_POKAL") == "BUNDESLIGA"
    assert fm.effective_xg_league_code("COPA_DEL_REY") == "LA_LIGA"
    assert fm.effective_xg_league_code("COPPA_ITALIA") == "SERIE_A"
    assert fm.fotmob_xg_enabled("DFB_POKAL") is True


def test_resolve_league_fixture_xg_mocked():
    cache = MagicMock()
    with patch("hibs_predictor.scrapers.fotmob_client.fotmob_xg_enabled", return_value=True):
        with patch(
            "hibs_predictor.scrapers.fotmob_client.fetch_league_data",
            return_value=UCL_XG_PAYLOAD,
        ):
            out = fm.resolve_league_fixture_xg("UCL", "Arsenal", "Aston Villa", cache=cache)
    assert out is not None
    xh, xa, meta = out
    assert xh > 0.04 and xa > 0.04
    assert meta.get("home_n") == 8

