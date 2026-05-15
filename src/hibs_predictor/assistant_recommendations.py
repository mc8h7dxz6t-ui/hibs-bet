"""
Deep-scan assistant recommendations: singles, accas, and market highlights.
Only fixtures with sufficient data quality and full model coverage are eligible.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from hibs_predictor.match_insight import _value_bet_key

_DISCLAIMER = (
    "Data-backed view for research only — not financial advice. "
    "Stake conservatively; 18+ gamble responsibly."
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
    si = packet.get("structured_insight") or {}
    bullets: List[str] = []
    mp = leg.get("model_pct")
    if mp is not None:
        bullets.append(f"Model assigns {mp}% to {leg.get('market_label')}.")
    if leg.get("is_value") and leg.get("edge_pct") is not None:
        bullets.append(f"Book edge +{leg['edge_pct']:.1f}% vs fair line.")
    dq = packet.get("data_quality_pct")
    if dq is not None:
        bullets.append(f"Fixture data coverage {dq}% — meets analyst threshold.")
    if si.get("predicted_scoreline"):
        bullets.append(f"Scoreline lean {si['predicted_scoreline']} from xG blend.")
    return bullets[:3]


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
        "market_highlights": _market_highlights(packets),
        "disclaimer": _DISCLAIMER,
    }
