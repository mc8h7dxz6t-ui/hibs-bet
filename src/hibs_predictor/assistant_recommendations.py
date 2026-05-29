"""
Deep-scan assistant recommendations: singles, accas, and market highlights.
Only fixtures with sufficient data quality and full model coverage are eligible.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from hibs_predictor.assistant_facts import enrich_leg_with_packet_facts
from hibs_predictor.match_insight import _value_bet_key

_DISCLAIMER = (
    "Data-backed view for research only — not financial advice. "
    "Stake conservatively; 18+ gamble responsibly."
)

_STAKE_FRIENDLIES = frozenset({"INTL_FRIENDLIES"})
_STAKE_SCALE_LEAGUES = frozenset(
    {
        "WORLD_CUP",
        "NORWAY_ELITESERIEN",
        "FINLAND_VEIKKAUSLIIGA",
        "DENMARK_SL",
    }
)

_ACCA_MARKET_KEYS = {
    "btts": frozenset({"btts_yes"}),
    "btts_no": frozenset({"btts_no"}),
    "over15": frozenset({"over_15"}),
    "over25": frozenset({"over_25"}),
    "over35": frozenset({"over_35"}),
    "win": frozenset({"home_win", "away_win"}),
    "value": None,  # any value-flagged leg from value_bets_display
}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def assistant_min_data_pct() -> float:
    return _env_float("HIBS_ASSISTANT_MIN_DATA_PCT", 78.0)


def assistant_min_form_matches() -> int:
    return max(2, _env_int("HIBS_ASSISTANT_MIN_FORM_MATCHES", 3))


def assistant_min_value_edge_pct() -> float:
    return _env_float("HIBS_ASSISTANT_MIN_VALUE_EDGE_PCT", 4.0)


def assistant_stake_kelly_fraction() -> float:
    """Fractional Kelly for small-stake guidance (default 12% of full Kelly)."""
    return max(0.05, min(0.5, _env_float("HIBS_ASSISTANT_STAKE_KELLY_FRAC", 0.12)))


def assistant_max_stake_pct() -> float:
    return max(0.25, min(10.0, _env_float("HIBS_ASSISTANT_MAX_STAKE_PCT", 2.5)))


def assistant_pre_proof_max_stake_pct() -> float:
    """Cap per-bet % until scale proof metrics pass (Brier + CLV on /tracker)."""
    return max(0.25, min(assistant_max_stake_pct(), _env_float("HIBS_ASSISTANT_PRE_PROOF_MAX_STAKE_PCT", 1.5)))


def assistant_stake_friendlies_enabled() -> bool:
    return (os.getenv("HIBS_ASSISTANT_STAKE_FRIENDLIES") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _league_stake_cohort(league_code: Optional[str]) -> str:
    lc = (league_code or "").strip().upper()
    if lc in _STAKE_FRIENDLIES:
        return "friendlies"
    if lc in _STAKE_SCALE_LEAGUES:
        return "scale"
    if lc and lc not in ("UNKNOWN", "SCOTTISH PREMIERSHIP"):
        return "scale"
    return "other"


def _implied_pct_from_odds(odds: Any) -> Optional[float]:
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if o <= 1.0:
        return None
    return round(100.0 / o, 1)


def _attach_stake_guidance(leg: Dict[str, Any], *, scale_proof_pass: bool) -> Dict[str, Any]:
    """Kelly-based small stake % + watch-only flags for friendlies / validation phase."""
    from hibs_predictor.betting_engine import OddsAnalyzer

    cohort = _league_stake_cohort(str(leg.get("league") or ""))
    out = dict(leg)
    out["stake_cohort"] = cohort
    mp = leg.get("model_pct")
    odds = leg.get("odds")
    implied = _implied_pct_from_odds(odds)
    if implied is not None:
        out["implied_pct"] = implied

    if cohort == "friendlies" and not assistant_stake_friendlies_enabled():
        out["stake_tier"] = "watch_only"
        out["stake_pct"] = 0.0
        out["stake_label"] = "Watch only"
        out["stake_note"] = (
            "International friendlies: high rotation — paper-track or skip real stakes "
            "(enable HIBS_ASSISTANT_STAKE_FRIENDLIES=1 to include in stake list)."
        )
        return out

    if mp is None or odds is None:
        out["stake_tier"] = "no_price"
        out["stake_pct"] = 0.0
        out["stake_label"] = "No stake"
        out["stake_note"] = "Missing model % or book price."
        return out

    try:
        win_p = float(mp) / 100.0
        o = float(odds)
    except (TypeError, ValueError):
        out["stake_tier"] = "no_price"
        out["stake_pct"] = 0.0
        out["stake_label"] = "No stake"
        return out

    kelly = OddsAnalyzer.kelly_criterion(win_p, o, fraction=assistant_stake_kelly_fraction())
    raw_pct = float(kelly.get("suggested_percent") or 0)
    cap = assistant_max_stake_pct()
    if not scale_proof_pass:
        cap = min(cap, assistant_pre_proof_max_stake_pct())
    stake_pct = round(min(cap, max(0.0, raw_pct)), 2)
    out["stake_pct"] = stake_pct
    out["stake_label"] = str(kelly.get("confidence_label") or "Cautious")
    out["stake_example_per_100"] = kelly.get("example_stake")
    if stake_pct <= 0:
        out["stake_tier"] = "skip"
        out["stake_note"] = "No positive Kelly edge at these odds — do not bet."
    elif not scale_proof_pass:
        out["stake_tier"] = "small_stake_validation"
        out["stake_note"] = (
            f"Validation phase: cap ~{stake_pct}% of bankroll per £100 until "
            "/tracker scale proof passes (Brier < baseline, CLV beat-close > 60%)."
        )
    else:
        out["stake_tier"] = "small_stake"
        out["stake_note"] = (
            f"Small stake: ~{stake_pct}% of bankroll "
            f"(fractional Kelly {assistant_stake_kelly_fraction():.0%}, max {cap}%)."
        )
    return out


def _staking_phase_summary() -> Dict[str, Any]:
    try:
        from hibs_predictor.performance_tracker import build_proof_metrics_dict

        proof = build_proof_metrics_dict()
    except Exception:
        proof = {}
    scale_ready = bool(proof.get("proof_pass"))
    lines = [
        "I only suggest **small stakes** on **value** legs with full model + book prices.",
        "Friendlies are **watch-only** unless you enable friendly stakes in env.",
    ]
    if scale_ready:
        lines.append("Scale proof on /tracker is **passing** — still use small fractional Kelly, not max stakes.")
    else:
        msg = proof.get("message") or "Keep stakes minimal while the audit sample builds on /tracker."
        lines.append(f"**Validation phase:** {msg}")
    return {
        "scale_proof_pass": scale_ready,
        "proof_metrics": proof,
        "summary_lines": lines,
    }


def build_small_stake_picks(
    packets: List[Dict[str, Any]],
    *,
    limit: int = 5,
) -> Dict[str, Any]:
    """
    Ranked value singles with model %, implied %, edge, and fractional-Kelly stake %.

    Used by the assistant for “small stakes” / “what to bet” intents.
    """
    limit = max(1, min(12, int(limit)))
    phase = _staking_phase_summary()
    scale_proof_pass = bool(phase.get("scale_proof_pass"))
    min_edge = assistant_min_value_edge_pct()
    candidates: List[Dict[str, Any]] = []

    for pkt in packets:
        if not is_analyzable(pkt):
            continue
        leg = _value_leg_from_display(pkt)
        if not leg:
            for item in pkt.get("pick_menu") or []:
                if not item.get("is_value"):
                    continue
                key = str(item.get("key") or "")
                mp_item = item.get("model_pct")
                if mp_item is not None and float(mp_item) < _min_model_pct_for_key(key):
                    continue
                leg = _leg_from_menu_item(pkt, item)
                leg["is_value"] = True
                break
        if not leg or not leg.get("is_value"):
            continue
        try:
            edge = float(leg.get("edge_pct") or 0)
        except (TypeError, ValueError):
            edge = 0.0
        if edge < min_edge:
            continue
        leg = enrich_leg_with_packet_facts(dict(leg), pkt)
        leg["match"] = _match_label(pkt)
        leg["rationale"] = build_detailed_leg_rationale(pkt, leg, max_bullets=4)
        leg = _attach_stake_guidance(leg, scale_proof_pass=scale_proof_pass)
        if leg.get("stake_tier") == "skip":
            continue
        candidates.append(leg)

    candidates.sort(key=lambda x: (-float(x.get("score") or 0), -float(x.get("edge_pct") or 0)))
    picks = candidates[:limit]
    bettable = [p for p in picks if p.get("stake_tier") in ("small_stake", "small_stake_validation")]

    return {
        "scale_proof_pass": scale_proof_pass,
        "summary_lines": phase.get("summary_lines") or [],
        "picks": picks,
        "bettable_count": len(bettable),
        "min_edge_pct": min_edge,
        "max_stake_pct": assistant_pre_proof_max_stake_pct()
        if not scale_proof_pass
        else assistant_max_stake_pct(),
    }


def _exclusion_reason(packet: Dict[str, Any]) -> Optional[str]:
    si = packet.get("structured_insight") or {}
    mode = si.get("mode") or ""
    if mode == "odds_only":
        return "odds_only"
    if mode == "avoid" and not packet.get("pick_menu"):
        return "no_model"
    dq = packet.get("data_quality_pct")
    if dq is None:
        dq = (packet.get("data_quality") or {}).get("score_pct")
    if dq is not None and float(dq) < assistant_min_data_pct():
        return "low_data_quality"
    n_h = int(packet.get("home_recent_n") or 0)
    n_a = int(packet.get("away_recent_n") or 0)
    if n_h < assistant_min_form_matches() and n_a < assistant_min_form_matches():
        return "thin_form_sample"
    if packet.get("prediction_unavailable"):
        return "prediction_unavailable"
    return None


def is_analyzable(packet: Dict[str, Any]) -> bool:
    return _exclusion_reason(packet) is None


def _match_label(packet: Dict[str, Any]) -> str:
    si = packet.get("structured_insight") or {}
    return si.get("match") or f"{packet.get('home', '?')} vs {packet.get('away', '?')}"


def _kickoff_display(packet: Dict[str, Any]) -> str:
    kt = packet.get("kickoff_time")
    if kt:
        return str(kt)
    raw = packet.get("date") or ""
    if "T" in raw and len(raw) >= 16:
        return raw[11:16]
    return ""


def _leg_from_menu_item(packet: Dict[str, Any], item: Dict[str, Any]) -> Dict[str, Any]:
    key = item.get("key") or ""
    return {
        "fixture_id": packet.get("id"),
        "home": packet.get("home"),
        "away": packet.get("away"),
        "league": packet.get("league"),
        "league_name": packet.get("league_name"),
        "kickoff_time": _kickoff_display(packet),
        "market_key": key,
        "market_label": item.get("label") or key,
        "model_pct": item.get("model_pct"),
        "odds": item.get("odds"),
        "is_value": bool(item.get("is_value")),
        "edge_pct": item.get("edge_pct"),
        "roi_pct": item.get("roi_pct"),
        "recommended": bool(item.get("recommended")),
        "data_quality_pct": packet.get("data_quality_pct"),
        "bet_confidence": packet.get("bet_confidence"),
        "has_value_dual_agree": packet.get("has_value_dual_agree"),
        "is_live": packet.get("is_live"),
        "live_score": packet.get("live_score"),
    }


def _leg_score(leg: Dict[str, Any]) -> float:
    mp = leg.get("model_pct")
    if mp is None:
        return 0.0
    score = float(mp)
    if leg.get("is_value"):
        score += float(leg.get("edge_pct") or 0) * 0.35
        score += float(leg.get("roi_pct") or 0) * 0.15
    if leg.get("recommended"):
        score += 4.0
    dq = leg.get("data_quality_pct")
    if dq is not None:
        score *= 0.85 + min(1.0, float(dq) / 100.0) * 0.15
    if leg.get("value_dual_agree") or leg.get("has_value_dual_agree"):
        score += 5.0
    bc = leg.get("bet_confidence")
    if bc is not None:
        score += min(6.0, max(0.0, (float(bc) - 72.0) * 0.12))
    return score


def _min_model_pct_for_key(key: str) -> float:
    thresholds = {
        "btts_yes": _env_float("HIBS_ASSISTANT_BTTS_MIN_PCT", 56.0),
        "btts_no": _env_float("HIBS_ASSISTANT_BTTS_MIN_PCT", 56.0),
        "over_15": _env_float("HIBS_ASSISTANT_OVER15_MIN_PCT", 62.0),
        "over_25": _env_float("HIBS_ASSISTANT_OVER25_MIN_PCT", 58.0),
        "over_35": _env_float("HIBS_ASSISTANT_OVER35_MIN_PCT", 55.0),
        "home_win": _env_float("HIBS_ASSISTANT_WIN_MIN_PCT", 50.0),
        "away_win": _env_float("HIBS_ASSISTANT_WIN_MIN_PCT", 50.0),
        "home_and_btts": _env_float("HIBS_ASSISTANT_COMBO_MIN_PCT", 18.0),
        "away_and_btts": _env_float("HIBS_ASSISTANT_COMBO_MIN_PCT", 18.0),
        "draw_and_btts": _env_float("HIBS_ASSISTANT_COMBO_MIN_PCT", 12.0),
    }
    return thresholds.get(key, 52.0)


def _collect_candidate_legs(
    packet: Dict[str, Any],
    allowed_keys: Optional[frozenset] = None,
) -> List[Dict[str, Any]]:
    if not is_analyzable(packet):
        return []
    legs: List[Dict[str, Any]] = []
    for item in packet.get("pick_menu") or []:
        key = item.get("key") or ""
        if key in ("avoid", "odds_only") or item.get("odds") is None:
            continue
        if allowed_keys is not None and key not in allowed_keys:
            continue
        mp = item.get("model_pct")
        if mp is None or float(mp) < _min_model_pct_for_key(key):
            continue
        leg = _leg_from_menu_item(packet, item)
        leg["score"] = _leg_score(leg)
        legs.append(leg)
    return legs


def _value_leg_from_display(packet: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not is_analyzable(packet):
        return None
    vbd = packet.get("value_bets_display") or []
    if not vbd:
        return None
    top = vbd[0]
    outcome = top.get("outcome") or ""
    menu_by_key = {m.get("key"): m for m in (packet.get("pick_menu") or [])}
    menu_key = None
    for mk, vbk in (
        ("home_win", "home"),
        ("away_win", "away"),
        ("draw", "draw"),
        ("btts_yes", "btts_yes"),
        ("btts_no", "btts_no"),
        ("over_25", "over25"),
        ("over_15", "over15"),
        ("over_35", "over35"),
    ):
        if vbk == outcome or _value_bet_key(mk) == outcome:
            menu_key = mk
            break
    item = menu_by_key.get(menu_key or "") if menu_key else None
    leg = {
        "fixture_id": packet.get("id"),
        "home": packet.get("home"),
        "away": packet.get("away"),
        "league": packet.get("league"),
        "league_name": packet.get("league_name"),
        "kickoff_time": _kickoff_display(packet),
        "market_key": menu_key or outcome,
        "market_label": top.get("market_label") or outcome,
        "model_pct": item.get("model_pct") if item else None,
        "odds": top.get("odds"),
        "is_value": True,
        "edge_pct": top.get("edge_pct"),
        "roi_pct": top.get("roi_percent"),
        "recommended": False,
        "data_quality_pct": packet.get("data_quality_pct"),
    }
    leg["score"] = _leg_score(leg) + 8.0
    return leg


def _joint_confidence_pct(legs: List[Dict[str, Any]]) -> Optional[float]:
    """Conservative joint model confidence (product of leg probs, capped)."""
    probs: List[float] = []
    for leg in legs:
        mp = leg.get("model_pct")
        if mp is None:
            continue
        probs.append(max(0.02, min(0.98, float(mp) / 100.0)))
    if not probs:
        return None
    joint = 1.0
    for p in probs:
        joint *= p
    min_p = min(probs)
    blend = joint * 0.55 + min_p * 0.45
    return round(blend * 100, 1)


def _combined_decimal_odds(legs: List[Dict[str, Any]]) -> Optional[float]:
    acc = 1.0
    for leg in legs:
        o = leg.get("odds")
        if o is None or float(o) <= 1.0:
            return None
        acc *= float(o)
    return round(acc, 2) if legs else None


def _build_acca(
    title: str,
    acca_type: str,
    legs: List[Dict[str, Any]],
    rationale: List[str],
    min_legs: int = 3,
    max_legs: int = 5,
) -> Optional[Dict[str, Any]]:
    if len(legs) < min_legs:
        return None
    picked = legs[:max_legs]
    combined = _combined_decimal_odds(picked)
    if combined is None:
        return None
    conf = _joint_confidence_pct(picked)
    return {
        "title": title,
        "type": acca_type,
        "leg_count": len(picked),
        "legs": picked,
        "combined_odds": combined,
        "joint_confidence_pct": conf,
        "rationale": rationale,
        "disclaimer": _DISCLAIMER,
    }


def build_mixed_market_acca(packets: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """One strongest priced leg per fixture; markets can differ (BTTS, O/U, 1X2, combos)."""
    legs: List[Dict[str, Any]] = []
    for pkt in packets:
        if not is_analyzable(pkt):
            continue
        candidates = _collect_candidate_legs(pkt, allowed_keys=None)
        if not candidates:
            vl = _value_leg_from_display(pkt)
            if vl:
                candidates = [vl]
        if not candidates:
            continue
        best = max(candidates, key=lambda x: float(x.get("score") or 0))
        best["rationale"] = _leg_rationale(pkt, best)
        legs.append(best)
    legs.sort(key=lambda x: -float(x.get("score") or 0))
    return _build_acca(
        "Multi-market Acca (strongest stats per match)",
        "mixed",
        legs,
        [
            "Each leg is the highest-scoring market for that fixture (BTTS, goals, win, combos).",
            "One selection per match — use as standard acca or same-game multi where your book allows.",
            "Only fixtures passing the professional data bar are included.",
        ],
    )


def _menu_item_by_key(packet: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(item.get("key") or ""): item for item in (packet.get("pick_menu") or [])}


def _builder_component(packet: Dict[str, Any], item: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not item or item.get("odds") is None:
        return None
    mp = item.get("model_pct")
    if mp is None:
        return None
    leg = _leg_from_menu_item(packet, item)
    leg["score"] = _leg_score(leg)
    return leg


def _build_same_game_builder(
    packet: Dict[str, Any],
    title: str,
    builder_type: str,
    keys: Tuple[str, ...],
    rationale: List[str],
    combo_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    menu = _menu_item_by_key(packet)
    legs: List[Dict[str, Any]] = []
    for key in keys:
        leg = _builder_component(packet, menu.get(key))
        if not leg:
            return None
        legs.append(leg)
    if len(legs) < 2:
        return None
    combo_item = menu.get(combo_key or "")
    combo_model_pct = combo_item.get("model_pct") if combo_item else None
    return {
        "title": title,
        "type": builder_type,
        "fixture_id": packet.get("id"),
        "match": _match_label(packet),
        "home": packet.get("home"),
        "away": packet.get("away"),
        "league": packet.get("league"),
        "league_name": packet.get("league_name"),
        "kickoff_time": _kickoff_display(packet),
        "legs": legs,
        "leg_count": len(legs),
        "estimated_independent_odds": _combined_decimal_odds(legs),
        "joint_confidence_pct": combo_model_pct or _joint_confidence_pct(legs),
        "bookmaker_quote_required": True,
        "rationale": rationale,
        "disclaimer": (
            "Same-game builders are correlated, so the bookmaker quote will differ from "
            "multiplying the leg odds. Use the listed markets only as components."
        ),
    }


def _collect_bet_builders_for_packet(pkt: Dict[str, Any]) -> List[Dict[str, Any]]:
    """All qualifying same-game builders for one fixture (caller applies per-fixture cap)."""
    if not is_analyzable(pkt):
        return []
    menu = _menu_item_by_key(pkt)
    local: List[Dict[str, Any]] = []

    def pct(key: str) -> float:
        try:
            return float((menu.get(key) or {}).get("model_pct") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def add(builder: Optional[Dict[str, Any]]) -> None:
        if builder:
            builder["score"] = sum(float(l.get("score") or 0) for l in builder.get("legs") or [])
            local.append(builder)

    if pct("btts_yes") >= 58 and pct("over_25") >= 58:
        add(
            _build_same_game_builder(
                pkt,
                "BTTS + Over 2.5",
                "btts_over25",
                ("btts_yes", "over_25"),
                [
                    "Positive correlation: both teams scoring supports a higher total-goals line.",
                    "Only suggested where both component markets have model support and book prices.",
                ],
            )
        )
    if pct("btts_yes") >= 60 and pct("over_15") >= 68:
        add(
            _build_same_game_builder(
                pkt,
                "BTTS + Over 1.5",
                "btts_over15",
                ("btts_yes", "over_15"),
                [
                    "Lower total than O2.5; still aligned with the BTTS game script.",
                    "Useful when BTTS is strong but the third goal is less certain.",
                ],
            )
        )
    if pct("draw") >= 28 and pct("over_15") >= 65:
        add(
            _build_same_game_builder(
                pkt,
                "Draw + Over 1.5",
                "draw_over15",
                ("draw", "over_15"),
                [
                    "Stalemate script with enough goal expectation for two or more.",
                    "Both legs need priced markets from the book.",
                ],
            )
        )
    if pct("home_win") >= 50 and pct("over_15") >= 62:
        add(
            _build_same_game_builder(
                pkt,
                "Home result + Over 1.5",
                "home_over15",
                ("home_win", "over_15"),
                [
                    "Favourite-led game script: home edge with enough goals profile for O1.5.",
                    "Standings/form context should still be checked before staking.",
                ],
            )
        )
    if pct("away_win") >= 50 and pct("over_15") >= 62:
        add(
            _build_same_game_builder(
                pkt,
                "Away result + Over 1.5",
                "away_over15",
                ("away_win", "over_15"),
                [
                    "Away side has a win edge and the match profile clears the O1.5 bar.",
                    "Use smaller stakes if travel/form inputs are thin.",
                ],
            )
        )
    if pct("home_or_draw") >= 62 and pct("over_15") >= 62:
        add(
            _build_same_game_builder(
                pkt,
                "Home or Draw + Over 1.5",
                "home_or_draw_over15",
                ("home_or_draw", "over_15"),
                [
                    "Safer result anchor: home avoids defeat while the goals profile supports O1.5.",
                    "Only appears when both double-chance and goals components have real book prices.",
                ],
            )
        )
    if pct("away_or_draw") >= 62 and pct("over_15") >= 62:
        add(
            _build_same_game_builder(
                pkt,
                "Away or Draw + Over 1.5",
                "away_or_draw_over15",
                ("away_or_draw", "over_15"),
                [
                    "Safer away-side result anchor paired with a modest goals line.",
                    "Only appears when both double-chance and goals components have real book prices.",
                ],
            )
        )
    if pct("home_or_draw") >= 58 and pct("btts_yes") >= 55:
        add(
            _build_same_game_builder(
                pkt,
                "Home or Draw + BTTS",
                "home_or_draw_btts",
                ("home_or_draw", "btts_yes"),
                [
                    "Double-chance home cover with both teams to score.",
                    "Correlated — use your book's bet-builder price, not multiplied leg odds.",
                ],
            )
        )
    if pct("away_or_draw") >= 58 and pct("btts_yes") >= 55:
        add(
            _build_same_game_builder(
                pkt,
                "Away or Draw + BTTS",
                "away_or_draw_btts",
                ("away_or_draw", "btts_yes"),
                [
                    "Away avoids defeat while both attacks rate for goals.",
                    "Correlated — confirm the combined quote in bet builder.",
                ],
            )
        )
    if pct("home_or_away") >= 70 and pct("over_15") >= 62:
        add(
            _build_same_game_builder(
                pkt,
                "No Draw + Over 1.5",
                "home_or_away_over15",
                ("home_or_away", "over_15"),
                [
                    "Draw risk rates low enough to pair no-draw with the O1.5 game script.",
                    "Requires a priced no-draw/double-chance market from the available odds feed.",
                ],
            )
        )
    if pct("home_win") >= 45 and pct("btts_yes") >= 58:
        add(
            _build_same_game_builder(
                pkt,
                "Home result + BTTS",
                "home_btts",
                ("home_win", "btts_yes"),
                [
                    "Correlated if the home side can win without fully suppressing the away attack.",
                    "Prefer when xG/form points to chances for both teams.",
                ],
                combo_key="home_and_btts",
            )
        )
    if pct("away_win") >= 45 and pct("btts_yes") >= 58:
        add(
            _build_same_game_builder(
                pkt,
                "Away result + BTTS",
                "away_btts",
                ("away_win", "btts_yes"),
                [
                    "Correlated if the away side has enough win probability and both attacks rate well.",
                    "No player props are included unless a real player-prop feed is wired.",
                ],
                combo_key="away_and_btts",
            )
        )
    if pct("draw") >= 28 and pct("btts_yes") >= 58:
        add(
            _build_same_game_builder(
                pkt,
                "Draw + BTTS",
                "draw_btts",
                ("draw", "btts_yes"),
                [
                    "Shared game script: stalemate with both teams scoring.",
                    "Use your book's bet builder — component odds multiply for reference only.",
                ],
                combo_key="draw_and_btts",
            )
        )
    if pct("home_win") >= 45 and pct("over_25") >= 58:
        add(
            _build_same_game_builder(
                pkt,
                "Home result + Over 2.5",
                "home_over25",
                ("home_win", "over_25"),
                [
                    "Favourite win profile paired with a higher goals line.",
                    "Correlated — book quote will differ from multiplying leg prices.",
                ],
            )
        )
    if pct("away_win") >= 45 and pct("over_25") >= 58:
        add(
            _build_same_game_builder(
                pkt,
                "Away result + Over 2.5",
                "away_over25",
                ("away_win", "over_25"),
                [
                    "Away win edge with enough goal expectation for three or more.",
                    "Correlated — confirm price in bet builder before staking.",
                ],
            )
        )
    if pct("home_win") >= 48 and pct("under_25") >= 58:
        add(
            _build_same_game_builder(
                pkt,
                "Home result + Under 2.5",
                "home_under25",
                ("home_win", "under_25"),
                [
                    "Tight home control script: win lean with a low total-goals profile.",
                    "Opposite correlation to BTTS+O2.5 — do not combine both on the same slip.",
                ],
            )
        )
    local.sort(key=lambda x: -float(x.get("score") or 0))
    return local


def build_bet_builder_suggestions(
    packets: List[Dict[str, Any]],
    fixture_id: Optional[Any] = None,
    *,
    limit: int = 36,
    max_per_fixture: int = 3,
) -> List[Dict[str, Any]]:
    """Same-game builder ideas from available markets only; no synthetic player props.

    Keeps up to *max_per_fixture* ranked options per match, then applies a global *limit*.
    """
    out: List[Dict[str, Any]] = []
    for pkt in packets:
        if fixture_id is not None and str(pkt.get("id")) != str(fixture_id):
            continue
        per_match = _collect_bet_builders_for_packet(pkt)[: max(1, max_per_fixture)]
        n = len(per_match)
        for rank, builder in enumerate(per_match, start=1):
            builder["builder_rank"] = rank
            builder["builders_for_fixture"] = n
            out.append(builder)
    out.sort(key=lambda x: (-float(x.get("score") or 0), str(x.get("kickoff_time") or "")))
    if limit > 0:
        return out[:limit]
    return out


def _rank_all_legs(packets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    all_legs: List[Dict[str, Any]] = []
    seen_fixture_market: set = set()
    for pkt in packets:
        if not is_analyzable(pkt):
            continue
        for leg in _collect_candidate_legs(pkt, allowed_keys=None):
            fid = leg.get("fixture_id")
            mk = leg.get("market_key")
            sk = (fid, mk)
            if sk in seen_fixture_market:
                continue
            seen_fixture_market.add(sk)
            all_legs.append(leg)
        vl = _value_leg_from_display(pkt)
        if vl:
            sk = (vl.get("fixture_id"), vl.get("market_key"))
            if sk not in seen_fixture_market:
                seen_fixture_market.add(sk)
                all_legs.append(vl)
    all_legs.sort(key=lambda x: -float(x.get("score") or 0))
    return all_legs


def _legs_for_acca_type(packets: List[Dict[str, Any]], acca_type: str) -> List[Dict[str, Any]]:
    keys = _ACCA_MARKET_KEYS.get(acca_type)
    legs: List[Dict[str, Any]] = []
    used_fixtures: set = set()
    for pkt in packets:
        if not is_analyzable(pkt):
            continue
        if acca_type == "value":
            vl = _value_leg_from_display(pkt)
            if vl and pkt.get("id") not in used_fixtures:
                legs.append(vl)
                used_fixtures.add(pkt.get("id"))
            continue
        if keys is None:
            continue
        candidates = _collect_candidate_legs(pkt, allowed_keys=keys)
        if not candidates:
            continue
        best = max(candidates, key=lambda x: float(x.get("score") or 0))
        fid = pkt.get("id")
        if fid in used_fixtures:
            continue
        legs.append(best)
        used_fixtures.add(fid)
    legs.sort(key=lambda x: -float(x.get("score") or 0))
    return legs


def _market_highlights(packets: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    buckets: Dict[str, List[Dict[str, Any]]] = {
        "btts_yes": [],
        "btts_no": [],
        "over_15": [],
        "over_25": [],
        "over_35": [],
        "win_combo": [],
    }
    win_combo_keys = frozenset({"home_and_btts", "away_and_btts", "draw_and_btts"})
    for pkt in packets:
        if not is_analyzable(pkt):
            continue
        for item in pkt.get("pick_menu") or []:
            key = item.get("key") or ""
            bucket = None
            if key in ("btts_yes", "btts_no", "over_15", "over_25", "over_35"):
                bucket = key
            elif key in win_combo_keys:
                bucket = "win_combo"
            if bucket is None:
                continue
            mp = item.get("model_pct")
            if mp is None or float(mp) < _min_model_pct_for_key(key):
                continue
            leg = _leg_from_menu_item(pkt, item)
            leg["score"] = _leg_score(leg)
            leg["rationale"] = _leg_rationale(pkt, leg)
            buckets[bucket].append(leg)
    out: Dict[str, List[Dict[str, Any]]] = {}
    for k, rows in buckets.items():
        rows.sort(key=lambda x: -float(x.get("score") or 0))
        out[k] = rows[:5]
    return out


def _leg_rationale(packet: Dict[str, Any], leg: Dict[str, Any]) -> List[str]:
    return build_detailed_leg_rationale(packet, leg, max_bullets=3)


def build_detailed_leg_rationale(
    packet: Dict[str, Any],
    leg: Dict[str, Any],
    *,
    max_bullets: int = 5,
) -> List[str]:
    """Grounded reasoning bullets from snapshot fields only — no invented stats."""
    si = packet.get("structured_insight") or {}
    ps = packet.get("probability_scores") or {}
    bullets: List[str] = []
    mk = leg.get("market_key") or ""
    mp = leg.get("model_pct")
    if mp is not None:
        bullets.append(f"Model **{mp}%** on {leg.get('market_label') or mk}.")
    btts_pct = ps.get("btts_pct")
    if mk == "btts_yes" and btts_pct is not None:
        bullets.append(f"Fixture BTTS probability **{btts_pct}%** (Poisson/xG blend).")
    if mk == "over_25" and ps.get("over25_pct") is not None:
        bullets.append(f"Over 2.5 model **{ps['over25_pct']}%**.")
    if mk in ("home_win", "away_win") and ps.get("home_win_pct") is not None:
        bullets.append(
            f"1X2 blend H {ps.get('home_win_pct')}% · D {ps.get('draw_pct')}% · A {ps.get('away_win_pct')}%."
        )
    xh, xa = ps.get("xg_home"), ps.get("xg_away")
    if xh is not None or xa is not None:
        src = packet.get("xg_source") or "model"
        bullets.append(f"xG **{xh}–{xa}** ({src}).")
    for side, label in (("home", packet.get("home") or "Home"), ("away", packet.get("away") or "Away")):
        fs = packet.get(f"{side}_form_summary") or {}
        if fs.get("played"):
            bullets.append(
                f"{label} L{fs['played']}: W{fs.get('wins')}D{fs.get('draws')}L{fs.get('losses')}, "
                f"GF{fs.get('gf')} GA{fs.get('ga')}, BTTS {fs.get('btts')}, O2.5 {fs.get('over25')}."
            )
            break
    hp = packet.get("home_position") or {}
    ap = packet.get("away_position") or {}
    if hp.get("position") or ap.get("position"):
        bullets.append(
            f"Table: {packet.get('home')} **{hp.get('position', '—')}** ({hp.get('points', '—')} pts) · "
            f"{packet.get('away')} **{ap.get('position', '—')}** ({ap.get('points', '—')} pts)."
        )
    injuries = packet.get("fixture_injuries") or []
    if injuries:
        bullets.append(f"**{len(injuries)}** injury/absence rows on feed — check team news before staking.")
    if leg.get("is_value") and leg.get("edge_pct") is not None:
        bullets.append(f"Value edge **+{leg['edge_pct']:.1f}%** vs fair line.")
    dq = packet.get("data_quality_pct")
    if dq is not None:
        bullets.append(f"Data coverage **{dq}%** (assistant bar ≥{assistant_min_data_pct():.0f}%).")
    if si.get("predicted_scoreline"):
        bullets.append(f"Scoreline lean **{si['predicted_scoreline']}**.")
    if si.get("rationale"):
        for bullet in si["rationale"][:2]:
            if bullet and bullet not in bullets:
                bullets.append(str(bullet))
    for metric in (si.get("rationale_metrics") or [])[:2]:
        if not isinstance(metric, dict):
            continue
        label = metric.get("label")
        value = metric.get("value")
        if label and value is not None:
            note = metric.get("note")
            line = f"{label}: **{value}**"
            if note:
                line += f" ({note})"
            if line not in bullets:
                bullets.append(line)
    return bullets[:max_bullets]


def build_ranked_btts_legs(
    packets: List[Dict[str, Any]],
    *,
    limit: int = 10,
    detailed: bool = False,
) -> List[Dict[str, Any]]:
    """Ranked BTTS Yes legs (one per fixture), with optional detailed rationale."""
    ranked: List[Dict[str, Any]] = []
    used: set = set()
    for pkt in packets:
        if not is_analyzable(pkt):
            continue
        candidates = _collect_candidate_legs(pkt, allowed_keys=frozenset({"btts_yes"}))
        if not candidates:
            continue
        best = max(candidates, key=lambda x: float(x.get("score") or 0))
        fid = pkt.get("id")
        if fid in used:
            continue
        used.add(fid)
        leg = enrich_leg_with_packet_facts(dict(best), pkt)
        leg["match"] = _match_label(pkt)
        leg["rationale"] = build_detailed_leg_rationale(pkt, leg, max_bullets=5 if detailed else 3)
        ranked.append(leg)
    ranked.sort(key=lambda x: -float(x.get("score") or 0))
    return ranked[:limit]


def build_multi_leg_btts_acca(
    packets: List[Dict[str, Any]],
    *,
    target_legs: int = 3,
    max_legs: int = 10,
    detailed: bool = False,
) -> Dict[str, Any]:
    """BTTS acca up to max_legs; disclaimer when fewer than target_legs qualify."""
    cap = min(max(2, max_legs), 10)
    want = min(max(2, target_legs), cap)
    pool = build_ranked_btts_legs(packets, limit=cap, detailed=detailed)
    picked = pool[:want]
    lines: List[str] = []
    if len(picked) < want:
        lines.append(
            f"Only **{len(picked)}** BTTS legs cleared the data/model bar (you asked for {want}). "
            "Widen the card or refresh — I won't pad with thin fixtures."
        )
    if not picked:
        return {
            "title": f"BTTS {want}-fold",
            "type": "btts",
            "leg_count": 0,
            "legs": [],
            "qualified_count": 0,
            "requested_count": want,
            "disclaimer": _DISCLAIMER,
            "rationale": ["No BTTS Yes legs with book prices and model support in this window."],
        }
    acca = _build_acca(
        f"BTTS {len(picked)}-fold",
        "btts",
        picked,
        [
            "One BTTS Yes per match; ranked by model score and data quality.",
            "Stats below are from the live fixture snapshot — not invented.",
        ],
        min_legs=2,
        max_legs=len(picked),
    )
    if not acca:
        return {
            "title": f"BTTS {len(picked)}-fold",
            "type": "btts",
            "leg_count": len(picked),
            "legs": picked,
            "qualified_count": len(picked),
            "requested_count": want,
            "disclaimer": _DISCLAIMER,
            "rationale": lines,
        }
    acca["qualified_count"] = len(picked)
    acca["requested_count"] = want
    if lines:
        acca["rationale"] = lines + list(acca.get("rationale") or [])
    for leg in acca.get("legs") or []:
        pkt = next((p for p in packets if p.get("id") == leg.get("fixture_id")), {})
        if pkt and detailed:
            leg["rationale"] = build_detailed_leg_rationale(pkt, leg, max_bullets=5)
    return acca


def build_win_btts_combo_suggestions(
    packets: List[Dict[str, Any]],
    *,
    limit: int = 3,
    detailed: bool = False,
) -> List[Dict[str, Any]]:
    """Ranked win+BTTS combo legs from priced pick_menu combo keys."""
    combo_keys = frozenset({"home_and_btts", "away_and_btts", "draw_and_btts"})
    out: List[Dict[str, Any]] = []
    for pkt in packets:
        if not is_analyzable(pkt):
            continue
        menu = _menu_item_by_key(pkt)
        for key in combo_keys:
            item = menu.get(key)
            if not item or item.get("odds") is None:
                continue
            mp = item.get("model_pct")
            if mp is None or float(mp) < _min_model_pct_for_key(key):
                continue
            leg = enrich_leg_with_packet_facts(_leg_from_menu_item(pkt, item), pkt)
            leg["score"] = _leg_score(leg)
            leg["match"] = _match_label(pkt)
            leg["rationale"] = build_detailed_leg_rationale(
                pkt, leg, max_bullets=5 if detailed else 3
            )
            out.append(leg)
    out.sort(key=lambda x: -float(x.get("score") or 0))
    seen: set = set()
    deduped: List[Dict[str, Any]] = []
    for leg in out:
        sk = (leg.get("fixture_id"), leg.get("market_key"))
        if sk in seen:
            continue
        seen.add(sk)
        deduped.append(leg)
        if len(deduped) >= limit:
            break
    return deduped


def build_assistant_recommendations(packets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Deep-scan all packets; return singles, accas, highlights, and eligibility summary."""
    scanned = len(packets)
    eligible: List[Dict[str, Any]] = []
    excluded: Dict[str, int] = {}
    for p in packets:
        reason = _exclusion_reason(p)
        if reason:
            excluded[reason] = excluded.get(reason, 0) + 1
        else:
            eligible.append(p)

    ranked = _rank_all_legs(packets)
    best_singles: List[Dict[str, Any]] = []
    for leg in ranked[:12]:
        pkt = next((p for p in packets if p.get("id") == leg.get("fixture_id")), {})
        best_singles.append(
            {
                **leg,
                "rationale": _leg_rationale(pkt, leg),
                "match": _match_label(pkt),
            }
        )

    btts_legs = _legs_for_acca_type(packets, "btts")
    o25_legs = _legs_for_acca_type(packets, "over25")
    o15_legs = _legs_for_acca_type(packets, "over15")
    win_legs = _legs_for_acca_type(packets, "win")
    value_legs = _legs_for_acca_type(packets, "value")
    mixed_legs_acca = build_mixed_market_acca(packets)
    bet_builders = build_bet_builder_suggestions(packets)

    acca_suggestions: List[Dict[str, Any]] = []
    acca_defs: List[Tuple[str, str, List[Dict[str, Any]], List[str]]] = [
        (
            "BTTS Acca",
            "btts",
            btts_legs,
            [
                "Legs require BTTS Yes model ≥ threshold and synced book prices.",
                "Only fixtures with strong form samples and data coverage included.",
            ],
        ),
        (
            "Over 2.5 Goals Acca",
            "over25",
            o25_legs,
            [
                "Selected where Poisson/xG blend favours open games with O2.5 model support.",
                "Combined odds are illustrative — verify at your bookmaker.",
            ],
        ),
        (
            "Over 1.5 Goals Acca",
            "over15",
            o15_legs,
            [
                "Safer goals ladder; higher hit rate but shorter prices.",
                "Still filtered to analyzable fixtures only.",
            ],
        ),
        (
            "Over 3.5 Goals Acca",
            "over35",
            _legs_for_acca_type(packets, "over35"),
            [
                "Higher-variance goal line; only when model supports open-score profiles.",
                "Use smaller stakes than O1.5/O2.5 accas.",
            ],
        ),
        (
            "Match Winner Acca",
            "win",
            win_legs,
            [
                "Outright home/away only when model clears win threshold — no forced favourites.",
                "Draws excluded from win acca by design.",
            ],
        ),
        (
            "Value Mixed Acca",
            "value",
            value_legs,
            [
                "Each leg flagged value vs model fair price with adequate data.",
                "Conservative joint confidence uses product × min-leg blend.",
            ],
        ),
    ]
    for title, atype, legs, rat in acca_defs:
        built = _build_acca(title, atype, legs, rat)
        if built:
            acca_suggestions.append(built)
    if mixed_legs_acca:
        acca_suggestions.append(mixed_legs_acca)

    return {
        "deep_dive_summary": {
            "fixtures_scanned": scanned,
            "fixtures_eligible": len(eligible),
            "fixtures_excluded": scanned - len(eligible),
            "excluded_by_reason": excluded,
            "min_data_pct": assistant_min_data_pct(),
            "min_form_matches": assistant_min_form_matches(),
            "summary_line": (
                f"Deep-dived {scanned} fixtures: {len(eligible)} meet professional data bar "
                f"(≥{assistant_min_data_pct():.0f}% coverage, form sample, full model)."
            ),
        },
        "best_singles": best_singles[:8],
        "acca_suggestions": acca_suggestions,
        "bet_builder_suggestions": bet_builders,
        "market_highlights": _market_highlights(packets),
        "small_stake_picks": build_small_stake_picks(packets),
        "disclaimer": _DISCLAIMER,
    }
