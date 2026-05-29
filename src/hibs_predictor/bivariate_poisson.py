"""Bivariate Poisson goals model: X = Z1 + Z3, Y = Z2 + Z3 (shared low-score correlation)."""

from __future__ import annotations

import math
import os
from typing import Dict, Tuple


def _poisson_pmf(lam: float, k: int) -> float:
    if k < 0 or lam < 0:
        return 0.0
    try:
        return (math.exp(-lam) * (lam**k)) / math.factorial(k)
    except (OverflowError, ValueError):
        return 0.0


def shared_lambda_fraction() -> float:
    try:
        return max(0.0, min(0.45, float(os.getenv("HIBS_BIV_POISSON_SHARED_FRAC", "0.22"))))
    except ValueError:
        return 0.22


def lambdas_from_marginals(lam_h: float, lam_a: float) -> Tuple[float, float, float]:
    """Split marginal attack rates into independent + shared Poisson components."""
    lam_h = max(0.08, float(lam_h))
    lam_a = max(0.08, float(lam_a))
    frac = shared_lambda_fraction()
    lam3 = frac * min(lam_h, lam_a)
    lam1 = max(0.05, lam_h - lam3)
    lam2 = max(0.05, lam_a - lam3)
    return lam1, lam2, lam3


def score_probability(lam1: float, lam2: float, lam3: float, h: int, a: int) -> float:
    """P(home goals = h, away goals = a) under bivariate Poisson."""
    if h < 0 or a < 0:
        return 0.0
    z_max = min(h, a)
    total = 0.0
    for z in range(z_max + 1):
        total += (
            _poisson_pmf(lam1, h - z)
            * _poisson_pmf(lam2, a - z)
            * _poisson_pmf(lam3, z)
        )
    return max(0.0, total)


def btts_yes_probability(lam_h: float, lam_a: float, *, max_goals: int = 10) -> float:
    lam1, lam2, lam3 = lambdas_from_marginals(lam_h, lam_a)
    p_both = 0.0
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            if h >= 1 and a >= 1:
                p_both += score_probability(lam1, lam2, lam3, h, a)
    return max(0.02, min(0.98, p_both))


def over_goals_probability(lam_h: float, lam_a: float, line: float, *, max_goals: int = 10) -> float:
    """P(total goals > line) for half-goal lines (e.g. 2.5)."""
    lam1, lam2, lam3 = lambdas_from_marginals(lam_h, lam_a)
    max_total = int(math.floor(float(line)))
    p_at_most = 0.0
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            if h + a <= max_total:
                p_at_most += score_probability(lam1, lam2, lam3, h, a)
    over = 1.0 - min(1.0, p_at_most)
    return max(0.02, min(0.98, over))


def joint_home_win_and_btts(lam_h: float, lam_a: float, *, max_goals: int = 10) -> float:
    lam1, lam2, lam3 = lambdas_from_marginals(lam_h, lam_a)
    s = 0.0
    for h in range(1, max_goals + 1):
        for a in range(1, max_goals + 1):
            if h > a:
                s += score_probability(lam1, lam2, lam3, h, a)
    return max(0.001, min(0.95, s))


def joint_draw_and_btts(lam_h: float, lam_a: float, *, max_goals: int = 10) -> float:
    lam1, lam2, lam3 = lambdas_from_marginals(lam_h, lam_a)
    s = 0.0
    for g in range(1, max_goals + 1):
        s += score_probability(lam1, lam2, lam3, g, g)
    return max(0.001, min(0.95, s))


def joint_away_win_and_btts(lam_h: float, lam_a: float, *, max_goals: int = 10) -> float:
    lam1, lam2, lam3 = lambdas_from_marginals(lam_h, lam_a)
    s = 0.0
    for h in range(1, max_goals + 1):
        for a in range(1, max_goals + 1):
            if a > h:
                s += score_probability(lam1, lam2, lam3, h, a)
    return max(0.001, min(0.95, s))


def side_market_probs(lam_h: float, lam_a: float) -> Dict[str, float]:
    """BTTS, O/U lines, and score+BTTS joints from bivariate Poisson."""
    btts = btts_yes_probability(lam_h, lam_a)
    over15 = over_goals_probability(lam_h, lam_a, 1.5)
    over25 = over_goals_probability(lam_h, lam_a, 2.5)
    over35 = over_goals_probability(lam_h, lam_a, 3.5)
    return {
        "btts_yes": btts,
        "btts_no": max(0.02, min(0.98, 1.0 - btts)),
        "over15": over15,
        "under15": max(0.02, min(0.98, 1.0 - over15)),
        "over25": over25,
        "under25": max(0.02, min(0.98, 1.0 - over25)),
        "over35": over35,
        "under35": max(0.02, min(0.98, 1.0 - over35)),
        "home_and_btts": joint_home_win_and_btts(lam_h, lam_a),
        "draw_and_btts": joint_draw_and_btts(lam_h, lam_a),
        "away_and_btts": joint_away_win_and_btts(lam_h, lam_a),
    }
