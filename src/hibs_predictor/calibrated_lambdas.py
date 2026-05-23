"""xG-style λ calibration: table-rank Elo proxy + league home-advantage multipliers.

Inspired by transparent Poisson+xG pipelines; ranks come from API/SoccerStats standings when present.
"""

import os
from typing import Any, Dict, Optional, Tuple

# League code → (home λ multiplier, away λ multiplier). Defaults ~ top-league empirical HA.
_HOME_AWAY_BY_LEAGUE: Dict[str, Tuple[float, float]] = {
    "EPL": (1.08, 0.94),
    "LA_LIGA": (1.10, 0.92),
    "SERIE_A": (1.07, 0.95),
    "BUNDESLIGA": (1.06, 0.96),
    "LIGUE_1": (1.09, 0.93),
    "CHAMPIONSHIP": (1.05, 0.96),
    "SCOTLAND": (1.06, 0.95),
    "UCL": (1.04, 0.97),
    "EUROPA_LEAGUE": (1.04, 0.97),
    "UECL": (1.04, 0.97),
}

_DEFAULT_HA = (1.06, 0.96)


def _elo_alpha() -> float:
    try:
        return float(os.getenv("HIBS_ELO_ALPHA", "0.18"))
    except ValueError:
        return 0.18


def _rank_to_elo_proxy(rank: Optional[int]) -> Optional[float]:
    """Map table rank to a pseudo-Elo (higher = stronger). None if unknown."""
    if rank is None:
        return None
    try:
        r = int(rank)
    except (TypeError, ValueError):
        return None
    if r < 1 or r > 40:
        return None
    return 1650.0 - float(r) * 12.0


def league_home_away_multipliers(league_code: str) -> Tuple[float, float]:
    if not league_code:
        return _DEFAULT_HA
    return _HOME_AWAY_BY_LEAGUE.get(league_code.upper(), _DEFAULT_HA)


def calibrated_match_lambdas(
    xg_home: float,
    xg_away: float,
    league_code: str,
    home_position: Optional[Dict[str, Any]] = None,
    away_position: Optional[Dict[str, Any]] = None,
) -> Tuple[float, float, Dict[str, Any]]:
    """
    Return (λ_home, λ_away, debug) after optional Elo-style rank scaling and league HA.

    Elo step (when both ranks known): λ_h *= (1 + α Δ/400), λ_a *= (1 − α Δ/400), Δ = elo_h − elo_a.
    """
    lam_h = max(0.12, float(xg_home))
    lam_a = max(0.12, float(xg_away))
    dbg: Dict[str, Any] = {"league_code": league_code or "", "alpha": _elo_alpha(), "elo_applied": False}

    hp = home_position or {}
    ap = away_position or {}
    eh = _rank_to_elo_proxy(hp.get("position"))
    ea = _rank_to_elo_proxy(ap.get("position"))
    alpha = _elo_alpha()
    if eh is not None and ea is not None and alpha > 0:
        d_elo = eh - ea
        lam_h *= 1.0 + alpha * (d_elo / 400.0)
        lam_a *= 1.0 - alpha * (d_elo / 400.0)
        dbg["elo_applied"] = True
        dbg["delta_elo_proxy"] = round(d_elo, 1)

    mh, ma = league_home_away_multipliers(league_code or "")
    lam_h *= mh
    lam_a *= ma
    dbg["home_ha_mult"] = mh
    dbg["away_ha_mult"] = ma

    lam_h = max(0.12, min(4.2, lam_h))
    lam_a = max(0.12, min(4.2, lam_a))
    dbg["lambda_home"] = round(lam_h, 3)
    dbg["lambda_away"] = round(lam_a, 3)
    return lam_h, lam_a, dbg
