"""Bivariate Poisson side markets (BTTS / O-U)."""

from hibs_predictor.bivariate_poisson import (
    btts_yes_probability,
    lambdas_from_marginals,
    score_probability,
    side_market_probs,
)


def test_bivariate_score_grid_sums_reasonably():
    lam1, lam2, lam3 = lambdas_from_marginals(1.3, 1.1)
    total = 0.0
    for h in range(8):
        for a in range(8):
            total += score_probability(lam1, lam2, lam3, h, a)
    assert 0.85 < total < 1.05


def test_bivariate_btts_higher_with_shared_component():
    low = btts_yes_probability(1.0, 1.0)
    high = btts_yes_probability(1.6, 1.5)
    assert high > low


def test_side_market_probs_keys():
    m = side_market_probs(1.25, 1.05)
    for k in ("btts_yes", "over25", "home_and_btts"):
        assert 0.0 < m[k] < 1.0
