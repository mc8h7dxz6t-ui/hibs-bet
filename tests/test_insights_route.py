"""Regression: /insights must render when accas and monitor macros are used."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def insights_client():
    from hibs_predictor.web import app

    fixture = {
        "id": 1,
        "home": "Hibs",
        "away": "Hearts",
        "league": "Scottish Premiership",
        "league_name": "Scottish Premiership",
        "prediction": {
            "probabilities": {"home": 0.45, "draw": 0.28, "away": 0.27},
            "predicted_outcome": "home",
        },
    }
    bundle = {
        "total": 1,
        "value_bet_count": 0,
        "fetch_days": 7,
        "all": [fixture],
        "fixture_coverage": {"summary": "1 league", "reason": "test"},
    }
    with patch("hibs_predictor.web.fetch_all_fixtures", return_value=bundle):
        yield app.test_client()


def test_insights_route_returns_200(insights_client):
    response = insights_client.get("/insights")
    assert response.status_code == 200, response.get_data(as_text=True)[:400]


def test_insights_route_renders_acca_result_badges(insights_client):
    """Macros must be module-scoped, not inside extra_css block."""
    acca_rec = {
        "enabled": True,
        "accas": [
            {
                "name": "Test 2-fold",
                "legs": [
                    {
                        "fixture_id": 1,
                        "match": "Hibs vs Hearts",
                        "market_label": "Home win",
                        "result": "W",
                        "model_pct": 55.0,
                        "odds": 2.1,
                        "reasoning": "Home edge.",
                    }
                ],
                "combined_odds": 2.1,
            }
        ],
        "winning_accas": [],
        "other_accas": [],
        "eligible_leg_count": 1,
        "value_data_pct_gate": 70,
        "disclaimer": "Test only.",
    }
    with patch(
        "hibs_predictor.insights.build_insights",
        return_value={
            "summary": {},
            "top_probabilities": [],
            "value_opportunities": [],
            "data_quality_alerts": [],
            "angles": [],
            "bet_builders": [],
            "coverage": {
                "seasons": [],
                "counts": {"wired": 0, "experimental": 0, "planned": 0},
                "player_prop_note": "",
            },
            "trust_digest": {"labels": {}, "weak_fields": []},
            "avoid_watchlist": [],
            "audit": {"ok": True, "message": "No scored predictions yet.", "n_used_metrics": 0},
            "monitor": {"ok": True, "enabled": False, "yesterday": {}, "today": {}},
            "acca_recommendations": acca_rec,
        },
    ):
        response = insights_client.get("/insights")
    body = response.get_data(as_text=True)
    assert response.status_code == 200, body[:400]
    assert "result-badge-w" in body
