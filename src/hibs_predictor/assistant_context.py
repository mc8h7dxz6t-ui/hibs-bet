"""
Shared factual context lines for the betting assistant and acca reviewer.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from hibs_predictor.assistant_recommendations import (
    _build_acca,
    _exclusion_reason,
    _kickoff_display,
    _match_label,
    _rank_all_legs,
    assistant_min_data_pct,
    assistant_min_form_matches,
    is_analyzable,
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


def leg_slip_payload(leg: Dict[str, Any]) -> Dict[str, Any]:
    """Structured leg for assistant UI → HibsBetslip.addSelection."""
    enriched = dict(leg)
    enriched["slip"] = {
        "fixture_id": leg.get("fixture_id"),
        "home": leg.get("home"),
        "away": leg.get("away"),
        "market_key": leg.get("market_key"),
        "market_label": leg.get("market_label"),
        "odds": leg.get("odds"),
        "league": leg.get("league_name") or leg.get("league"),
    }
    return enriched


def enrich_acca_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for acca in items or []:
        copy = dict(acca)
        copy["legs"] = [leg_slip_payload(l) for l in (acca.get("legs") or [])]
        out.append(copy)
    return out


def enrich_leg_list(legs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [leg_slip_payload(l) for l in legs]


def build_acca_window_summary(packets: List[Dict[str, Any]]) -> str:
    """One-line card summary for acca-first assistant context."""
    eligible = sum(1 for p in packets if is_analyzable(p))
    value_n = sum(1 for p in packets if p.get("has_value_bet") and is_analyzable(p))
    dual = 0
    for p in packets:
        for v in p.get("value_bets_display") or []:
            if isinstance(v, dict) and v.get("value_dual_agree"):
                dual += 1
                break
    scanned = len(packets)
    if not scanned:
        return "No fixtures in the current window — widen fetch days or refresh."
    parts = [f"{scanned} games loaded", f"{eligible} with full model data"]
    if value_n:
        parts.append(f"{value_n} value flags")
    if dual:
        parts.append(f"{dual} dual-agree value")
    return " · ".join(parts) + "."


def build_acca_candidates(
    packets: List[Dict[str, Any]],
    *,
    limit: int = 24,
) -> List[Dict[str, Any]]:
    """Ranked leg options across the card (one best market per fixture, then extras)."""
    ranked = _rank_all_legs(packets)
    by_fixture: Dict[Any, List[Dict[str, Any]]] = {}
    for leg in ranked:
        fid = leg.get("fixture_id")
        by_fixture.setdefault(fid, []).append(leg)
    ordered: List[Dict[str, Any]] = []
    for fid in sorted(by_fixture.keys(), key=lambda f: -(by_fixture[f][0].get("score") or 0)):
        for leg in by_fixture[fid][:2]:
            pkt = next((p for p in packets if p.get("id") == fid), {})
            leg = dict(leg)
            leg["rationale"] = _leg_candidate_blurb(pkt, leg)
            ordered.append(leg_slip_payload(leg))
            if len(ordered) >= limit:
                return ordered
    return ordered


def _leg_candidate_blurb(packet: Dict[str, Any], leg: Dict[str, Any]) -> str:
    bits: List[str] = []
    mp = leg.get("model_pct")
    if mp is not None:
        bits.append(f"model {mp}%")
    if leg.get("is_value") and leg.get("edge_pct") is not None:
        bits.append(f"+{leg['edge_pct']:.1f}% edge")
    dq = packet.get("data_quality_pct")
    if dq is not None:
        bits.append(f"dq {dq}%")
    for v in packet.get("value_bets_display") or []:
        if isinstance(v, dict) and v.get("market_key") == leg.get("market_key") and v.get("value_dual_agree"):
            bits.append("dual agree")
            break
    ps = packet.get("probability_scores") or {}
    mk = leg.get("market_key") or ""
    if mk == "btts_yes" and ps.get("btts_pct") is not None:
        bits.append(f"BTTS {ps['btts_pct']}%")
    if mk == "over_25" and ps.get("over25_pct") is not None:
        bits.append(f"O2.5 {ps['over25_pct']}%")
    if mk in ("home_win", "away_win") and ps.get("home_win_pct") is not None:
        bits.append(
            f"1X2 H{ps.get('home_win_pct')}% D{ps.get('draw_pct')}% A{ps.get('away_win_pct')}%"
        )
    return " · ".join(bits) if bits else "meets data bar"


def _acca_rank_score(acca: Dict[str, Any]) -> float:
    conf = float(acca.get("joint_confidence_pct") or 0)
    legs = acca.get("legs") or []
    leg_scores = sum(float(l.get("score") or l.get("model_pct") or 0) for l in legs)
    thin_penalty = sum(12.0 for l in legs if (l.get("data_quality_pct") or 100) < assistant_min_data_pct())
    combined = float(acca.get("combined_odds") or 1.0)
    price_bonus = min(8.0, max(0.0, (combined - 2.5) * 2.0))
    return conf * 0.55 + leg_scores * 0.08 + price_bonus - thin_penalty


def build_best_acca_ideas(
    recommendations: Dict[str, Any],
    *,
    max_ideas: int = 5,
    min_legs: int = 2,
    max_legs: int = 4,
    prefer_safer: bool = False,
    target_legs: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Rank 2–4 leg pre-built accas from suggestions + top singles combos."""
    ideas: List[Dict[str, Any]] = []
    seen: set = set()

    def _sig(acca: Dict[str, Any]) -> tuple:
        return tuple(
            (str(l.get("fixture_id")), str(l.get("market_key")))
            for l in (acca.get("legs") or [])
        )

    for acca in recommendations.get("acca_suggestions") or []:
        lc = acca.get("leg_count") or len(acca.get("legs") or [])
        if lc < min_legs or lc > max_legs:
            continue
        if target_legs is not None and lc != target_legs:
            continue
        sig = _sig(acca)
        if sig in seen:
            continue
        seen.add(sig)
        ideas.append(dict(acca))

    singles = recommendations.get("best_singles") or []
    for n in range(min_legs, max_legs + 1):
        if target_legs is not None and n != target_legs:
            continue
        chunk = singles[:n]
        if len(chunk) < n:
            continue
        fids = [str(l.get("fixture_id")) for l in chunk]
        if len(set(fids)) < n:
            continue
        title = f"Top {n}-fold ({'safer stats' if prefer_safer and n <= 3 else 'mixed markets'})"
        built = _build_acca(title, "best_pick", chunk, ["Strongest ranked legs from today's card."], min_legs=n, max_legs=n)
        if built:
            sig = _sig(built)
            if sig not in seen:
                seen.add(sig)
                ideas.append(built)

    if prefer_safer:
        ideas.sort(key=lambda a: (-_acca_rank_score(a), float(a.get("combined_odds") or 99)))
    else:
        ideas.sort(key=lambda a: (-_acca_rank_score(a), -float(a.get("combined_odds") or 0)))

    return enrich_acca_items(ideas[:max_ideas])


def acca_greeting_lines(packets: List[Dict[str, Any]]) -> List[str]:
    return [
        "I can build accas from today's card — want 2–5 legs, safer or bigger price?",
        "Try **best acca**, **acca tips**, **suggest legs**, or **BTTS acca** / **mixed acca**.",
        build_acca_window_summary(packets),
    ]
