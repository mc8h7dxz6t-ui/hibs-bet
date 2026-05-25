"""Statistics xG API budget runs only when explicitly allowed (post core enrich)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from hibs_predictor.data_aggregator import DataAggregator


def test_fetch_expected_goals_skips_statistics_by_default():
    agg = DataAggregator.__new__(DataAggregator)
    agg.cache = MagicMock()
    agg.cache.get.return_value = None
    agg._lambda_from_rates = MagicMock(return_value=(1.2, 1.1))
    agg.clients = {"api_sports": MagicMock()}
    agg.clients["api_sports"].fetch_fixture.return_value = {
        "teams": {"home": {"id": 1}, "away": {"id": 2}},
        "statistics": [],
    }
    with patch(
        "hibs_predictor.fixture_statistics_xg.fetch_fixture_statistics_xg",
    ) as mock_stats:
        agg._fetch_expected_goals(
            99,
            {"n": 8, "avg_gf": 1.4, "avg_ga": 1.1},
            {"n": 8, "avg_gf": 1.2, "avg_ga": 1.3},
            1.0,
            allow_statistics_xg=False,
        )
    mock_stats.assert_not_called()


def test_fetch_expected_goals_allows_statistics_when_flagged():
    agg = DataAggregator.__new__(DataAggregator)
    agg.cache = MagicMock()
    agg.cache.get.return_value = None
    agg._lambda_from_rates = MagicMock(return_value=(1.2, 1.1))
    agg.clients = {"api_sports": MagicMock()}
    agg.clients["api_sports"].fetch_fixture.return_value = {
        "teams": {"home": {"id": 1}, "away": {"id": 2}},
        "statistics": [],
    }
    with patch(
        "hibs_predictor.fixture_statistics_xg.fetch_fixture_statistics_xg",
        return_value=(1.5, 1.2, "api_statistics_xg"),
    ) as mock_stats:
        xh, xa, tag = agg._fetch_expected_goals(
            99,
            {"n": 8, "avg_gf": 1.4, "avg_ga": 1.1},
            {"n": 8, "avg_gf": 1.2, "avg_ga": 1.3},
            1.0,
            allow_statistics_xg=True,
        )
    mock_stats.assert_called_once()
    assert tag == "api_statistics_xg"
    assert xh == 1.5 and xa == 1.2
