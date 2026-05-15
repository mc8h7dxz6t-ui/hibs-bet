"""
Natural-language handler for the Betting Assistant (rule-based on live packets + recommendations).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from hibs_predictor.assistant_recommendations import (
    _exclusion_reason,
    _kickoff_display,
    _match_label,
    build_assistant_recommendations,
    build_mixed_market_acca,
    is_analyzable,
)

_HELP_LINES = [
    "Ask in plain English — I use the same live model, odds, and data-quality gates as the dashboard.",
    "Examples:",
    "• “best bets” or “top singles by stats”",
    "• “BTTS acca” / “over 2.5 acca” / “win acca” / “over 1.5” / “over 3.5”",
    "• “mixed acca” or “multi market acca” (strongest leg per match, any market)",
    "• “value bets” / “deep dive all fixtures”",
    "• “stats for Hibs v Hearts” or “analyze Rangers” (pick a fixture in the dropdown to focus)",
    "• “why low data” / “xg and form” on the selected match",
]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _tokens(q: str) -> List[str]:
    return [t for t in re.split(r"[^a-z0-9]+", _norm(q)) if len(t) >= 2]


def _find_packets(packets: List[Dict[str, Any]], query: str, fixture_id: Optional[Any] = None) -> List[Dict[str, Any]]:
    if fixture_id is not None and str(fixture_id).strip():
        fid = str(fixture_id)
        for p in packets:
            if str(p.get("id")) == fid:
                return [p]
    toks = _tokens(query)
    if not toks:
        return []
    hits: List[Tuple[int, Dict[str, Any]]] = []
    for p in packets:
        hay = _norm(
            f"{p.get('home', '')} {p.get('away', '')} {p.get('league_name', '')} {p.get('league', '')}"
        )
        score = sum(1 for t in toks if t in hay)
        if score > 0:
            hits.append((score, p))
    hits.sort(key=lambda x: -x[0])
    return [p for _, p in hits[:3]]


def _ensure_recommendations(
    packets: List[Dict[str, Any]], recommendations: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    if recommendations:
        return recommendations
    return build_assistant_recommendations(packets)


def _acca_by_type(rec: Dict[str, Any], atype: str) -> List[Dict[str, Any]]:
    return [a for a in (rec.get("acca_suggestions") or []) if a.get("type") == atype]


def _stats_reply(pkt: Dict[str, Any]) -> Dict[str, Any]:
    si = pkt.get("structured_insight") or {}
    ps = pkt.get("probability_scores") or {}
    lines = [
        f"**{_match_label(pkt)}**" + (f" · KO {_kickoff_display(pkt)}" if _kickoff_display(pkt) else ""),
        f"Data coverage: **{pkt.get('data_quality_pct', '—')}%**",
        f"Structured pick: **{si.get('pick', '—')}**"
        + (f" ({si.get('confidence_pct')}% conf.)" if si.get("confidence_pct") is not None else ""),
    ]
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
    if ps.get("xg_home") is not None:
        lines.append(f"xG lean: {ps['xg_home']} – {ps.get('xg_away', '?')}")
    if si.get("predicted_scoreline"):
        lines.append(f"Scoreline: {si['predicted_scoreline']}")
    if si.get("rationale"):
        lines.extend(si["rationale"][:3])
    return {"lines": lines, "packet": pkt}


def parse_intent(question: str) -> Tuple[str, Dict[str, Any]]:
    q = _norm(question)
    if not q:
        return "help", {}
    if any(x in q for x in ("help", "what can you", "how do i", "commands")):
        return "help", {}
    if any(x in q for x in ("deep dive", "deep-dive", "scan all", "all fixtures", "full scan")):
        return "deep_dive", {}
    if any(x in q for x in ("mixed acca", "multi market", "multi-market", "several markets", "same bet")):
        return "mixed_acca", {}
    if "btts" in q and "acca" in q:
        return "acca", {"type": "btts"}
    if any(x in q for x in ("over 2.5", "o2.5", "over 2_5", "goals acca")) or ("over" in q and "2.5" in q):
        return "acca", {"type": "over25"}
    if any(x in q for x in ("over 1.5", "o1.5")) or ("over" in q and "1.5" in q):
        return "acca", {"type": "over15"}
    if any(x in q for x in ("over 3.5", "o3.5")) or ("over" in q and "3.5" in q):
        return "acca", {"type": "over35"}
    if ("win" in q or "winner" in q) and "acca" in q:
        return "acca", {"type": "win"}
    if any(x in q for x in ("value bet", "value scan", "edge", "ev ")):
        return "value", {}
    if any(x in q for x in ("best single", "best bet", "top bet", "best pick", "strongest bet")):
        return "best_singles", {}
    if "acca" in q or "accumulator" in q or "parlay" in q:
        return "mixed_acca", {}
    if any(x in q for x in ("stats", "xg", "form", "data quality", "coverage", "probability", "model")):
        return "stats", {}
    if any(x in q for x in ("analyze", "analysis", "breakdown", "tell me about", " v ", " vs ")):
        return "analyze", {}
    return "general", {}


def handle_chat(
    question: str,
    packets: List[Dict[str, Any]],
    recommendations: Optional[Dict[str, Any]] = None,
    fixture_id: Optional[Any] = None,
) -> Dict[str, Any]:
    """Return structured assistant reply for the UI."""
    rec = _ensure_recommendations(packets, recommendations)
    intent, params = parse_intent(question)
    out: Dict[str, Any] = {
        "intent": intent,
        "question": question,
        "disclaimer": rec.get("disclaimer"),
        "blocks": [],
    }

    if intent == "help":
        out["blocks"] = [{"type": "text", "lines": _HELP_LINES}]
        return out

    if intent == "deep_dive":
        out["blocks"] = [
            {"type": "summary", "data": rec.get("deep_dive_summary")},
            {"type": "accas", "items": rec.get("acca_suggestions") or []},
            {"type": "highlights", "data": rec.get("market_highlights") or {}},
        ]
        return out

    if intent == "best_singles":
        singles = rec.get("best_singles") or []
        if not singles:
            out["blocks"] = [{"type": "text", "lines": ["No singles cleared the data bar right now. Try “deep dive all”."]}]
        else:
            out["blocks"] = [{"type": "singles", "items": singles[:8]}]
        return out

    if intent == "acca":
        atype = params.get("type", "btts")
        accas = _acca_by_type(rec, atype)
        if not accas:
            mixed = build_mixed_market_acca(packets)
            if mixed and atype != "mixed":
                out["blocks"] = [
                    {
                        "type": "text",
                        "lines": [
                            f"Not enough legs for a {atype} acca (need 3+ with prices).",
                            "Here is a multi-market acca using the strongest stats per match instead:",
                        ],
                    },
                    {"type": "accas", "items": [mixed]},
                ]
            else:
                out["blocks"] = [
                    {
                        "type": "text",
                        "lines": [
                            f"No {atype} acca with 3+ eligible legs and book prices.",
                            "Ask “mixed acca” or “deep dive all”.",
                        ],
                    }
                ]
        else:
            out["blocks"] = [{"type": "accas", "items": accas}]
        return out

    if intent == "mixed_acca":
        mixed = _acca_by_type(rec, "mixed")
        if not mixed:
            built = build_mixed_market_acca(packets)
            if built:
                mixed = [built]
        if not mixed:
            out["blocks"] = [{"type": "text", "lines": ["Could not build a 3+ leg multi-market acca — refresh fixtures or lower data bar in .env."]}]
        else:
            out["blocks"] = [{"type": "accas", "items": mixed}]
        return out

    if intent == "value":
        hits = [p for p in packets if p.get("has_value_bet") and is_analyzable(p)]
        if not hits:
            out["blocks"] = [{"type": "text", "lines": ["No value-flagged fixtures with full model data in this window."]}]
        else:
            out["blocks"] = [{"type": "fixtures", "items": hits[:10], "compact": True}]
        return out

    if intent in ("stats", "analyze", "general"):
        matches = _find_packets(packets, question, fixture_id)
        if not matches and fixture_id:
            matches = _find_packets(packets, "", fixture_id)
        if not matches:
            if intent == "general":
                out["blocks"] = [
                    {"type": "text", "lines": _HELP_LINES[:2] + ["Could not match a team or fixture — select one in the dropdown or name both sides."]}
                ]
            else:
                out["blocks"] = [{"type": "text", "lines": ["No matching fixture — select one above or name both teams (e.g. Hibs v Hearts)."]}]
            return out
        blocks: List[Dict[str, Any]] = []
        for pkt in matches:
            reason = _exclusion_reason(pkt)
            if reason:
                blocks.append(
                    {
                        "type": "text",
                        "lines": [
                            f"{_match_label(pkt)}: excluded ({reason.replace('_', ' ')}) — not used in accas.",
                        ],
                    }
                )
                continue
            st = _stats_reply(pkt)
            blocks.append({"type": "stats", "lines": st["lines"], "packet": pkt})
            if intent == "analyze":
                blocks.append({"type": "fixture", "packet": pkt, "compact": False})
        if intent == "general" and len(blocks) == 1 and blocks[0].get("type") == "stats":
            blocks.append(
                {
                    "type": "text",
                    "lines": ["Tip: ask “mixed acca”, “best bets”, or “BTTS acca” for built slips."],
                }
            )
        out["blocks"] = blocks
        return out

    out["blocks"] = [{"type": "text", "lines": _HELP_LINES}]
    return out
