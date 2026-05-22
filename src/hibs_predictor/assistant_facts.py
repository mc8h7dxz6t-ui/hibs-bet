"""
Ground-truth helpers for the betting assistant — only fields present on live packets.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Set


def _min_data_pct() -> float:
    try:
        return float(os.getenv("HIBS_ASSISTANT_MIN_DATA_PCT", "78.0"))
    except (TypeError, ValueError):
        return 78.0

INSUFFICIENT_DATA_LINE = (
    "Not enough live fixture data in this snapshot — I won't invent odds, BTTS%, or picks. "
    "Refresh the dashboard or widen the fetch window."
)

_BETTING_INTENTS = frozenset(
    {
        "best_acca",
        "suggest_legs",
        "acca_builder",
        "mixed_acca",
        "acca",
        "best_singles",
        "btts_acca",
        "multi_leg_btts",
        "win_btts_combo",
        "value",
        "bet_builder",
        "deep_dive",
    }
)


def _present(val: Any) -> bool:
    return val is not None and val != ""


def fact_from_packet(packet: Dict[str, Any]) -> Dict[str, Any]:
    """Extract only factual fields that exist on the packet — never default BTTS% or odds."""
    if not packet:
        return {}
    ps = packet.get("probability_scores") or {}
    si = packet.get("structured_insight") or {}
    facts: Dict[str, Any] = {}

    for key in (
        "id",
        "home",
        "away",
        "league",
        "league_name",
        "kickoff_time",
        "data_quality_pct",
        "trust_label",
        "xg_source",
        "bet_confidence",
        "has_value_dual_agree",
    ):
        if _present(packet.get(key)):
            facts[key] = packet[key]

    dq = packet.get("data_quality_pct")
    if dq is None:
        dq = (packet.get("data_quality") or {}).get("score_pct")
    if dq is not None:
        facts["data_quality_pct"] = dq

    for pct_key, out_key in (
        ("btts_pct", "btts_prob"),
        ("over15_pct", "over15_prob"),
        ("over25_pct", "over25_prob"),
        ("over35_pct", "over35_prob"),
        ("home_win_pct", "home_win_prob"),
        ("draw_pct", "draw_prob"),
        ("away_win_pct", "away_win_prob"),
    ):
        val = ps.get(pct_key)
        if val is not None:
            facts[out_key] = val
            if pct_key == "btts_pct":
                facts["btts_pct"] = val

    xh, xa = ps.get("xg_home"), ps.get("xg_away")
    if xh is not None or xa is not None:
        facts["xg_home"] = xh
        facts["xg_away"] = xa

    for side in ("home", "away"):
        fs = packet.get(f"{side}_form_summary") or {}
        if fs.get("played"):
            facts[f"{side}_form_summary"] = fs
        wdl = packet.get(f"{side}_last10_wdl")
        if _present(wdl):
            facts[f"{side}_last10_wdl"] = wdl
        rn = packet.get(f"{side}_recent_n")
        if rn is not None:
            facts[f"{side}_recent_n"] = rn

    injuries = packet.get("fixture_injuries") or []
    if injuries:
        facts["injuries_n"] = len(injuries)

    hp = packet.get("home_position") or {}
    ap = packet.get("away_position") or {}
    if hp.get("position") or hp.get("points") is not None:
        facts["home_position"] = hp
    if ap.get("position") or ap.get("points") is not None:
        facts["away_position"] = ap

    metrics = si.get("rationale_metrics")
    if isinstance(metrics, list) and metrics:
        facts["rationale_metrics"] = metrics

    lo = packet.get("line_odds") or {}
    best = packet.get("best_odds_1x2") or {}
    if lo or best:
        facts["line_odds"] = lo
        facts["best_odds_1x2"] = best

    return facts


def enrich_leg_with_packet_facts(leg: Dict[str, Any], packet: Dict[str, Any]) -> Dict[str, Any]:
    """Merge leg with packet facts; leg fields win when already set."""
    out = dict(leg)
    for key, val in fact_from_packet(packet).items():
        if out.get(key) is None and val is not None:
            out[key] = val
    if out.get("btts_pct") is None and out.get("btts_prob") is not None:
        out["btts_pct"] = out["btts_prob"]
    return out


def analyzable_packets(packets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from hibs_predictor.assistant_recommendations import is_analyzable

    return [p for p in (packets or []) if is_analyzable(p)]


def snapshot_team_names(packets: List[Dict[str, Any]]) -> Set[str]:
    names: Set[str] = set()
    for pkt in packets or []:
        for key in ("home", "away"):
            val = pkt.get(key)
            if _present(val):
                names.add(str(val).strip().lower())
    return names


def snapshot_refusal_line(
    packets: List[Dict[str, Any]],
    intent: str,
    params: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Global refusal when the snapshot cannot satisfy the requested intent."""
    _ = params
    if intent in ("help", "acca_review"):
        return None
    if not packets:
        return INSUFFICIENT_DATA_LINE
    eligible = analyzable_packets(packets)
    if intent in _BETTING_INTENTS and not eligible:
        return INSUFFICIENT_DATA_LINE
    if intent in ("btts_acca", "multi_leg_btts"):
        from hibs_predictor.assistant_recommendations import build_ranked_btts_legs

        if not build_ranked_btts_legs(packets, limit=1):
            return (
                "Not enough data for BTTS picks — no priced BTTS Yes legs cleared the "
                f"model and data bar (≥{_min_data_pct():.0f}% coverage)."
            )
    if intent == "win_btts_combo":
        combo_keys = frozenset({"home_and_btts", "away_and_btts", "draw_and_btts"})
        has_combo = False
        for pkt in eligible:
            menu = {str(m.get("key") or ""): m for m in (pkt.get("pick_menu") or [])}
            for key in combo_keys:
                item = menu.get(key)
                if item and item.get("odds") is not None and item.get("model_pct") is not None:
                    has_combo = True
                    break
            if has_combo:
                break
        if not has_combo:
            return (
                "Not enough data for win+BTTS combos — no priced combo markets on analyzable fixtures."
            )
    if intent in ("best_acca", "suggest_legs", "acca_builder", "mixed_acca") and intent != "deep_dive":
        from hibs_predictor.assistant_recommendations import _collect_candidate_legs

        priced = 0
        for pkt in eligible:
            if _collect_candidate_legs(pkt, allowed_keys=None):
                priced += 1
        if priced < 2 and intent in ("best_acca", "acca_builder", "mixed_acca"):
            return (
                "Not enough priced legs on today's card — need at least two analyzable fixtures "
                "with book prices and model support."
            )
    return None


def leg_has_required_fields(leg: Dict[str, Any], *, require_odds: bool = True) -> bool:
    if not leg.get("fixture_id") and not leg.get("home"):
        return False
    if leg.get("model_pct") is None:
        return False
    if require_odds and (leg.get("odds") is None or float(leg.get("odds") or 0) <= 1.0):
        return False
    dq = leg.get("data_quality_pct")
    if dq is not None and float(dq) < _min_data_pct():
        return False
    return True
