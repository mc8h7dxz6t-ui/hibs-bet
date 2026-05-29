"""Odds-ratio de-vig and DQ-aware blending."""

from hibs_predictor.odds_devig import blend_probs_toward_anchor, odds_ratio_devig_probs


def test_odds_ratio_devig_sums_to_one():
    fair = odds_ratio_devig_probs({"home": 2.1, "draw": 3.4, "away": 3.8})
    assert abs(sum(fair.values()) - 1.0) < 1e-6
    assert fair["home"] > fair["away"]


def test_blend_probs_toward_anchor():
    model = {"home": 0.5, "draw": 0.25, "away": 0.25}
    anchor = {"home": 0.4, "draw": 0.3, "away": 0.3}
    out = blend_probs_toward_anchor(model, anchor, 0.5, keys=("home", "draw", "away"))
    assert abs(out["home"] - 0.45) < 0.01
