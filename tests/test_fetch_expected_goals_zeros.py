"""_fetch_expected_goals must not treat API 0/0 as measured fixture xG."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from hibs_predictor.data_aggregator import DataAggregator


def test_fetch_expected_goals_ignores_api_zero_pair():
    agg = DataAggregator.__new__(DataAggregator)
    agg.cache = MagicMock()
    agg.cache.get.return_value = None
    agg._lambda_from_rates = MagicMock(return_value=(1.2, 1.1))
    agg.clients = {
        "api_sports": MagicMock(),
    }
    agg.clients["api_sports"].fetch_fixture.return_value = {
        "teams": {"home": {"id": 1}, "away": {"id": 2}},
        "statistics": [
            {
                "team": {"id": 1},
                "expected_goals": {"value": 0.0},
            },
            {
                "team": {"id": 2},
                "expected_goals": {"value": 0.0},
            },
        ],
    }
    with patch(
        "hibs_predictor.fixture_statistics_xg.fetch_fixture_statistics_xg",
        return_value=None,
    ):
        xh, xa, tag = agg._fetch_expected_goals(
            99,
            {"n": 5, "avg_gf": 1.4, "avg_ga": 1.1},
            {"n": 5, "avg_gf": 1.2, "avg_ga": 1.3},
            1.0,
            home_team_id=1,
            away_team_id=2,
        )
    assert tag in ("goals_proxy", "mixed_api_goals_proxy")
    assert xh > 0 and xa > 0
