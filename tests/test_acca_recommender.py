"""Tests for stat-based acca recommender."""

from __future__ import annotations

import os
from typing import Any, Dict, List

import pytest


def _packet(
    pid: int,
    home: str,
    away: str,
    *,
    league: str = "EPL",
    kickoff: str = "15:00",
    dq: float = 85.0,
    pick_menu: List[Dict[str, Any]] | None = None,
    structured_insight: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "id": pid,
        "home": home,
        "away": away,
        "league": league,
        "league_name": league,
        "kickoff_time": kickoff,
        "date": "2026-05-24T15:00:00",
        "data_quality_pct": dq,
        "home_recent_n": 5,
        "away_recent_n": 5,
        "bet_confidence": 74.0,
        "bet_confidence_min_value": 45.0,
        "structured_insight": structured_insight
        or {"mode": "prediction", "match": f"{home} vs {away}", "rationale": ["Open game profile."]},
        "probability_scores": {"btts_pct": 62, "over25_pct": 61, "home_win_pct": 55, "draw_pct": 25, "away_win_pct": 20},
        "pick_menu": pick_menu
        or [
            {
                "key": "btts_yes",
                "label": "BTTS Yes",
                "model_pct": 62.0,
                "odds": 1.85,
                "edge_pct": 4.0,
                "is_value": True,
            }
        ],
        "value_bets_display": [],
    }


@pytest.fixture
def rich_packets() -> List[Dict[str, Any]]:
    return [
        _packet(1, "Arsenal", "Chelsea", league="EPL", kickoff="12:30"),
        _packet(2, "Barcelona", "Sevilla", league="LA_LIGA", kickoff="17:00"),
        _packet(
            3,
            "Inter",
            "Milan",
            league="SERIE_A",
            kickoff="19:45",
            pick_menu=[
                {
                    "key": "over_25",
                    "label": "Over 2.5",
                    "model_pct": 60.0,
                    "odds": 1.95,
                    "edge_pct": 3.5,
                    "is_value": True,
                }
            ],
        ),
        _packet(
            4,
            "Bayern",
            "Dortmund",
            league="BUNDESLIGA",
            kickoff="14:30",
            pick_menu=[
                {
                    "key": "home_win",
                    "label": "Home Win",
                    "model_pct": 58.0,
                    "odds": 1.75,
                    "edge_pct": 1.0,
                    "recommended": True,
                }
            ],
        ),
    ]


def test_acca_recommender_builds_folds(rich_packets):
    from hibs_predictor.acca_recommender import build_acca_recommendations

    out = build_acca_recommendations(rich_packets)
    assert out["enabled"] is True
    assert out["eligible_leg_count"] >= 3
    names = [a["name"] for a in out["accas"]]
    assert any("2-fold" in n for n in names)
    assert any("3-fold" in n for n in names)
    assert any("Acca of the day" in n for n in names)


def test_acca_leg_structure(rich_packets):
    from hibs_predictor.acca_recommender import build_acca_recommendations

    acca = build_acca_recommendations(rich_packets)["accas"][0]
    leg = acca["legs"][0]
    for key in ("fixture_id", "match", "market_label", "model_pct", "odds", "reasoning", "slip"):
        assert key in leg
    assert acca["combined_odds"] > 1.0
    assert acca["combined_prob_pct"] is not None
    assert acca["independence_note"]


def test_one_leg_per_fixture(rich_packets):
    from hibs_predictor.acca_recommender import build_acca_recommendations

    for acca in build_acca_recommendations(rich_packets)["accas"]:
        fids = [l["fixture_id"] for l in acca["legs"]]
        assert len(fids) == len(set(fids))


def test_abstains_on_low_dq():
    from hibs_predictor.acca_recommender import build_acca_recommendations

    thin = [_packet(10, "A", "B", dq=60.0)]
    out = build_acca_recommendations(thin)
    assert out["eligible_leg_count"] == 0
    assert out["accas"] == []
    assert out["message"]


def test_abstains_on_negative_edge():
    from hibs_predictor.acca_recommender import build_acca_recommendations

    bad = [
        _packet(
            11,
            "X",
            "Y",
            pick_menu=[
                {"key": "btts_yes", "label": "BTTS Yes", "model_pct": 62.0, "odds": 1.5, "edge_pct": -2.0}
            ],
        )
    ]
    out = build_acca_recommendations(bad)
    assert out["eligible_leg_count"] == 0


def test_correlation_warning_same_league_btts():
    from hibs_predictor.acca_recommender import _correlation_warnings

    legs = [
        {"fixture_id": 1, "league": "EPL", "market_key": "btts_yes", "kickoff_time": "2026-05-24 15:00"},
        {"fixture_id": 2, "league": "EPL", "market_key": "btts_yes", "kickoff_time": "2026-05-24 17:30"},
    ]
    warnings = _correlation_warnings(legs)
    assert any("BTTS" in w for w in warnings)


def test_disabled_via_env(monkeypatch, rich_packets):
    from hibs_predictor.acca_recommender import build_acca_recommendations

    monkeypatch.setenv("HIBS_ACCA_RECOMMENDER", "0")
    out = build_acca_recommendations(rich_packets)
    assert out["enabled"] is False
    assert out["accas"] == []


def test_max_legs_env(monkeypatch, rich_packets):
    from hibs_predictor.acca_recommender import acca_max_legs, build_acca_recommendations

    monkeypatch.setenv("HIBS_ACCA_MAX_LEGS", "3")
    assert acca_max_legs() == 3
    accas = build_acca_recommendations(rich_packets)["accas"]
    assert accas
    assert max(a["leg_count"] for a in accas) <= 3
