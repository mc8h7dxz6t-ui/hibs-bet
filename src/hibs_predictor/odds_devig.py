"""Odds-ratio (OR) de-vig for multi-outcome books (1X2, BTTS, etc.)."""

from __future__ import annotations

from typing import Dict, Mapping, Optional


def implied_prob(decimal_odds: float) -> float:
    if decimal_odds <= 1.0:
        return 0.0
    return 1.0 / float(decimal_odds)


def odds_ratio_devig_probs(odds: Mapping[str, float]) -> Dict[str, float]:
    """
    Odds-ratio de-vig: fair probability per outcome from decimal prices.

    Falls back to proportional normalization when fewer than two valid prices exist.
    """
    implied: Dict[str, float] = {}
    for key, raw in odds.items():
        try:
            price = float(raw)
        except (TypeError, ValueError):
            continue
        if price <= 1.0:
            continue
        implied[str(key)] = implied_prob(price)
    if not implied:
        return {}
    keys = list(implied.keys())
    n = len(keys)
    if n == 1:
        return {keys[0]: 1.0}
    if n == 2:
        s = sum(implied.values())
        return {k: implied[k] / s for k in keys} if s > 0 else implied

    out: Dict[str, float] = {}
    for k in keys:
        others_prod = 1.0
        for j in keys:
            if j != k:
                others_prod *= implied[j]
        if others_prod > 0:
            out[k] = implied[k] / (others_prod ** (1.0 / (n - 1)))
        else:
            out[k] = implied[k]
    total = sum(out.values())
    if total <= 0:
        s = sum(implied.values())
        return {k: implied[k] / s for k in keys} if s > 0 else {}
    return {k: max(1e-9, v / total) for k, v in out.items()}


def blend_probs_toward_anchor(
    model: Mapping[str, float],
    anchor: Mapping[str, float],
    anchor_weight: float,
    *,
    keys: Optional[tuple] = None,
) -> Dict[str, float]:
    """Convex blend model → anchor, renormalized."""
    w = max(0.0, min(1.0, float(anchor_weight)))
    use_keys = keys or tuple(model.keys())
    if not use_keys or not anchor:
        return dict(model)
    out: Dict[str, float] = {}
    for k in use_keys:
        m = float(model.get(k, 0.0))
        a = float(anchor.get(k, 0.0))
        out[k] = m * (1.0 - w) + a * w
    total = sum(out.values())
    if total <= 0:
        return dict(model)
    return {k: max(1e-9, v / total) for k, v in out.items()}
