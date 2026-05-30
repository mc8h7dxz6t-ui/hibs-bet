"""League-specific model calibration profiles.

These are intentionally small, transparent adjustments. They do not replace the
model; they nudge outputs for league context and expose the assumption to the UI.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple


_DEFAULT = {
    "label": "Balanced club profile",
    "description": "Standard club-league calibration with normal home advantage and market anchoring.",
    "draw_target": 0.255,
    "upset_risk": 0.08,
    "market_anchor": 0.08,
    "value_margin_extra": 0.0,
}

_PROFILES: Dict[str, Dict[str, Any]] = {
    "SCOTLAND": {
        "label": "Scottish Premiership profile",
        "description": "Adds caution for table mismatches and thinner xG coverage outside the strongest feeds.",
        "draw_target": 0.265,
        "upset_risk": 0.10,
        "market_anchor": 0.10,
        "value_margin_extra": 0.006,
    },
    "SCOTLAND_CHAMP": {
        "label": "Scottish lower-league profile",
        "description": "Higher variance and thinner data; value needs extra evidence.",
        "draw_target": 0.275,
        "upset_risk": 0.14,
        "market_anchor": 0.12,
        "value_margin_extra": 0.012,
    },
    "SCOTLAND_L1": {
        "label": "Scottish lower-league profile",
        "description": "Higher variance and thinner data; value needs extra evidence.",
        "draw_target": 0.275,
        "upset_risk": 0.15,
        "market_anchor": 0.12,
        "value_margin_extra": 0.014,
    },
    "SCOTLAND_L2": {
        "label": "Scottish lower-league profile",
        "description": "Higher variance and thinner data; value needs extra evidence.",
        "draw_target": 0.28,
        "upset_risk": 0.16,
        "market_anchor": 0.13,
        "value_margin_extra": 0.016,
    },
    "EPL": {
        "label": "Premier League profile",
        "description": "Strong market and table signal; longshot value is treated strictly.",
        "draw_target": 0.245,
        "upset_risk": 0.07,
        "market_anchor": 0.10,
        "value_margin_extra": 0.004,
    },
    "CHAMPIONSHIP": {
        "label": "Championship profile",
        "description": "Higher draw and upset rate than elite leagues; model confidence is slightly softened.",
        "draw_target": 0.275,
        "upset_risk": 0.13,
        "market_anchor": 0.10,
        "value_margin_extra": 0.01,
    },
    "LEAGUE_ONE": {
        "label": "English lower-league profile",
        "description": "Noisier table/form data; value requires stronger edge.",
        "draw_target": 0.28,
        "upset_risk": 0.15,
        "market_anchor": 0.11,
        "value_margin_extra": 0.014,
    },
    "LEAGUE_TWO": {
        "label": "English lower-league profile",
        "description": "Noisier table/form data; value requires stronger edge.",
        "draw_target": 0.285,
        "upset_risk": 0.16,
        "market_anchor": 0.11,
        "value_margin_extra": 0.016,
    },
    "FA_CUP": {
        "label": "Cup profile",
        "description": "Cup rotation and motivation variance; avoid forcing thin-value picks.",
        "draw_target": 0.255,
        "upset_risk": 0.18,
        "market_anchor": 0.12,
        "value_margin_extra": 0.018,
    },
    "SCOTTISH_CUP": {
        "label": "Cup profile",
        "description": "Cup rotation and motivation variance; avoid forcing thin-value picks.",
        "draw_target": 0.255,
        "upset_risk": 0.18,
        "market_anchor": 0.12,
        "value_margin_extra": 0.018,
    },
    "LEAGUE_CUP": {
        "label": "Cup profile",
        "description": "Cup rotation and motivation variance; avoid forcing thin-value picks.",
        "draw_target": 0.255,
        "upset_risk": 0.17,
        "market_anchor": 0.12,
        "value_margin_extra": 0.016,
    },
    "IRELAND_PREMIER": {
        "label": "League of Ireland profile",
        "description": "Smaller domestic league; thinner xG and more upset variance than UK top tiers.",
        "draw_target": 0.27,
        "upset_risk": 0.14,
        "market_anchor": 0.11,
        "value_margin_extra": 0.012,
    },
    "NORWAY_ELITESERIEN": {
        "label": "Eliteserien profile",
        "description": "Nordic summer league; moderate upset variance and thinner measured-xG than UK top tiers.",
        "draw_target": 0.265,
        "upset_risk": 0.12,
        "market_anchor": 0.10,
        "value_margin_extra": 0.010,
    },
    "FINLAND_VEIKKAUSLIIGA": {
        "label": "Veikkausliiga profile",
        "description": "Nordic summer league; moderate upset variance and thinner measured-xG than UK top tiers.",
        "draw_target": 0.27,
        "upset_risk": 0.13,
        "market_anchor": 0.10,
        "value_margin_extra": 0.011,
    },
    "DENMARK_SL": {
        "label": "Superliga profile",
        "description": "Nordic summer league; moderate upset variance and thinner measured-xG than UK top tiers.",
        "draw_target": 0.26,
        "upset_risk": 0.11,
        "market_anchor": 0.10,
        "value_margin_extra": 0.010,
    },
    "COUPE_DE_FRANCE": {
        "label": "Cup profile",
        "description": "Cup rotation and motivation variance; avoid forcing thin-value picks.",
        "draw_target": 0.255,
        "upset_risk": 0.18,
        "market_anchor": 0.12,
        "value_margin_extra": 0.018,
    },
    "DFB_POKAL": {
        "label": "Cup profile",
        "description": "Cup rotation and motivation variance; avoid forcing thin-value picks.",
        "draw_target": 0.255,
        "upset_risk": 0.17,
        "market_anchor": 0.12,
        "value_margin_extra": 0.016,
    },
    "COPPA_ITALIA": {
        "label": "Cup profile",
        "description": "Cup rotation and motivation variance; avoid forcing thin-value picks.",
        "draw_target": 0.255,
        "upset_risk": 0.17,
        "market_anchor": 0.12,
        "value_margin_extra": 0.016,
    },
    "COPA_DEL_REY": {
        "label": "Cup profile",
        "description": "Cup rotation and motivation variance; avoid forcing thin-value picks.",
        "draw_target": 0.255,
        "upset_risk": 0.17,
        "market_anchor": 0.12,
        "value_margin_extra": 0.016,
    },
    "UCL": {
        "label": "Elite Europe profile",
        "description": "Market and squad quality matter more; mismatch longshots need strong evidence.",
        "draw_target": 0.25,
        "upset_risk": 0.09,
        "market_anchor": 0.11,
        "value_margin_extra": 0.006,
    },
    "EUROPA_LEAGUE": {
        "label": "European cup profile",
        "description": "Travel and rotation variance; probability first, value second.",
        "draw_target": 0.255,
        "upset_risk": 0.13,
        "market_anchor": 0.11,
        "value_margin_extra": 0.012,
    },
    "UECL": {
        "label": "European cup profile",
        "description": "Travel and rotation variance; probability first, value second.",
        "draw_target": 0.26,
        "upset_risk": 0.15,
        "market_anchor": 0.12,
        "value_margin_extra": 0.014,
    },
    "WORLD_CUP": {
        "label": "International tournament profile",
        "description": "National-team samples are thinner; neutral venue, squads and market signal matter more.",
        "draw_target": 0.27,
        "upset_risk": 0.16,
        "market_anchor": 0.13,
        "value_margin_extra": 0.018,
    },
    "INTL_FRIENDLIES": {
        "label": "International friendlies profile",
        "description": "High squad rotation and thin samples — lean on market signal; value needs extra edge.",
        "draw_target": 0.28,
        "upset_risk": 0.18,
        "market_anchor": 0.15,
        "value_margin_extra": 0.022,
    },
    "EURO": {
        "label": "International tournament profile",
        "description": "National-team samples are thinner; neutral venue, squads and market signal matter more.",
        "draw_target": 0.27,
        "upset_risk": 0.16,
        "market_anchor": 0.13,
        "value_margin_extra": 0.018,
    },
}


def get_league_profile(league_code: str) -> Dict[str, Any]:
    code = (league_code or "").upper()
    base = dict(_DEFAULT)
    base.update(_PROFILES.get(code, {}))
    base["league_code"] = code
    return base


def _normalise(probs: Dict[str, float]) -> Dict[str, float]:
    total = sum(max(0.000001, float(probs.get(k, 0.0))) for k in ("home", "draw", "away"))
    if total <= 0:
        return {"home": 1 / 3, "draw": 1 / 3, "away": 1 / 3}
    return {k: max(0.000001, float(probs.get(k, 0.0))) / total for k in ("home", "draw", "away")}


def apply_league_probability_profile(
    probs: Dict[str, float], league_code: str
) -> Tuple[Dict[str, float], Dict[str, Any]]:
    """Return lightly calibrated probabilities plus transparent debug metadata."""
    profile = get_league_profile(league_code)
    out = _normalise(probs)
    original = dict(out)

    draw_target = float(profile.get("draw_target") or 0.255)
    upset_risk = float(profile.get("upset_risk") or 0.08)
    draw_weight = max(0.0, min(0.16, 0.06 + upset_risk * 0.35))
    new_draw = out["draw"] * (1.0 - draw_weight) + draw_target * draw_weight
    side_total_old = max(0.000001, out["home"] + out["away"])
    side_total_new = max(0.000001, 1.0 - new_draw)
    out["home"] = out["home"] / side_total_old * side_total_new
    out["away"] = out["away"] / side_total_old * side_total_new
    out["draw"] = new_draw

    fav = "home" if out["home"] >= out["away"] else "away"
    dog = "away" if fav == "home" else "home"
    if out[fav] >= 0.58 and upset_risk >= 0.13:
        shift = min(0.025, (upset_risk - 0.12) * 0.18)
        out[fav] -= shift
        out[dog] += shift * 0.65
        out["draw"] += shift * 0.35

    out = _normalise(out)
    debug = {
        "league_code": profile.get("league_code"),
        "label": profile.get("label"),
        "description": profile.get("description"),
        "draw_target": round(draw_target, 3),
        "upset_risk": round(upset_risk, 3),
        "market_anchor": round(float(profile.get("market_anchor") or 0.0), 3),
        "value_margin_extra": round(float(profile.get("value_margin_extra") or 0.0), 4),
        "applied": any(abs(out[k] - original[k]) >= 0.001 for k in ("home", "draw", "away")),
    }
    return out, debug


def value_margin_extra(league_code: str, data_quality_pct: float) -> float:
    """Extra edge required before showing value in noisy leagues / thin data."""
    profile = get_league_profile(league_code)
    extra = float(profile.get("value_margin_extra") or 0.0)
    if data_quality_pct < 70:
        extra += 0.012
    elif data_quality_pct < 82:
        extra += 0.006
    return max(0.0, min(0.04, extra))
