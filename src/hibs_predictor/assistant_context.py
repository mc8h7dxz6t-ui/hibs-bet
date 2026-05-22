"""
Shared factual context lines for the betting assistant and acca reviewer.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from hibs_predictor.assistant_facts import enrich_leg_with_packet_facts
from hibs_predictor.assistant_recommendations import (
    _build_acca,
    _exclusion_reason,
    _kickoff_display,
    _match_label,
    _rank_all_legs,
    assistant_min_data_pct,
    assistant_min_form_matches,
    build_detailed_leg_rationale,
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


def enrich_assistant_packet(packet: Dict[str, Any]) -> Dict[str, Any]:
    """Attach derived assistant fields (sources line, dual-agree flag)."""
    out = dict(packet)
    if not out.get("sources_summary"):
        out["sources_summary"] = data_sources_summary(out)
    if not out.get("supplemental_tags"):
        sup = out.get("supplemental") or {}
        tags: List[str] = []
        if isinstance(sup, dict):
            for key, label in (
                ("understat", "understat"),
                ("understat_light", "understat"),
                ("wikipedia_positions", "wikipedia"),
                ("soccerstats_positions", "soccerstats"),
                ("fbref_schedule", "fbref"),
                ("statsbomb_open_team_proxy", "statsbomb"),
            ):
                if sup.get(key):
                    tags.append(label)
        out["supplemental_tags"] = sorted(set(tags))
    if "has_value_dual_agree" not in out:
        out["has_value_dual_agree"] = any(
            isinstance(v, dict) and v.get("value_dual_agree")
            for v in out.get("value_bets_display") or []
        ) or any(
            isinstance(row, dict) and row.get("value_dual_agree")
            for row in (out.get("value_bets") or {}).values()
        )
    return out


def _position_brief(pos: Dict[str, Any], team: str) -> str:
    if not pos or not pos.get("position"):
        return f"{team}: —"
    bits = [f"{team} **{pos.get('position')}**", f"{pos.get('points', '—')} pts"]
    if pos.get("played") is not None:
        bits.append(f"P{pos.get('played')}")
    if pos.get("goal_diff") is not None:
        gd = pos.get("goal_diff")
        gd_s = f"+{gd}" if isinstance(gd, (int, float)) and gd > 0 else str(gd)
        bits.append(f"GD {gd_s}")
    if pos.get("form"):
        bits.append(f"table form {pos.get('form')}")
    return " · ".join(bits)


def _live_snippet(packet: Dict[str, Any]) -> Optional[str]:
    if not packet.get("is_live"):
        return None
    score = packet.get("live_score") or "—"
    status = packet.get("live_status") or "LIVE"
    minute = packet.get("live_minute")
    chunk = f"In play **{score}** ({status}"
    if minute is not None:
        chunk += f" {minute}'"
    chunk += ")"
    lxh = packet.get("live_xg_home")
    lxa = packet.get("live_xg_away")
    if lxh is not None or lxa is not None:
        chunk += f" · live xG {lxh}–{lxa}"
    evt = packet.get("live_last_event") or {}
    if isinstance(evt, dict) and evt.get("label"):
        chunk += f" · last {evt['label']}"
    return chunk


def _sharp_anchor_pct(packet: Dict[str, Any]) -> Optional[Dict[str, float]]:
    sharp = packet.get("sharp_anchor_implied") or {}
    if not isinstance(sharp, dict) or not sharp:
        return None
    out: Dict[str, float] = {}
    for k, v in sharp.items():
        try:
            out[k] = round(float(v) * 100, 1)
        except (TypeError, ValueError):
            continue
    return out or None


def _value_signals_compact(packet: Dict[str, Any], *, limit: int = 2) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for v in packet.get("value_bets_display") or []:
        if not isinstance(v, dict):
            continue
        rows.append(
            {
                "label": v.get("market_label") or v.get("outcome"),
                "edge_pct": v.get("edge_pct"),
                "dual": bool(v.get("value_dual_agree")),
                "tier": v.get("value_tier"),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def build_fixtures_summary(
    packets: List[Dict[str, Any]],
    *,
    max_n: int = 80,
) -> List[Dict[str, Any]]:
    """Compact per-fixture rows for assistant snapshot (card scan, filters)."""
    ordered = sorted(packets or [], key=lambda p: (p.get("date") or "", p.get("kickoff_time") or ""))
    out: List[Dict[str, Any]] = []
    for pkt in ordered[:max_n]:
        si = pkt.get("structured_insight") or {}
        ps = pkt.get("probability_scores") or {}
        hp = pkt.get("home_position") or {}
        ap = pkt.get("away_position") or {}
        out.append(
            {
                "id": pkt.get("id"),
                "home": pkt.get("home"),
                "away": pkt.get("away"),
                "kickoff_time": pkt.get("kickoff_time"),
                "league": pkt.get("league"),
                "league_name": pkt.get("league_name"),
                "competition_display": pkt.get("competition_display"),
                "data_quality_pct": pkt.get("data_quality_pct"),
                "trust_label": pkt.get("trust_label"),
                "weak_fields": (pkt.get("weak_fields") or [])[:4],
                "xg_source": pkt.get("xg_source"),
                "xg_home": ps.get("xg_home"),
                "xg_away": ps.get("xg_away"),
                "home_last10_wdl": pkt.get("home_last10_wdl"),
                "away_last10_wdl": pkt.get("away_last10_wdl"),
                "home_win_pct": ps.get("home_win_pct"),
                "draw_pct": ps.get("draw_pct"),
                "away_win_pct": ps.get("away_win_pct"),
                "btts_pct": ps.get("btts_pct"),
                "over15_pct": ps.get("over15_pct"),
                "over25_pct": ps.get("over25_pct"),
                "over35_pct": ps.get("over35_pct"),
                "pick": si.get("pick"),
                "pick_confidence_pct": si.get("confidence_pct"),
                "pick_mode": si.get("mode"),
                "bet_confidence": pkt.get("bet_confidence"),
                "bet_confidence_min_value": pkt.get("bet_confidence_min_value"),
                "has_value_bet": pkt.get("has_value_bet"),
                "has_value_dual_agree": pkt.get("has_value_dual_agree"),
                "value_signals": _value_signals_compact(pkt),
                "value_rejected_n": len(pkt.get("value_bets_rejected") or {}),
                "line_odds": pkt.get("line_odds"),
                "best_odds_1x2": pkt.get("best_odds_1x2"),
                "sharp_anchor_pct": _sharp_anchor_pct(pkt),
                "is_live": pkt.get("is_live"),
                "live_score": pkt.get("live_score"),
                "live_status": pkt.get("live_status"),
                "live_minute": pkt.get("live_minute"),
                "live_xg_home": pkt.get("live_xg_home"),
                "live_xg_away": pkt.get("live_xg_away"),
                "home_position": {
                    "position": hp.get("position"),
                    "points": hp.get("points"),
                    "source": hp.get("source"),
                }
                if hp
                else {},
                "away_position": {
                    "position": ap.get("position"),
                    "points": ap.get("points"),
                    "source": ap.get("source"),
                }
                if ap
                else {},
                "injuries_n": len(pkt.get("fixture_injuries") or []),
                "supplemental_tags": pkt.get("supplemental_tags") or [],
                "calibration_shrink": pkt.get("calibration_shrink"),
                "sources_summary": pkt.get("sources_summary") or data_sources_summary(pkt),
                "form_brief": _form_snippet(pkt),
                "home_recent_n": pkt.get("home_recent_n"),
                "away_recent_n": pkt.get("away_recent_n"),
            }
        )
    return out


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
        wdl = packet.get(f"{side}_last10_wdl") or ""
        fs = packet.get(f"{side}_form_summary") or {}
        if not fs.get("played") and not wdl:
            bits.append(f"{label}: form n/a")
            continue
        chunk = f"{label}"
        if wdl:
            chunk += f" [{wdl}]"
        if fs.get("played"):
            chunk += (
                f" L{fs.get('played')}: W{fs.get('wins')}D{fs.get('draws')}L{fs.get('losses')} "
                f"(GF{fs.get('gf')} GA{fs.get('ga')}, BTTS {fs.get('btts')}, O2.5 {fs.get('over25')})"
            )
        bits.append(chunk)
    return " · ".join(bits)


def _line_odds_snippet(packet: Dict[str, Any]) -> Optional[str]:
    lo = packet.get("line_odds") or {}
    best = packet.get("best_odds_1x2") or {}
    bits: List[str] = []
    for key, label in (("btts_yes", "BTTS"), ("over25", "O2.5"), ("over15", "O1.5")):
        if lo.get(key):
            bits.append(f"{label} {lo[key]}")
    for side, label in (("home", "H"), ("draw", "D"), ("away", "A")):
        if best.get(side):
            bits.append(f"best {label} {best[side]}")
    sharp = _sharp_anchor_pct(packet)
    if sharp:
        bits.append(
            "sharp "
            + "/".join(f"{k[0].upper()}{sharp[k]:.0f}%" for k in ("home", "draw", "away") if k in sharp)
        )
    return ", ".join(bits) if bits else None


def _calibration_snippet(packet: Dict[str, Any]) -> Optional[str]:
    shrink = packet.get("calibration_shrink")
    if not isinstance(shrink, dict) or not shrink:
        return None
    factor = shrink.get("shrink_factor") or shrink.get("factor")
    if factor is None:
        return None
    try:
        return f"Historic calibration shrink **{float(factor):.2f}** applied to model blend."
    except (TypeError, ValueError):
        return None


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
    comp = packet.get("competition_display") or packet.get("league_name") or packet.get("league")
    lines: List[str] = [
        f"**{_match_label(packet)}**"
        + (f" · {comp}" if comp else "")
        + (f" · KO {_kickoff_display(packet)}" if _kickoff_display(packet) else ""),
    ]
    dq = packet.get("data_quality_pct")
    trust = packet.get("trust_label")
    if dq is not None:
        gate = value_require_data_pct()
        note = "clears value bar" if float(dq) >= gate else f"below value bar ({gate:.0f}%)"
        trust_bit = f" · trust **{trust}**" if trust else ""
        lines.append(f"Data coverage: **{dq}%**{trust_bit} ({note}).")
    elif trust:
        lines.append(f"Data trust: **{trust}**.")
    bet_conf = packet.get("bet_confidence")
    if bet_conf is not None:
        floor = packet.get("bet_confidence_min_value")
        conf_note = "meets value floor" if floor is None or float(bet_conf) >= float(floor) else "below value confidence floor"
        lines.append(f"Bet confidence: **{bet_conf:.0f}%** ({conf_note}).")
    tags = packet.get("supplemental_tags") or []
    src = packet.get("sources_summary") or data_sources_summary(packet)
    if tags:
        src += f" · tags: {', '.join(tags)}"
    lines.append(f"Sources: {src}.")
    live = _live_snippet(packet)
    if live:
        lines.append(live + ".")
    if packet.get("live_stats") and packet.get("is_live"):
        lines.append("Live stats feed attached for in-play read.")
    hp = packet.get("home_position") or {}
    ap = packet.get("away_position") or {}
    if hp.get("position") or ap.get("position"):
        lines.append(
            "Table: "
            + _position_brief(hp, packet.get("home") or "Home")
            + " · "
            + _position_brief(ap, packet.get("away") or "Away")
            + "."
        )
    lines.append(_xg_snippet(packet))
    form = _form_snippet(packet)
    if form:
        lines.append(f"Form: {form}.")
    prices = _line_odds_snippet(packet)
    if prices:
        lines.append(f"Best lines: {prices}.")
    cal = _calibration_snippet(packet)
    if cal:
        lines.append(cal)
    inj = packet.get("fixture_injuries") or []
    if inj:
        lines.append(f"Injuries/absences: **{len(inj)}** rows on feed.")
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
    if packet.get("has_value_dual_agree"):
        lines.append("Value dual finder: **both model and consensus agree** on at least one market.")
    val_lines = _value_signal_lines(packet)
    if val_lines:
        lines.append("Value signals: " + "; ".join(val_lines) + ".")
    alt_n = len(packet.get("value_bets_alt") or {})
    if alt_n:
        lines.append(f"Alt value finder: **{alt_n}** consensus-edge market(s).")
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


def enrich_leg_list(
    legs: List[Dict[str, Any]],
    packets: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    by_id = {p.get("id"): p for p in (packets or [])}
    out: List[Dict[str, Any]] = []
    for leg in legs or []:
        pkt = by_id.get(leg.get("fixture_id")) or {}
        merged = enrich_leg_with_packet_facts(leg, pkt) if pkt else dict(leg)
        out.append(leg_slip_payload(merged))
    return out


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
            if leg.get("market_key") == "btts_yes":
                leg["rationale"] = build_detailed_leg_rationale(pkt, leg, max_bullets=3)
            else:
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
    if packet.get("trust_label"):
        bits.append(str(packet["trust_label"]))
    bc = packet.get("bet_confidence")
    if bc is not None:
        bits.append(f"bet conf {bc:.0f}%")
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
    return " · ".join(bits) if bits else "priced leg from snapshot (see model/dq when listed)"


def _acca_rank_score(acca: Dict[str, Any]) -> float:
    conf = float(acca.get("joint_confidence_pct") or 0)
    legs = acca.get("legs") or []
    leg_scores = sum(float(l.get("score") or l.get("model_pct") or 0) for l in legs)
    thin_penalty = sum(
        12.0
        for l in legs
        if l.get("data_quality_pct") is not None
        and float(l["data_quality_pct"]) < assistant_min_data_pct()
    )
    dual_bonus = sum(3.0 for l in legs if l.get("value_dual_agree") or l.get("has_value_dual_agree"))
    bet_conf_bonus = sum(
        min(4.0, max(0.0, (float(l.get("bet_confidence") or 0) - 70.0) * 0.1))
        for l in legs
        if l.get("bet_confidence") is not None
    )
    combined = float(acca.get("combined_odds") or 1.0)
    price_bonus = min(8.0, max(0.0, (combined - 2.5) * 2.0))
    return conf * 0.55 + leg_scores * 0.08 + price_bonus + dual_bonus + bet_conf_bonus - thin_penalty


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
        "I cover today's full fixture card — leagues, dq, value flags, and live games — not just one match.",
        "Card-wide: **live**, **value bets**, **deep dive all** · Accas: **best acca**, **suggest legs**, **BTTS acca**.",
        build_acca_window_summary(packets),
    ]
