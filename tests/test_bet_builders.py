"""Pro bet builder: multiple ranked options per fixture."""

from __future__ import annotations

from hibs_predictor.assistant_recommendations import build_bet_builder_suggestions


def _rich_packet() -> dict:
    return {
        "id": 10,
        "home": "Hibs",
        "away": "Hearts",
        "league": "SCOTLAND",
        "league_name": "Scottish Premiership",
        "kickoff_time": "15:00",
        "data_quality_pct": 90.0,
        "data_quality": {"score_pct": 90, "blocks": []},
        "home_recent_n": 5,
        "away_recent_n": 5,
        "structured_insight": {"mode": "prediction", "match": "Hibs vs Hearts", "pick": "BTTS Yes"},
        "pick_menu": [
            {"key": "btts_yes", "label": "BTTS Yes", "model_pct": 64.0, "odds": 1.8},
            {"key": "over_25", "label": "Over 2.5", "model_pct": 61.0, "odds": 1.95},
            {"key": "over_15", "label": "Over 1.5", "model_pct": 74.0, "odds": 1.35},
            {"key": "home_or_draw", "label": "Home or Draw", "model_pct": 68.0, "odds": 1.42},
            {"key": "home_win", "label": "Home Win", "model_pct": 52.0, "odds": 2.1},
            {"key": "under_25", "label": "Under 2.5", "model_pct": 60.0, "odds": 1.9},
        ],
        "probability_scores": {"xg_home": 1.6, "xg_away": 1.2},
        "home_position": {"position": 4},
        "away_position": {"position": 7},
        "home_form_summary": {"played": 5, "wins": 3, "draws": 1, "losses": 1},
        "away_form_summary": {"played": 5, "wins": 2, "draws": 1, "losses": 2},
    }


def test_bet_builders_multiple_per_fixture():
    builders = build_bet_builder_suggestions([_rich_packet()], max_per_fixture=3)
    assert len(builders) >= 2
    assert all(b.get("fixture_id") == 10 for b in builders)
    assert builders[0].get("builders_for_fixture", 0) >= 2
    ranks = sorted(b.get("builder_rank") for b in builders)
    assert ranks == list(range(1, len(builders) + 1))


def test_bet_builders_global_limit_does_not_starve_other_fixtures():
    p1 = _rich_packet()
    p2 = {**_rich_packet(), "id": 11, "home": "Celtic", "away": "Rangers"}
    builders = build_bet_builder_suggestions([p1, p2], limit=4, max_per_fixture=2)
    by_fid = {10: 0, 11: 0}
    for b in builders:
        by_fid[b["fixture_id"]] = by_fid.get(b["fixture_id"], 0) + 1
    assert by_fid[10] >= 1
    assert by_fid[11] >= 1
