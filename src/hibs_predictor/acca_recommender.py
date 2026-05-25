"""
Stat-based accumulator recommendations from enriched fixture packets.

Uses existing model/value gates — no extra API calls. Legs must pass data-quality
and confidence bars; abstains rather than padding thin accas.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from hibs_predictor.assistant_context import (
    leg_slip_payload,
    pick_recommendation_line,
    value_require_data_pct,
)
from hibs_predictor.assistant_recommendations import (
    _collect_candidate_legs,
    _combined_decimal_odds,
    _joint_confidence_pct,
    _leg_score,
    _min_model_pct_for_key,
    _value_leg_from_display,
    build_detailed_leg_rationale,
    is_analyzable,
)
from hibs_predictor.assistant_recommendations import _match_label as _packet_match_label
from hibs_predictor.fixture_utils import is_finished_fixture

_DISCLAIMER = (
    "Research-only acca suggestions from live fixture snapshots — not financial advice. "
    "Combined probabilities assume independent legs. 18+ gamble responsibly."
)
_INDEPENDENCE_NOTE = (
    "Combined probability treats legs as independent — correlated markets "
    "(e.g. BTTS + Over 2.5) may differ in reality."
)

_ALLOWED_MARKETS = frozenset(
    {
        "home_win",
        "away_win",
        "draw",
        "btts_yes",
        "btts_no",
        "over_25",
        "over_15",
        "over_35",
    }
)
_CORRELATED_MARKETS = frozenset({"btts_yes", "btts_no", "over_25", "over_15", "over_35"})


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def acca_recommender_enabled() -> bool:
    raw = os.getenv("HIBS_ACCA_RECOMMENDER", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def acca_max_legs() -> int:
    return max(2, min(10, _env_int("HIBS_ACCA_MAX_LEGS", 6)))


def _strip_md(text: str) -> str:
    return re.sub(r"\*\*", "", text).strip()


def _leg_reasoning_snippet(packet: Dict[str, Any], leg: Dict[str, Any]) -> str:
    """One-line grounded reasoning from structured insight / pick menu."""
    si = packet.get("structured_insight") or {}
    for bullet in si.get("rationale") or []:
        if bullet:
            return _strip_md(str(bullet))[:220]
    line = pick_recommendation_line(
        packet,
        market_key=leg.get("market_key"),
        odds=leg.get("odds"),
        model_pct=leg.get("model_pct"),
    )
    if line:
        return _strip_md(line)[:220]
    detailed = build_detailed_leg_rationale(packet, leg, max_bullets=1)
    if detailed:
        return _strip_md(detailed[0])[:220]
    mp = leg.get("model_pct")
    if mp is not None:
        return f"Model {mp}% on {leg.get('market_label') or leg.get('market_key')}."
    return "Priced leg from current fixture snapshot."


def _leg_passes_value_gate(packet: Dict[str, Any], leg: Dict[str, Any]) -> bool:
    """Require adequate DQ and a defensible model/value read — abstain on thin/no-value legs."""
    dq = packet.get("data_quality_pct")
    if dq is None or float(dq) < value_require_data_pct():
        return False
    if not is_analyzable(packet):
        return False
    odds = leg.get("odds")
    if odds is None or float(odds) <= 1.0:
        return False
    mk = leg.get("market_key") or ""
    if mk not in _ALLOWED_MARKETS:
        return False
    mp = leg.get("model_pct")
    if mp is None or float(mp) < _min_model_pct_for_key(mk):
        return False
    edge = leg.get("edge_pct")
    if edge is not None:
        return float(edge) >= 0.0
    if leg.get("is_value") or leg.get("recommended"):
        return True
    bc = packet.get("bet_confidence")
    floor = packet.get("bet_confidence_min_value")
    if bc is not None and floor is not None and float(bc) < float(floor):
        return False
    return float(mp) >= 58.0


def _best_leg_for_packet(packet: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Strongest eligible market on one fixture (1X2, BTTS, O/U only)."""
    candidates = _collect_candidate_legs(packet, allowed_keys=_ALLOWED_MARKETS)
    eligible = [leg for leg in candidates if _leg_passes_value_gate(packet, leg)]
    if not eligible:
        vl = _value_leg_from_display(packet)
        if vl and _leg_passes_value_gate(packet, vl):
            eligible = [vl]
    if not eligible:
        return None
    best = max(eligible, key=lambda x: float(x.get("score") or 0))
    return dict(best)


