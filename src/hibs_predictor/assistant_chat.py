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
    build_bet_builder_suggestions,
    build_mixed_market_acca,
    is_analyzable,
)

_HELP_LINES = [
    "Ask in plain English — I use the same live model, odds, and data-quality gates as the dashboard.",
    "Examples:",
    "• “best bets” or “top singles by stats”",
    "• “BTTS acca” / “over 2.5 acca” / “win acca” / “over 1.5” / “over 3.5”",
    "• “mixed acca” or “multi market acca” (strongest leg per match, any market)",
    "• “bet builder for this game” for correlated same-game market ideas",
    "• “value bets” / “deep dive all fixtures”",
    "• “stats for Hibs v Hearts”, “analyze Rangers”, “why Arsenal value?”, “xG and form for Chelsea”",
    "• “table”, “standings”, “why league position matters”, “team news”, “what is missing?”",
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


def _is_ambiguous_match(matches: List[Dict[str, Any]], question: str) -> bool:
    if len(matches) < 2:
        return False
    toks = set(_tokens(question))
    # If the user named both teams, the top scorer is usually enough.
    top_names = set(_tokens(f"{matches[0].get('home', '')} {matches[0].get('away', '')}"))
    return len(toks & top_names) < 2


def _clarification_lines(matches: List[Dict[str, Any]]) -> List[str]:
    lines = ["I found more than one possible fixture. Which one do you mean?"]
    for pkt in matches[:3]:
        ko = f" · {_kickoff_display(pkt)}" if _kickoff_display(pkt) else ""
        lines.append(f"• {_match_label(pkt)}{ko}")
    lines.append("Reply with both teams, e.g. “deep dive Team A v Team B”.")
    return lines


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
    if pkt.get("trust_label"):
        lines.append(f"Trust read: **{pkt.get('trust_label')}**")
    weak = pkt.get("weak_fields") or []
    if weak:
        lines.append("Weakest inputs: " + ", ".join(str(x) for x in weak[:3]) + ".")
    profile = pkt.get("league_model_profile") or {}
    if profile.get("label"):
        lines.append(f"League profile: {profile.get('label')} — {profile.get('description')}")
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
    rejected = pkt.get("value_bets_rejected") or {}
    if rejected:
        lines.append(
            "Value guardrails blocked: "
            + ", ".join(f"{k} ({v})" for k, v in list(rejected.items())[:3])
            + "."
        )
    return {"lines": lines, "packet": pkt}


def _position_summary(pos: Dict[str, Any], team: str) -> str:
    if not pos or not pos.get("position"):
        return f"{team}: table data unavailable."
    parts = [
        f"{team}: **{pos.get('position')}**",
        f"{pos.get('points', '—')} pts",
    ]
    if pos.get("played") is not None:
        parts.append(f"P{pos.get('played')}")
    if pos.get("goal_diff") is not None:
        gd = pos.get("goal_diff")
        gd_s = f"+{gd}" if isinstance(gd, (int, float)) and gd > 0 else str(gd)
        parts.append(f"GD {gd_s}")
    if pos.get("form"):
        parts.append(f"form {pos.get('form')}")
    src = pos.get("source")
    if src:
        parts.append(f"source {src}")
    return " · ".join(parts)


def _adjacent_summary(pos: Dict[str, Any], team: str) -> List[str]:
    lines: List[str] = []
    for key, label in (("above", "one above"), ("below", "one below")):
        row = pos.get(key) if isinstance(pos, dict) else None
        if isinstance(row, dict) and row.get("team"):
            pts = row.get("points", "—")
            gd = row.get("goal_diff", "—")
            lines.append(f"{team} {label}: {row.get('team')} ({pts} pts, GD {gd}).")
    return lines


def _table_reply(pkt: Dict[str, Any]) -> Dict[str, Any]:
    hp = pkt.get("home_position") or {}
    ap = pkt.get("away_position") or {}
    home = pkt.get("home") or "Home"
    away = pkt.get("away") or "Away"
    lines = [
        f"**Table context: {_match_label(pkt)}**",
        _position_summary(hp, home),
        _position_summary(ap, away),
    ]
    if hp.get("position") and ap.get("position"):
        try:
            pos_gap = int(ap.get("position")) - int(hp.get("position"))
            pts_gap = int(hp.get("points") or 0) - int(ap.get("points") or 0)
            gd_gap = int(hp.get("goal_diff") or 0) - int(ap.get("goal_diff") or 0)
            if pos_gap > 0:
                lines.append(f"{home} sit {abs(pos_gap)} places above {away}; points gap {pts_gap}, GD gap {gd_gap}.")
            elif pos_gap < 0:
                lines.append(f"{away} sit {abs(pos_gap)} places above {home}; points gap {-pts_gap}, GD gap {-gd_gap}.")
            else:
                lines.append(f"They are level on table position context; points gap {pts_gap}, GD gap {gd_gap}.")
        except (TypeError, ValueError):
            pass
    lines.extend(_adjacent_summary(hp, home))
    lines.extend(_adjacent_summary(ap, away))
    if len(lines) == 3 and "unavailable" in " ".join(lines).lower():
        lines.append("One-above/one-below snapshots are not loaded for this league yet; the assistant will use current team rows when available.")
    else:
        lines.append("Why it matters: standings anchor baseline strength, pressure, goal difference, and whether recent form is over- or under-performing league rank.")
    return {"lines": lines, "packet": pkt}


def _form_reply(pkt: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    for side, label in (("home", pkt.get("home") or "Home"), ("away", pkt.get("away") or "Away")):
        fs = pkt.get(f"{side}_form_summary") or {}
        if not fs.get("played"):
            lines.append(f"{label}: recent form unavailable.")
            continue
        lines.append(
            f"{label} last {fs.get('played')}: W{fs.get('wins')} D{fs.get('draws')} L{fs.get('losses')}, "
            f"GF {fs.get('gf')} GA {fs.get('ga')}, BTTS {fs.get('btts')}, O2.5 {fs.get('over25')}."
        )
    return lines


def _team_news_reply(pkt: Dict[str, Any]) -> List[str]:
    injuries = pkt.get("fixture_injuries") or []
    if not injuries:
        return ["Team news: no confirmed injury/absence feed loaded for this fixture."]
    lines = [f"Team news: {len(injuries)} absence rows loaded."]
    for inj in injuries[:4]:
        player = (inj.get("player") or {}).get("name") if isinstance(inj, dict) else None
        team = (inj.get("team") or {}).get("name") if isinstance(inj, dict) else None
        reason = inj.get("reason") if isinstance(inj, dict) else None
        lines.append(f"{player or 'Player'} ({team or 'team'}): {reason or 'listed absence'}.")
    return lines


def _selected_deep_dive_blocks(pkt: Dict[str, Any]) -> List[Dict[str, Any]]:
    st = _stats_reply(pkt)
    table = _table_reply(pkt)
    lines = st["lines"] + [""] + table["lines"] + [""] + _form_reply(pkt) + [""] + _team_news_reply(pkt)
    builders = build_bet_builder_suggestions([pkt], fixture_id=pkt.get("id"), limit=4)
    blocks: List[Dict[str, Any]] = [{"type": "stats", "lines": lines, "packet": pkt}]
    if builders:
        blocks.append({"type": "builders", "items": builders})
    blocks.append({"type": "fixture", "packet": pkt, "compact": False})
    return blocks


def parse_intent(question: str) -> Tuple[str, Dict[str, Any]]:
    q = _norm(question)
    if not q:
        return "help", {}
    if any(x in q for x in ("help", "what can you", "how do i", "commands")):
        return "help", {}
    if any(x in q for x in ("deep dive", "deep-dive", "scan all", "all fixtures", "full scan")):
        return "deep_dive", {}
    if any(x in q for x in ("bet builder", "builder", "same game", "sgm", "game line", "game-line")):
        return "bet_builder", {}
    if any(x in q for x in ("table", "standings", "league position", "league table", "points", "goal difference", "gd", "one above", "one below")):
        return "table", {}
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
    if any(x in q for x in ("stats", "xg", "form", "data quality", "coverage", "probability", "model", "team news", "injuries")):
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
        selected = _find_packets(packets, question, fixture_id)
        if _is_ambiguous_match(selected, question):
            out["blocks"] = [{"type": "text", "lines": _clarification_lines(selected)}]
            return out
        if selected and not any(x in _norm(question) for x in ("all fixtures", "scan all", "full scan")):
            out["blocks"] = _selected_deep_dive_blocks(selected[0])
            return out
        out["blocks"] = [
            {"type": "summary", "data": rec.get("deep_dive_summary")},
            {"type": "accas", "items": rec.get("acca_suggestions") or []},
            {"type": "builders", "items": rec.get("bet_builder_suggestions") or []},
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

    if intent == "bet_builder":
        matches = _find_packets(packets, question, fixture_id)
        if _is_ambiguous_match(matches, question):
            out["blocks"] = [{"type": "text", "lines": _clarification_lines(matches)}]
            return out
        builders = build_bet_builder_suggestions(
            packets if not matches else matches,
            fixture_id=matches[0].get("id") if matches else fixture_id,
            limit=6,
        )
        if not builders:
            out["blocks"] = [
                {
                    "type": "text",
                    "lines": [
                        "No same-game bet builder clears the current probability/data/price bar.",
                        "I will not invent player props; those need a real player-prop/team-news feed.",
                    ],
                }
            ]
        else:
            out["blocks"] = [{"type": "builders", "items": builders}]
        return out

    if intent == "value":
        hits = [p for p in packets if p.get("has_value_bet") and is_analyzable(p)]
        if not hits:
            out["blocks"] = [{"type": "text", "lines": ["No value-flagged fixtures with full model data in this window."]}]
        else:
            out["blocks"] = [{"type": "fixtures", "items": hits[:10], "compact": True}]
        return out

    if intent in ("stats", "analyze", "general", "table"):
        matches = _find_packets(packets, question, fixture_id)
        if not matches and fixture_id:
            matches = _find_packets(packets, "", fixture_id)
        if _is_ambiguous_match(matches, question):
            out["blocks"] = [{"type": "text", "lines": _clarification_lines(matches)}]
            return out
        if not matches:
            if intent == "table":
                out["blocks"] = [
                    {
                        "type": "text",
                        "lines": [
                            "Table context matters because league position, points gap and goal difference anchor baseline team strength before recent form and xG adjust the view.",
                            "For a fixture-specific table read, ask “table for Team A v Team B”.",
                            "When standings are missing, I will say so instead of pretending one-above/one-below context exists.",
                        ],
                    }
                ]
                return out
            if intent == "general":
                out["blocks"] = [
                    {"type": "text", "lines": _HELP_LINES[:2] + ["Could not match a team or fixture — name a team or both sides."]}
                ]
            else:
                out["blocks"] = [{"type": "text", "lines": ["No matching fixture — select one above or name both teams (e.g. Hibs v Hearts)."]}]
            return out
        blocks: List[Dict[str, Any]] = []
        for pkt in matches:
            reason = _exclusion_reason(pkt)
            if reason and intent not in ("stats", "analyze", "general", "table"):
                blocks.append(
                    {
                        "type": "text",
                        "lines": [
                            f"{_match_label(pkt)}: excluded ({reason.replace('_', ' ')}) — not used in accas.",
                        ],
                    }
                )
                continue
            if reason:
                blocks.append({"type": "text", "lines": [f"{_match_label(pkt)} is thin for betting ({reason.replace('_', ' ')}), but I can still explain the available data."]})
            if intent == "table":
                tb = _table_reply(pkt)
                blocks.append({"type": "stats", "lines": tb["lines"], "packet": pkt})
            elif intent == "analyze":
                blocks.extend(_selected_deep_dive_blocks(pkt))
            else:
                st = _stats_reply(pkt)
                extra = []
                qn = _norm(question)
                if "form" in qn:
                    extra.extend(_form_reply(pkt))
                if any(x in qn for x in ("team news", "injuries", "absence")):
                    extra.extend(_team_news_reply(pkt))
                blocks.append({"type": "stats", "lines": st["lines"] + extra, "packet": pkt})
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
