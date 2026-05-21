"""
Shared factual context lines for the betting assistant and acca reviewer.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from hibs_predictor.assistant_recommendations import (
    _exclusion_reason,
    _kickoff_display,
    _match_label,
    assistant_min_data_pct,
    assistant_min_form_matches,
)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def value_require_data_pct() -> float:
    return _env_float("HIBS_VALUE_REQUIRE_DATA_PCT", 78.0)


def _implied_pct(odds: Any) -> Optional[float]:
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if o <= 1.0:
        return None
    return round(100.0 / o, 1)


def data_sources_summary(packet: Dict[str, Any]) -> str:
    """Human-readable list of inputs that contributed to this fixture."""
    parts: List[str] = []
    xg = packet.get("xg_source")
    if xg and str(xg).lower() not in ("unknown", "none", ""):
        parts.append(f"xG: {xg}")
    hp = packet.get("home_position") or {}
    ap = packet.get("away_position") or {}
    if hp.get("source"):
        parts.append(f"{packet.get('home', 'Home')} table: {hp['source']}")
    if ap.get("source"):
        parts.append(f"{packet.get('away', 'Away')} table: {ap['source']}")
    sup = packet.get("supplemental") or {}
    if isinstance(sup, dict):
        if sup.get("understat") or sup.get("understat_xg"):
            parts.append("Understat supplemental")
        if sup.get("wikipedia") or sup.get("wiki_positions"):
            parts.append("Wikipedia positions")
        if sup.get("fbref"):
            parts.append("FBref")
        if sup.get("statsbomb"):
            parts.append("StatsBomb open data")
    if packet.get("fixture_injuries"):
        parts.append("API injuries feed")
    if not parts:
        parts.append("API-Football core fixture + odds")
    return " · ".join(parts)


def _value_signal_lines(packet: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    for v in packet.get("value_bets_display") or []:
        if not isinstance(v, dict):
            continue
        lbl = v.get("market_label") or "Value"
        edge = v.get("edge_pct")
        tier = v.get("value_tier")
        dual = v.get("value_dual_agree")
        model_p = v.get("model_probability_pct")
        impl_p = v.get("implied_probability_pct")
        odds = v.get("odds")
        chunk = lbl
        if model_p is not None and impl_p is not None:
            chunk += f" — model {model_p}% vs implied {impl_p}%"
        elif model_p is not None:
            chunk += f" — model {model_p}%"
        if edge is not None:
            chunk += f" (+{edge}% edge)"
        if odds:
            chunk += f" @ {odds}"
        if tier in ("favorite", "outsider"):
            chunk += f" ({tier})"
        if dual:
            chunk += " · dual finder agree"
        lines.append(chunk)
    return lines[:3]


def _rejected_lines(packet: Dict[str, Any]) -> List[str]:
    rejected = packet.get("value_bets_rejected") or {}
    if not rejected:
        return []
    return [
        f"{k}: {v}"
        for k, v in list(rejected.items())[:4]
    ]


def _form_snippet(packet: Dict[str, Any]) -> str:
    bits: List[str] = []
    for side, label in (("home", packet.get("home") or "Home"), ("away", packet.get("away") or "Away")):
        fs = packet.get(f"{side}_form_summary") or {}
        if not fs.get("played"):
            bits.append(f"{label}: form n/a")
            continue
        bits.append(
            f"{label} L{fs.get('played')}: W{fs.get('wins')}D{fs.get('draws')}L{fs.get('losses')} "
            f"(GF{fs.get('gf')} GA{fs.get('ga')}, BTTS {fs.get('btts')}, O2.5 {fs.get('over25')})"
        )
    return " · ".join(bits)


def _xg_snippet(packet: Dict[str, Any]) -> str:
    ps = packet.get("probability_scores") or {}
    xh = ps.get("xg_home")
    xa = ps.get("xg_away")
    src = packet.get("xg_source") or "unknown"
    if xh is None and xa is None:
        return f"xG unavailable (source: {src})"
    return f"xG {xh}–{xa} via {src}"


def thin_data_flags(packet: Dict[str, Any]) -> List[str]:
    flags: List[str] = []
    dq = packet.get("data_quality_pct")
    if dq is None:
        dq = (packet.get("data_quality") or {}).get("score_pct")
    if dq is not None and float(dq) < value_require_data_pct():
        flags.append("thin_data")
    reason = _exclusion_reason(packet)
    if reason == "thin_form_sample":
        flags.append("missing_form")
    elif reason == "low_data_quality":
        flags.append("thin_data")
    n_h = int(packet.get("home_recent_n") or 0)
    n_a = int(packet.get("away_recent_n") or 0)
    if n_h < assistant_min_form_matches() and n_a < assistant_min_form_matches():
        flags.append("missing_form")
    si = packet.get("structured_insight") or {}
    if si.get("mode") == "odds_only":
        flags.append("odds_only")
    return flags


def build_fixture_context_lines(packet: Dict[str, Any], *, include_pick: bool = True) -> List[str]:
    """Factual assistant lines grounded in structured_insight + packet fields."""
    si = packet.get("structured_insight") or {}
    ps = packet.get("probability_scores") or {}
    lines: List[str] = [
        f"**{_match_label(packet)}**"
        + (f" · KO {_kickoff_display(packet)}" if _kickoff_display(packet) else ""),
    ]
    dq = packet.get("data_quality_pct")
    if dq is not None:
        gate = value_require_data_pct()
        note = "clears value bar" if float(dq) >= gate else f"below value bar ({gate:.0f}%)"
        lines.append(f"Data coverage: **{dq}%** ({note}).")
    lines.append(f"Sources: {data_sources_summary(packet)}.")
    lines.append(_xg_snippet(packet))
    form = _form_snippet(packet)
    if form:
        lines.append(f"Form: {form}.")
    if include_pick:
        pick = si.get("pick") or "—"
        conf = si.get("confidence_pct")
        lines.append(
            f"Structured pick: **{pick}**"
            + (f" ({conf}% conf.)" if conf is not None else "")
            + (f" · mode {si.get('mode')}" if si.get("mode") else "")
        )
    if ps.get("home_win_pct") is not None:
        lines.append(
            f"1X2 model: H {ps.get('home_win_pct')}% · D {ps.get('draw_pct')}% · A {ps.get('away_win_pct')}%"
        )
    for label, key in (
        ("BTTS", "btts_pct"),
        ("O1.5", "over15_pct"),
        ("O2.5", "over25_pct"),
        ("O3.5", "over35_pct"),
    ):
        if ps.get(key) is not None:
            lines.append(f"{label}: {ps[key]}%")
    val_lines = _value_signal_lines(packet)
    if val_lines:
        lines.append("Value signals: " + "; ".join(val_lines) + ".")
    rejected = _rejected_lines(packet)
    if rejected:
        lines.append("Value guardrails blocked: " + "; ".join(rejected) + ".")
    weak = packet.get("weak_fields") or []
    if weak:
        lines.append("Weakest inputs: " + ", ".join(str(x) for x in weak[:4]) + ".")
    flags = thin_data_flags(packet)
    if flags:
        lines.append("**Thin data — caution** (" + ", ".join(flags) + ").")
    return lines


def pick_recommendation_line(
    packet: Dict[str, Any],
    market_key: Optional[str] = None,
    odds: Any = None,
    model_pct: Any = None,
) -> Optional[str]:
    """Bet-pick line with model vs implied; None if dq below assistant bar."""
    dq = packet.get("data_quality_pct")
    if dq is not None and float(dq) < assistant_min_data_pct():
        return None
    if _exclusion_reason(packet):
        return None
    menu = packet.get("pick_menu") or []
    item = None
    if market_key:
        item = next((m for m in menu if m.get("key") == market_key), None)
    if not item and menu:
        item = next((m for m in menu if m.get("recommended")), menu[0])
    if not item:
        return None
    mp = model_pct if model_pct is not None else item.get("model_pct")
    o = odds if odds is not None else item.get("odds")
    impl = _implied_pct(o)
    lbl = item.get("label") or market_key or "Pick"
    tier_bits: List[str] = []
    vb_key = market_key or item.get("key")
    for v in packet.get("value_bets_display") or []:
        if vb_key and v.get("market_key") == vb_key:
            if v.get("value_tier"):
                tier_bits.append(str(v["value_tier"]))
            if v.get("value_dual_agree"):
                tier_bits.append("dual agree")
    line = f"**{lbl}**"
    if mp is not None:
        line += f" — model **{mp}%**"
    if impl is not None:
        line += f" vs line implied **{impl}%**"
    if o:
        line += f" @ {o}"
    if tier_bits:
        line += f" ({', '.join(tier_bits)})"
    return line
