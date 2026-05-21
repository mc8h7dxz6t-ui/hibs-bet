"""
Structured acca / betslip leg review for the assistant API.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from hibs_predictor.assistant_context import (
    _implied_pct,
    _form_snippet,
    _xg_snippet,
    data_sources_summary,
    pick_recommendation_line,
    thin_data_flags,
    value_require_data_pct,
)
from hibs_predictor.assistant_recommendations import _match_label
from hibs_predictor.match_insight import _value_bet_key

_DISCLAIMER = (
    "Leg-by-leg research view only — not financial advice. "
    "Stake conservatively; 18+ gamble responsibly."
)


def _find_packet(
    packets: List[Dict[str, Any]],
    leg: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    fid = leg.get("fixture_id")
    if fid is not None and str(fid).strip():
        for p in packets:
            if str(p.get("id")) == str(fid):
                return p
    home = (leg.get("home") or "").strip().lower()
    away = (leg.get("away") or "").strip().lower()
    if home and away:
        for p in packets:
            if (p.get("home") or "").strip().lower() == home and (p.get("away") or "").strip().lower() == away:
                return p
    return None


def _menu_item(packet: Dict[str, Any], market_key: Optional[str], market_label: Optional[str]) -> Optional[Dict[str, Any]]:
    menu = packet.get("pick_menu") or []
    if market_key:
        hit = next((m for m in menu if m.get("key") == market_key), None)
        if hit:
            return hit
    if market_label:
        ml = market_label.strip().lower()
        for m in menu:
            if (m.get("label") or "").strip().lower() == ml:
                return m
    outcome_map = {
        "home": "home_win",
        "draw": "draw",
        "away": "away_win",
    }
    oc = (market_key or market_label or "").strip().lower()
    if oc in outcome_map:
        return next((m for m in menu if m.get("key") == outcome_map[oc]), None)
    return None


def _leg_model_edge(
    packet: Dict[str, Any],
    leg: Dict[str, Any],
    item: Optional[Dict[str, Any]],
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    model_pct = leg.get("model_pct")
    if model_pct is None and item:
        model_pct = item.get("model_pct")
    if model_pct is None and packet:
        ps = packet.get("probability_scores") or {}
        mk = leg.get("market_key") or (item.get("key") if item else None)
        pct_map = {
            "home_win": ps.get("home_win_pct"),
            "draw": ps.get("draw_pct"),
            "away_win": ps.get("away_win_pct"),
            "btts_yes": ps.get("btts_pct"),
            "over_25": ps.get("over25_pct"),
            "over_15": ps.get("over15_pct"),
            "over_35": ps.get("over35_pct"),
        }
        if mk in pct_map:
            model_pct = pct_map[mk]
    odds = leg.get("odds")
    if odds is None and item:
        odds = item.get("odds")
    implied = _implied_pct(odds)
    edge = None
    if model_pct is not None and implied is not None:
        edge = round(float(model_pct) - float(implied), 1)
    vb_key = _value_bet_key(leg.get("market_key") or "")
    for v in packet.get("value_bets_display") or []:
        if vb_key and (v.get("market_key") == vb_key or v.get("key") == vb_key):
            edge = v.get("edge_pct")
            if model_pct is None:
                model_pct = v.get("model_probability_pct")
            if implied is None:
                implied = v.get("implied_probability_pct")
            break
    if edge is None and item and item.get("edge_pct") is not None:
        edge = item.get("edge_pct")
    return (
        float(model_pct) if model_pct is not None else None,
        implied,
        float(edge) if edge is not None else None,
    )


def _verdict(flags: List[str], edge: Optional[float], model_pct: Optional[float]) -> str:
    if "thin_data" in flags or "missing_form" in flags or "odds_only" in flags:
        return "caution"
    if edge is not None and edge >= 4.0:
        return "strong"
    if model_pct is not None and model_pct >= 58.0 and (edge is None or edge >= 0):
        return "strong"
    if edge is not None and edge < 0:
        return "weak"
    return "neutral"


def _leg_paragraph(
    packet: Dict[str, Any],
    leg: Dict[str, Any],
    *,
    model_pct: Optional[float],
    implied: Optional[float],
    edge: Optional[float],
    flags: List[str],
) -> str:
    match = _match_label(packet) if packet else f"{leg.get('home', '?')} vs {leg.get('away', '?')}"
    market = leg.get("market_label") or leg.get("market_key") or leg.get("outcome") or "selection"
    dq = (packet or {}).get("data_quality_pct")
    parts: List[str] = [f"{match} — {market}."]
    if dq is not None:
        parts.append(f"Data coverage {dq}%")
        if float(dq) < value_require_data_pct():
            parts.append(f"(below {value_require_data_pct():.0f}% value threshold)")
        parts.append(".")
    bet_conf = (packet or {}).get("bet_confidence")
    if bet_conf is not None:
        parts.append(f" Bet confidence {bet_conf:.0f}%")
        floor = (packet or {}).get("bet_confidence_min_value")
        if floor is not None and float(bet_conf) < float(floor):
            parts.append(" (below value confidence floor)")
        parts.append(".")
    if packet:
        parts.append(_xg_snippet(packet) + ".")
        form = _form_snippet(packet)
        if "n/a" not in form.lower():
            parts.append(f"Form: {form}.")
        parts.append(f"Sources: {data_sources_summary(packet)}.")
    if model_pct is not None:
        parts.append(f"Model probability {model_pct:.1f}%")
        if implied is not None:
            parts.append(f" vs best-line implied {implied:.1f}%")
        if edge is not None:
            parts.append(f" ({'+' if edge >= 0 else ''}{edge:.1f}% edge)")
        parts.append(".")
    elif leg.get("odds"):
        impl = _implied_pct(leg.get("odds"))
        if impl is not None:
            parts.append(f"Line implied {impl:.1f}% @ {leg['odds']}.")
    pick_line = pick_recommendation_line(
        packet,
        market_key=leg.get("market_key"),
        odds=leg.get("odds"),
        model_pct=model_pct,
    ) if packet else None
    if pick_line:
        parts.append(f"Model read: {pick_line.replace('**', '')}.")
    si = (packet or {}).get("structured_insight") or {}
    if si.get("pick") and si.get("mode") == "prediction":
        parts.append(f"Structured lean: {si['pick']}")
        if si.get("confidence_pct") is not None:
            parts.append(f" ({si['confidence_pct']}% conf.)")
        parts.append(".")
    if flags:
        parts.append(" Flags: thin data — caution (" + ", ".join(flags) + ").")
    elif edge is not None and edge >= 3:
        parts.append(" Leg looks statistically supported vs the price.")
    elif edge is not None and edge < 0:
        parts.append(" Leg is weak vs implied — price may be short.")
    else:
        parts.append(" Mixed signal — size down if stacking.")
    return " ".join(parts)


def review_acca_legs(
    legs: List[Dict[str, Any]],
    packets: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Review each betslip leg; returns structured paragraphs + flags."""
    if not legs:
        return {
            "legs": [],
            "summary": "No legs supplied — add selections on the acca builder first.",
            "disclaimer": _DISCLAIMER,
        }

    reviewed: List[Dict[str, Any]] = []
    strong_n = caution_n = 0

    for leg in legs:
        packet = _find_packet(packets, leg)
        item = _menu_item(packet, leg.get("market_key"), leg.get("market_label")) if packet else None
        mk = leg.get("market_key") or (item.get("key") if item else None)
        if mk and not leg.get("market_key"):
            leg = {**leg, "market_key": mk}
        model_pct, implied, edge = _leg_model_edge(packet or {}, leg, item)
        flags = thin_data_flags(packet) if packet else ["fixture_not_found"]
        verdict = _verdict(flags, edge, model_pct)
        if verdict == "strong":
            strong_n += 1
        if verdict == "caution" or flags:
            caution_n += 1
        reviewed.append(
            {
                "fixture_id": leg.get("fixture_id"),
                "home": leg.get("home") or (packet or {}).get("home"),
                "away": leg.get("away") or (packet or {}).get("away"),
                "match": _match_label(packet) if packet else f"{leg.get('home', '?')} vs {leg.get('away', '?')}",
                "market_key": mk,
                "market_label": leg.get("market_label") or (item.get("label") if item else mk),
                "odds": leg.get("odds") or (item.get("odds") if item else None),
                "model_pct": model_pct,
                "implied_pct": implied,
                "edge_pct": edge,
                "data_quality_pct": (packet or {}).get("data_quality_pct"),
                "bet_confidence": (packet or {}).get("bet_confidence"),
                "has_value_dual_agree": (packet or {}).get("has_value_dual_agree"),
                "xg_snippet": _xg_snippet(packet) if packet else None,
                "form_snippet": _form_snippet(packet) if packet else None,
                "data_sources": data_sources_summary(packet) if packet else None,
                "flags": flags,
                "thin_data": "thin_data" in flags,
                "verdict": verdict,
                "paragraph": _leg_paragraph(
                    packet or {},
                    leg,
                    model_pct=model_pct,
                    implied=implied,
                    edge=edge,
                    flags=flags,
                ),
            }
        )

    n = len(reviewed)
    summary = (
        f"Reviewed {n} leg{'s' if n != 1 else ''}: "
        f"{strong_n} with supportive model reads, {caution_n} flagged for thin or missing data."
    )
    if caution_n == n and n:
        summary += " Consider dropping or reducing stake until coverage improves."

    return {
        "legs": reviewed,
        "summary": summary,
        "disclaimer": _DISCLAIMER,
        "value_data_pct_gate": value_require_data_pct(),
    }
