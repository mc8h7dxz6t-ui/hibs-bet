"""Dixon–Coles low-score correlation on Poisson 1X2."""

import os

import pytest


def test_dixon_coles_increases_draw_vs_independent_poisson(monkeypatch):
    monkeypatch.setenv("HIBS_DIXON_COLES_RHO", "-0.12")
    from hibs_predictor.betting_engine import BettingEngine

    engine = BettingEngine({})
    dc = engine._poisson_match_probs(1.25, 1.05)
    monkeypatch.setenv("HIBS_DIXON_COLES_RHO", "0")
    plain = engine._poisson_match_probs(1.25, 1.05)
    assert dc["draw"] > plain["draw"]
    assert abs(sum(dc.values()) - 1.0) < 1e-6


def test_dixon_coles_disabled_when_rho_zero(monkeypatch):
    monkeypatch.setenv("HIBS_DIXON_COLES_RHO", "0")
    from hibs_predictor.betting_engine import BettingEngine

    engine = BettingEngine({})
    a = engine._poisson_match_probs(1.4, 0.9)
    b = engine._poisson_match_probs(1.4, 0.9)
    assert a == b


def test_dixon_coles_tau_identity():
    from hibs_predictor.betting_engine import BettingEngine

    assert BettingEngine._dixon_coles_tau(2, 3, 1.2, 1.0, -0.1) == 1.0
