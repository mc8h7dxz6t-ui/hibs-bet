"""The Odds API parsing, merge, and sport-key wiring."""

from __future__ import annotations

from hibs_predictor.api_clients import OddsApiClient
from hibs_predictor.data_aggregator import (
    _market_odds_from_side_parsed,
    _merge_market_odds_additive,
    _odds_api_apply_markets_to_book_row,
    _odds_event_matches_fixture,
    _parse_odds_api_event_side_markets,
)
from hibs_predictor.data_quality import _side_markets_pts


def _sample_odds_api_event() -> dict:
    return {
        "home_team": "Hibernian",
        "away_team": "Celtic",
        "commence_time": "2026-05-25T15:30:00Z",
        "bookmakers": [
            {
                "key": "williamhill",
                "title": "William Hill",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Hibernian", "price": 3.2},
                            {"name": "Celtic", "price": 2.1},
                            {"name": "Draw", "price": 3.4},
                        ],
                    },
                    {
                        "key": "totals",
                        "outcomes": [
                            {"name": "Over", "price": 1.85, "point": 2.5},
                            {"name": "Under", "price": 2.0, "point": 2.5},
                        ],
                    },
                    {
                        "key": "btts",
                        "outcomes": [
                            {"name": "Yes", "price": 1.72},
                            {"name": "No", "price": 2.05},
                        ],
                    },
                ],
            },
            {
                "key": "paddypower",
                "title": "Paddy Power",
                "markets": [
                    {
                        "key": "totals",
                        "outcomes": [
                            {"name": "Over", "price": 1.9, "point": 2.5},
                            {"name": "Under", "price": 1.95, "point": 2.5},
                        ],
                    }
                ],
            },
        ],
    }


def test_championship_and_scotland_sport_keys():
    assert OddsApiClient.SPORT_KEYS["CHAMPIONSHIP"] == "soccer_efl_champ"
    assert "soccer_england_efl_championship" in OddsApiClient.SPORT_KEY_FALLBACKS["CHAMPIONSHIP"]
    assert OddsApiClient.SPORT_KEYS["SCOTLAND"] == "soccer_spl"
    assert "soccer_scotland_premiership" in OddsApiClient.SPORT_KEY_FALLBACKS["SCOTLAND"]


def test_parse_odds_api_totals_and_btts():
    parsed = _parse_odds_api_event_side_markets(_sample_odds_api_event())
    assert parsed["over_2_5"] == 1.9
    assert parsed["under_2_5"] == 2.0
    assert parsed["btts_yes"] == 1.72
    assert parsed["btts_no"] == 2.05
    mo = _market_odds_from_side_parsed(parsed)
    assert mo["totals_2_5"]["over"] == 1.9
    assert mo["btts"]["yes"] == 1.72


def test_merge_market_odds_additive_keeps_api_sports():
    api = _market_odds_from_side_parsed(
        {"btts_yes": 1.8, "btts_no": 2.0, "over_2_5": 1.88, "under_2_5": 1.98}
    )
    oa = _market_odds_from_side_parsed({"over_2_5": 1.95, "under_2_5": 2.05})
    merged = _merge_market_odds_additive(api, oa)
    assert merged["btts"]["yes"] == 1.8
    assert merged["totals_2_5"]["over"] == 1.88
    assert merged["totals_2_5"]["under"] == 1.98


def test_merge_fills_missing_totals_from_odds_api():
    api = _market_odds_from_side_parsed({"btts_yes": 1.8})
    oa = _market_odds_from_side_parsed({"over_2_5": 1.9, "under_2_5": 2.0})
    merged = _merge_market_odds_additive(api, oa)
    assert merged["totals_2_5"]["over"] == 1.9
    assert merged["btts"]["yes"] == 1.8


def test_odds_api_book_row_includes_side_prices():
    event = _sample_odds_api_event()
    bm = event["bookmakers"][0]
    row: dict = {"bookmaker": "William Hill", "source": "the_odds_api"}
    side_acc: dict = {k: [] for k in ("btts_yes", "btts_no", "over_1_5", "under_1_5", "over_2_5", "under_2_5", "over_3_5", "under_3_5")}
    _odds_api_apply_markets_to_book_row(
        bm,
        row,
        home_display="Hibernian",
        away_display="Celtic",
        teams_swapped=False,
        side_acc=side_acc,
    )
    assert row["home"] == 3.2
    assert row["over_2_5"] == 1.85
    assert row["btts_yes"] == 1.72


def test_side_markets_dq_points_from_odds_api_totals_only():
    enriched = {
        "market_odds": _market_odds_from_side_parsed({"over_2_5": 1.9, "under_2_5": 2.0}),
        "line_odds": {},
    }
    assert _side_markets_pts(enriched) == 4.0


def test_odds_event_match_for_merge_fixture():
    fixture = {
        "home": "Hibernian",
        "away": "Celtic",
        "date": "2026-05-25T15:00:00+00:00",
    }
    assert _odds_event_matches_fixture(
        _sample_odds_api_event(), fixture, "Hibernian", "Celtic"
    )