def _collect_eligible_legs(packets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One best leg per fixture, ranked by score."""
    legs: List[Dict[str, Any]] = []
    for pkt in packets:
        best = _best_leg_for_packet(pkt)
        if best:
            best["match"] = _packet_match_label(pkt)
            best["score"] = _leg_score(best)
            legs.append(best)
    legs.sort(key=lambda x: -float(x.get("score") or 0))
    return legs


def _market_category(market_key: str) -> str:
    if market_key in ("btts_yes", "btts_no"):
        return "btts"
    if market_key.startswith("over_"):
        return "goals"
    if market_key in ("home_win", "away_win", "draw"):
        return "result"
    return market_key


def _league_key(leg: Dict[str, Any]) -> str:
    return str(leg.get("league_name") or leg.get("league") or "unknown").strip().lower()


def _kickoff_bucket(leg: Dict[str, Any]) -> str:
    kt = leg.get("kickoff_time") or leg.get("date") or ""
    return str(kt)[:10] if kt else "unknown"


def _diversification_penalty(selected: List[Dict[str, Any]], candidate: Dict[str, Any]) -> float:
    """Lower is better — penalise same league + correlated market clusters."""
    penalty = 0.0
    cand_league = _league_key(candidate)
    cand_cat = _market_category(candidate.get("market_key") or "")
    cand_day = _kickoff_bucket(candidate)
    for leg in selected:
        if _league_key(leg) == cand_league:
            penalty += 4.0
            if _market_category(leg.get("market_key") or "") == cand_cat:
                penalty += 6.0
            if (
                cand_cat in _CORRELATED_MARKETS
                and _market_category(leg.get("market_key") or "") in _CORRELATED_MARKETS
                and _kickoff_bucket(leg) == cand_day
            ):
                penalty += 5.0
        if str(leg.get("kickoff_time") or "") == str(candidate.get("kickoff_time") or "") and leg.get("kickoff_time"):
            penalty += 2.0
    return penalty


def _select_diversified_legs(pool: List[Dict[str, Any]], count: int) -> List[Dict[str, Any]]:
    """Greedy pick: highest score minus correlation penalty vs already selected."""
    selected: List[Dict[str, Any]] = []
    used_fixtures: set = set()
    remaining = list(pool)
    while remaining and len(selected) < count:
        best_idx = -1
        best_val = -1e9
        for i, leg in enumerate(remaining):
            fid = leg.get("fixture_id")
            if fid in used_fixtures:
                continue
            base = float(leg.get("score") or leg.get("model_pct") or 0)
            val = base - _diversification_penalty(selected, leg)
            if val > best_val:
                best_val = val
                best_idx = i
        if best_idx < 0:
            break
        pick = remaining.pop(best_idx)
        selected.append(pick)
        used_fixtures.add(pick.get("fixture_id"))
    return selected


def _correlation_warnings(legs: List[Dict[str, Any]]) -> List[str]:
    warnings: List[str] = []
    if not legs:
        return warnings
    fids = [str(l.get("fixture_id")) for l in legs]
    if len(fids) != len(set(fids)):
        warnings.append("Same-match legs detected — accas should use one pick per fixture.")
    btts_by_league_day: Dict[Tuple[str, str], int] = defaultdict(int)
    goals_by_league_day: Dict[Tuple[str, str], int] = defaultdict(int)
    for leg in legs:
        league = _league_key(leg)
        day = _kickoff_bucket(leg)
        mk = leg.get("market_key") or ""
        if mk in ("btts_yes", "btts_no"):
            btts_by_league_day[(league, day)] += 1
        if mk.startswith("over_"):
            goals_by_league_day[(league, day)] += 1
    for (league, day), n in btts_by_league_day.items():
        if n >= 2:
            warnings.append(
                f"{n} BTTS legs in {league.upper()} on {day} — league goal environment may correlate."
            )
    for (league, day), n in goals_by_league_day.items():
        if n >= 2:
            warnings.append(
                f"{n} Over/Under legs in {league.upper()} on {day} — totals may move together."
            )
    thin = [
        l
        for l in legs
        if l.get("data_quality_pct") is not None and float(l["data_quality_pct"]) < value_require_data_pct()
    ]
    if thin:
        warnings.append(f"{len(thin)} leg(s) below {value_require_data_pct():.0f}% data-quality bar.")
    return warnings


def _combined_independent_prob_pct(legs: List[Dict[str, Any]]) -> Optional[float]:
    probs: List[float] = []
    for leg in legs:
        mp = leg.get("model_pct")
        if mp is None:
            return None
        probs.append(max(0.01, min(0.99, float(mp) / 100.0)))
    if not probs:
        return None
    joint = 1.0
    for p in probs:
        joint *= p
    return round(joint * 100, 2)


def _format_leg(packet: Dict[str, Any], leg: Dict[str, Any]) -> Dict[str, Any]:
    out = {
        "fixture_id": leg.get("fixture_id"),
        "home": leg.get("home") or packet.get("home"),
        "away": leg.get("away") or packet.get("away"),
        "match": leg.get("match") or _packet_match_label(packet),
        "league": leg.get("league_name") or leg.get("league") or packet.get("league_name") or packet.get("league"),
        "kickoff_time": leg.get("kickoff_time") or packet.get("kickoff_time"),
        "market_key": leg.get("market_key"),
        "market_label": leg.get("market_label") or leg.get("market_key"),
        "model_pct": leg.get("model_pct"),
        "odds": leg.get("odds"),
        "edge_pct": leg.get("edge_pct"),
        "implied_pct": leg.get("implied_pct"),
        "data_quality_pct": leg.get("data_quality_pct") or packet.get("data_quality_pct"),
        "bet_confidence": leg.get("bet_confidence") or packet.get("bet_confidence"),
        "is_value": bool(leg.get("is_value")),
        "reasoning": _leg_reasoning_snippet(packet, leg),
    }
    return leg_slip_payload(out)


def _fixture_goals(packet: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    """FT goals from live score fields on the packet — None when unknown."""
    h = packet.get("live_score_home")
    a = packet.get("live_score_away")
    if h is not None and a is not None:
        try:
            return int(h), int(a)
        except (TypeError, ValueError):
            pass
    ls = packet.get("live_score")
    if ls is not None and "-" in str(ls):
        parts = str(ls).strip().split("-", 1)
        try:
            return int(parts[0].strip()), int(parts[1].strip())
        except (TypeError, ValueError):
            pass
    return None, None


def market_leg_result_label(packet: Dict[str, Any], market_key: Optional[str]) -> str:
    """
    W / L / pending from finished fixture scores only.
    Does not invent results — requires FT (or equivalent) status and known goals.
    """
    if not packet or not is_finished_fixture(packet):
        return "pending"
    home_g, away_g = _fixture_goals(packet)
    if home_g is None or away_g is None:
        return "pending"
    mk = (market_key or "").strip().lower()
    total = home_g + away_g
    both_scored = home_g > 0 and away_g > 0
    if mk == "home_win":
        return "W" if home_g > away_g else "L"
    if mk == "away_win":
        return "W" if away_g > home_g else "L"
    if mk == "draw":
        return "W" if home_g == away_g else "L"
    if mk == "btts_yes":
        return "W" if both_scored else "L"
    if mk == "btts_no":
        return "W" if not both_scored else "L"
    if mk == "over_25":
        return "W" if total >= 3 else "L"
    if mk == "over_15":
        return "W" if total >= 2 else "L"
    if mk == "over_35":
        return "W" if total >= 4 else "L"
    return "pending"


def _annotate_acca_results(
    accas: List[Dict[str, Any]], packets_by_id: Dict[Any, Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Attach per-leg and acca-level results; partition winning vs other accas."""
    winning: List[Dict[str, Any]] = []
    other: List[Dict[str, Any]] = []
    for acca in accas:
        legs = acca.get("legs") or []
        for leg in legs:
            pkt = packets_by_id.get(leg.get("fixture_id")) or {}
            leg["result"] = market_leg_result_label(pkt, leg.get("market_key"))
        results = [leg.get("result") for leg in legs]
        settled = [r for r in results if r in ("W", "L")]
        if settled and len(settled) == len(results) and all(r == "W" for r in settled):
            acca["all_legs_won"] = True
            acca["is_winning"] = True
            winning.append(acca)
        else:
            acca["all_legs_won"] = False if any(r == "L" for r in results) else None
            acca["is_winning"] = False
            other.append(acca)
        reasons = [str(leg.get("reasoning") or "").strip() for leg in legs]
        acca["brief_summary"] = next((r for r in reasons if r), acca.get("name") or "")
    return winning, other


def _build_acca_candidate(
    name: str,
    acca_type: str,
    legs: List[Dict[str, Any]],
    packets_by_id: Dict[Any, Dict[str, Any]],
    *,
    min_legs: int = 2,
) -> Optional[Dict[str, Any]]:
    if len(legs) < min_legs:
        return None
    formatted = [_format_leg(packets_by_id.get(leg.get("fixture_id"), {}), leg) for leg in legs]
    combined_odds = _combined_decimal_odds(formatted)
    if combined_odds is None:
        return None
    combined_prob = _combined_independent_prob_pct(formatted)
    joint_conf = _joint_confidence_pct(formatted)
    warnings = _correlation_warnings(formatted)
    return {
        "name": name,
        "type": acca_type,
        "leg_count": len(formatted),
        "legs": formatted,
        "combined_odds": combined_odds,
        "combined_prob_pct": combined_prob,
        "joint_confidence_pct": joint_conf,
        "independence_note": _INDEPENDENCE_NOTE,
        "warnings": warnings,
        "disclaimer": _DISCLAIMER,
    }


def build_acca_recommendations(packets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build structured acca candidates (2-fold, 3-fold, acca of the day).

    Returns empty accas when insufficient eligible legs — never pads with thin data.
    """
    if not acca_recommender_enabled():
        return {
            "enabled": False,
            "accas": [],
            "eligible_leg_count": 0,
            "message": "Acca recommender disabled (HIBS_ACCA_RECOMMENDER=0).",
            "disclaimer": _DISCLAIMER,
        }

    pool = _collect_eligible_legs(packets)
    packets_by_id = {p.get("id"): p for p in packets}
    max_legs = acca_max_legs()
    accas: List[Dict[str, Any]] = []

    defs = [
        ("High-confidence 2-fold", "fold_2", 2, 2),
        ("High-confidence 3-fold", "fold_3", 3, 3),
        (f"Acca of the day ({min(max_legs, max(3, len(pool)))}-leg)", "acca_of_day", 3, max_legs),
        ("Mixed 4-fold", "fold_4", 3, 4),
        ("Mixed 5-fold", "fold_5", 4, 5),
        ("Mixed 6-fold", "fold_6", 5, 6),
    ]
    seen_sigs: set = set()

    for name, acca_type, min_n, target_n in defs:
        n = min(target_n, len(pool), max_legs)
        if n < min_n:
            continue
        picked = _select_diversified_legs(pool, n)
        if len(picked) < min_n:
            continue
        if acca_type == "acca_of_day":
            display_name = f"Acca of the day ({len(picked)}-fold)"
        else:
            display_name = name
        built = _build_acca_candidate(display_name, acca_type, picked, packets_by_id, min_legs=min_n)
        if not built:
            continue
        sig = tuple((str(l.get("fixture_id")), str(l.get("market_key"))) for l in built.get("legs") or [])
        if sig in seen_sigs:
            continue
        seen_sigs.add(sig)
        accas.append(built)

    value_pool = [leg for leg in pool if leg.get("edge_pct") is not None and float(leg["edge_pct"]) >= 3.0]
    if len(value_pool) >= 2:
        vpicked = _select_diversified_legs(value_pool, min(3, len(value_pool)))
        vbuilt = _build_acca_candidate(
            f"Value edge {len(vpicked)}-fold",
            "value_edge",
            vpicked,
            packets_by_id,
            min_legs=2,
        )
        if vbuilt:
            sig = tuple((str(l.get("fixture_id")), str(l.get("market_key"))) for l in vbuilt.get("legs") or [])
            if sig not in seen_sigs:
                seen_sigs.add(sig)
                accas.append(vbuilt)

    mixed_pool = sorted(pool, key=lambda x: -float(x.get("score") or 0))
    for target in (4, 5, 6):
        if target > max_legs or len(mixed_pool) < 3:
            continue
        mpicked = _select_diversified_legs(mixed_pool, min(target, len(mixed_pool), max_legs))
        if len(mpicked) < 3:
            continue
        cats = {_market_category(l.get("market_key") or "") for l in mpicked}
        if len(cats) < 2:
            continue
        mbuilt = _build_acca_candidate(
            f"Mixed markets {len(mpicked)}-fold",
            f"mixed_{len(mpicked)}",
            mpicked,
            packets_by_id,
            min_legs=3,
        )
        if not mbuilt:
            continue
        sig = tuple((str(l.get("fixture_id")), str(l.get("market_key"))) for l in mbuilt.get("legs") or [])
        if sig in seen_sigs:
            continue
        seen_sigs.add(sig)
        accas.append(mbuilt)
        break

    message = None
    if not accas:
        message = (
            f"No acca legs cleared value/data gates ({len(pool)} fixture legs scanned). "
            "Refresh when more fixtures have book prices and model support."
        )

    winning_accas, other_accas = _annotate_acca_results(accas, packets_by_id)
    ordered_accas = winning_accas + other_accas

    return {
        "enabled": True,
        "accas": ordered_accas,
        "winning_accas": winning_accas,
        "other_accas": other_accas,
        "eligible_leg_count": len(pool),
        "max_legs": max_legs,
        "value_data_pct_gate": value_require_data_pct(),
        "message": message,
        "disclaimer": _DISCLAIMER,
    }
