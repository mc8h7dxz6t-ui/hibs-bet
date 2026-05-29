"""
Natural-language handler for the Betting Assistant (rule-based on live packets + recommendations).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from hibs_predictor.acca_review import review_acca_legs
from hibs_predictor.assistant_context import (
    _live_snippet,
    acca_greeting_lines,
    build_acca_candidates,
    build_acca_window_summary,
    build_best_acca_ideas,
    build_fixture_context_lines,
    build_fixtures_summary,
    enrich_acca_items,
    enrich_leg_list,
    pick_recommendation_line,
)
from hibs_predictor.assistant_facts import INSUFFICIENT_DATA_LINE, snapshot_refusal_line
from hibs_predictor.assistant_recommendations import (
    _exclusion_reason,
    _kickoff_display,
    _match_label,
    assistant_min_data_pct,
    build_assistant_recommendations,
    build_bet_builder_suggestions,
    build_mixed_market_acca,
    build_multi_leg_btts_acca,
    build_ranked_btts_legs,
    build_small_stake_picks,
    build_win_btts_combo_suggestions,
    is_analyzable,
)

_HELP_LINES = [
    "Today's card — leagues loaded, value flags, live games (same dq gates as the dashboard).",
    "BTTS: btts 10 fold · best 3 btts · best 3 btts win (detailed reasoning)",
    "Accas: best acca · acca tips · suggest legs · BTTS acca · mixed acca · 3-leg safer acca",
    "Small stakes: small stakes · what to bet · stake picks (value + model % + suggested % bankroll)",
    "Singles & review: value bets · best singles · review acca (on /acca)",
    "One fixture: stats / table / bet builder for Team A v Team B",
]

_CARD_WIDE_INTENTS = frozenset(
    {
        "help",
        "general",
        "best_acca",
        "suggest_legs",
        "acca_builder",
        "live",
        "value",
        "mixed_acca",
        "acca",
        "best_singles",
        "small_stakes",
        "btts_acca",
        "multi_leg_btts",
        "win_btts_combo",
    }
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _tokens(q: str) -> List[str]:
    return [t for t in re.split(r"[^a-z0-9]+", _norm(q)) if len(t) >= 2]


def _effective_fixture_id(
    question: str,
    fixture_id: Optional[Any],
    intent: str,
) -> Optional[Any]:
    """Use dashboard fixture context only when the question is fixture-scoped."""
    if fixture_id is None or not str(fixture_id).strip():
        return None
    if intent not in _CARD_WIDE_INTENTS:
        return fixture_id
    q = _norm(question)
    if not q:
        return fixture_id
    if intent == "deep_dive" and any(x in q for x in ("this game", "this match", "this fixture")):
        return fixture_id
    if _tokens(question):
        return None
    return fixture_id


def _card_overview_blocks(packets: List[Dict[str, Any]], rec: Dict[str, Any]) -> List[Dict[str, Any]]:
    summary = rec.get("deep_dive_summary") or {}
    lines = [
        build_acca_window_summary(packets),
        summary.get("summary_line") or f"**{len(packets)}** fixture(s) in the assistant window.",
    ]
    live_n = sum(1 for p in packets if p.get("is_live"))
    value_n = sum(1 for p in packets if p.get("has_value_bet") and is_analyzable(p))
    if live_n:
        lines.append(f"**{live_n}** in play — ask **live** for scores.")
    if value_n:
        lines.append(f"**{value_n}** with value flags — ask **value bets**.")
    blocks: List[Dict[str, Any]] = [{"type": "text", "lines": lines}]
    card = build_fixtures_summary(packets, max_n=12)
    if card:
        blocks.append({"type": "fixtures", "items": card, "compact": True})
    return blocks


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
    lines = build_fixture_context_lines(pkt)
    pick_line = pick_recommendation_line(pkt)
    if pick_line:
        lines.append(f"Bet pick (dq ≥ {assistant_min_data_pct():.0f}%): {pick_line}")
    elif _exclusion_reason(pkt):
        lines.append(
            f"No stake-style pick — data/form below assistant bar ({assistant_min_data_pct():.0f}%) "
            f"or mode { (pkt.get('structured_insight') or {}).get('mode', 'n/a') }."
        )
    si = pkt.get("structured_insight") or {}
    if si.get("rationale"):
        for bullet in si["rationale"][:2]:
            if bullet not in lines:
                lines.append(bullet)
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


def _wants_detailed_reasoning(q: str) -> bool:
    return any(
        x in q
        for x in (
            "detailed",
            "detail",
            "reasoning",
            "reason",
            "explain",
            "why",
            "breakdown",
            "rationale",
            "analysis",
        )
    )


def _parse_fold_or_leg_count(q: str) -> Optional[int]:
    for pat in (
        r"\b(\d{1,2})\s*[- ]?\s*fold\b",
        r"\b(\d{1,2})\s*[- ]?\s*leg\b",
        r"\b(\d{1,2})\s*fold\b",
        r"\b(\d{1,2})\s*picker\b",
    ):
        m = re.search(pat, q)
        if m:
            return min(10, max(2, int(m.group(1))))
    m = re.search(r"\b(?:best|top)\s+(\d{1,2})\b", q)
    if m:
        return min(10, max(1, int(m.group(1))))
    if "double" in q or "2-fold" in q or "2 fold" in q:
        return 2
    if "treble" in q or "3-fold" in q or "3 fold" in q:
        return 3
    if "4-fold" in q or "4 fold" in q or "fourfold" in q:
        return 4
    if "5-fold" in q or "5 fold" in q:
        return 5
    if "6-fold" in q or "6 fold" in q:
        return 6
    if "7-fold" in q or "7 fold" in q:
        return 7
    if "8-fold" in q or "8 fold" in q:
        return 8
    if "9-fold" in q or "9 fold" in q:
        return 9
    if "10-fold" in q or "10 fold" in q or "tenfold" in q:
        return 10
    return None


def _parse_leg_count(q: str) -> Optional[int]:
    n = _parse_fold_or_leg_count(q)
    if n is not None and n >= 2:
        return n
    return None


def _btts_multi_leg_params(q: str) -> Dict[str, Any]:
    n = _parse_fold_or_leg_count(q)
    if n is None and any(x in q for x in ("acca", "accumulator", "parlay", "fold")):
        n = 3
    wants_acca = any(x in q for x in ("fold", "acca", "accumulator", "parlay", "treble", "double"))
    ranked_only = any(x in q for x in ("best", "top")) and not wants_acca
    return {
        "leg_count": n or 3,
        "detailed": _wants_detailed_reasoning(q),
        "ranked_only": ranked_only,
    }


def parse_intent(question: str) -> Tuple[str, Dict[str, Any]]:
    q = _norm(question)
    if not q:
        return "general", {}
    if any(x in q for x in ("help", "what can you", "how do i", "commands")):
        return "help", {}
    if any(x in q for x in ("best acca", "acca tips", "acca tip", "top acca", "acca ideas", "acca picks")):
        return "best_acca", {}
    if any(x in q for x in ("suggest legs", "leg options", "pick legs", "acca legs", "choose legs", "leg picker")):
        return "suggest_legs", {}
    if any(x in q for x in ("build acca", "make acca", "acca builder", "stack acca")) or (
        "acca" in q and any(x in q for x in ("safer", "bigger", "price", "odds", "leg"))
    ):
        prefer_safer = any(x in q for x in ("safer", "safe", "lower odds", "banker"))
        return "acca_builder", {"prefer_safer": prefer_safer, "leg_count": _parse_leg_count(q)}
    if any(x in q for x in ("deep dive", "deep-dive", "scan all", "all fixtures", "full scan")):
        return "deep_dive", {}
    if any(x in q for x in ("bet builder", "builder", "same game", "sgm", "game line", "game-line")):
        return "bet_builder", {}
    if any(x in q for x in ("table", "standings", "league position", "league table", "points", "goal difference", "gd", "one above", "one below")):
        return "table", {}
    if any(x in q for x in ("mixed acca", "multi market", "multi-market", "several markets", "same bet")):
        return "mixed_acca", {}
    win_btts = ("btts" in q and ("win" in q or "winner" in q or "result" in q)) or any(
        x in q for x in ("win and btts", "win + btts", "winner btts", "home and btts", "away and btts")
    )
    if win_btts:
        n = _parse_fold_or_leg_count(q) or 3
        return "win_btts_combo", {"leg_count": min(10, max(1, n)), "detailed": _wants_detailed_reasoning(q)}
    if "btts" in q and any(
        x in q
        for x in (
            "fold",
            "leg",
            "picker",
            "best",
            "top",
            "acca",
            "accumulator",
            "parlay",
            "treble",
            "double",
        )
    ):
        params = _btts_multi_leg_params(q)
        intent = "multi_leg_btts" if params.get("ranked_only") else "btts_acca"
        return intent, params
    if "btts" in q and any(x in q for x in ("best", "top")):
        params = _btts_multi_leg_params(q)
        params["ranked_only"] = True
        return "multi_leg_btts", params
    if "btts" in q and "acca" in q:
        return "btts_acca", {"leg_count": _parse_fold_or_leg_count(q) or 3, "detailed": _wants_detailed_reasoning(q)}
    if any(x in q for x in ("over 2.5", "o2.5", "over 2_5", "goals acca")) or ("over" in q and "2.5" in q):
        return "acca", {"type": "over25"}
    if any(x in q for x in ("over 1.5", "o1.5")) or ("over" in q and "1.5" in q):
        return "acca", {"type": "over15"}
    if any(x in q for x in ("over 3.5", "o3.5")) or ("over" in q and "3.5" in q):
        return "acca", {"type": "over35"}
    if ("win" in q or "winner" in q) and "acca" in q:
        return "acca", {"type": "win"}
    if any(x in q for x in ("review acca", "review slip", "review my acca", "review betslip", "acca review", "review legs")):
        return "acca_review", {}
    if any(x in q for x in ("in play", "in-play", "live score", "live game", "live match")) or (
        "live" in q and any(x in q for x in ("fixture", "game", "match", "score", "now"))
    ):
        return "live", {}
    if any(
        x in q
        for x in (
            "small stake",
            "small stakes",
            "what to bet",
            "stake pick",
            "stake picks",
            "which value",
            "which bet",
            "low stakes",
        )
    ):
        return "small_stakes", {}
    if any(x in q for x in ("value bet", "value scan", "edge", "ev ", "dual agree", "dual finder")):
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


def _refusal_blocks(line: str) -> List[Dict[str, Any]]:
    return [{"type": "text", "lines": [line]}]


def _dq_below_bar(dq: Any) -> bool:
    if dq is None:
        return True
    return float(dq) < assistant_min_data_pct()


def handle_chat(
    question: str,
    packets: List[Dict[str, Any]],
    recommendations: Optional[Dict[str, Any]] = None,
    fixture_id: Optional[Any] = None,
    legs: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Return structured assistant reply for the UI."""
    rec = _ensure_recommendations(packets, recommendations)
    intent, params = parse_intent(question)
    fixture_id = _effective_fixture_id(question, fixture_id, intent)
    out: Dict[str, Any] = {
        "intent": intent,
        "question": question,
        "disclaimer": rec.get("disclaimer"),
        "blocks": [],
    }

    refusal = snapshot_refusal_line(packets, intent, params)
    if refusal:
        out["blocks"] = _refusal_blocks(refusal)
        return out

    if intent == "help":
        out["blocks"] = [
            {"type": "text", "lines": acca_greeting_lines(packets)},
            {"type": "text", "lines": _HELP_LINES},
        ]
        return out

    if intent == "best_acca":
        ideas = build_best_acca_ideas(rec, max_ideas=5)
        lines = ["Here are the strongest acca ideas on today's card (2–4 legs each)."]
        thin = [
            l.get("market_label")
            for a in ideas
            for l in (a.get("legs") or [])
            if _dq_below_bar(l.get("data_quality_pct"))
        ]
        if thin:
            lines.append(f"Caution: thin dq on — {', '.join(thin[:3])}.")
        if not ideas:
            lines.append(INSUFFICIENT_DATA_LINE)
            out["blocks"] = [{"type": "text", "lines": lines}]
        else:
            out["blocks"] = [
                {"type": "text", "lines": lines},
                {"type": "accas", "items": ideas},
            ]
        return out

    if intent == "acca_builder":
        n = params.get("leg_count")
        ideas = build_best_acca_ideas(
            rec,
            max_ideas=4,
            target_legs=n,
            prefer_safer=bool(params.get("prefer_safer")),
        )
        tone = "safer" if params.get("prefer_safer") else "bigger price"
        leg_hint = f"{n}-leg " if n else ""
        lines = [f"Built {leg_hint}acca ideas leaning {tone} — tap Add to slip on any leg or add the whole acca."]
        if not ideas:
            lines.append("Could not stack enough legs — try suggest legs or lower the data bar.")
            out["blocks"] = [{"type": "text", "lines": lines}]
        else:
            out["blocks"] = [
                {"type": "text", "lines": lines},
                {"type": "accas", "items": ideas},
                {"type": "suggest_legs", "items": build_acca_candidates(packets, limit=14)},
            ]
        return out

    if intent == "suggest_legs":
        candidates = build_acca_candidates(packets)
        out["blocks"] = [
            {
                "type": "text",
                "lines": [
                    "Leg options from today's card — mix your own acca (one pick per game on the slip).",
                    build_acca_window_summary(packets),
                ],
            },
            {"type": "suggest_legs", "items": candidates},
        ]
        return out

    if intent == "acca_review":
        if not legs:
            out["blocks"] = [
                {
                    "type": "text",
                    "lines": [
                        "Add legs on the **Acca Builder** (/acca), then click **Review acca with AI**.",
                        "Or POST legs to `/api/assistant/acca-review` with fixture_id, market, and odds per selection.",
                    ],
                }
            ]
            return out
        review = review_acca_legs(legs, packets)
        out["blocks"] = [
            {"type": "text", "lines": [review.get("summary") or ""]},
            {"type": "acca_review", "data": review},
        ]
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
            {"type": "accas", "items": enrich_acca_items(rec.get("acca_suggestions") or [])},
            {"type": "builders", "items": rec.get("bet_builder_suggestions") or []},
            {"type": "highlights", "data": rec.get("market_highlights") or {}},
        ]
        return out

    if intent == "best_singles":
        singles = rec.get("best_singles") or []
        if not singles:
            out["blocks"] = [{"type": "text", "lines": ["No singles cleared the data bar right now. Try “deep dive all”."]}]
        else:
            extra: List[Dict[str, Any]] = []
            for leg in singles[:8]:
                pkt = next((p for p in packets if str(p.get("id")) == str(leg.get("fixture_id"))), None)
                if pkt:
                    pl = pick_recommendation_line(pkt, market_key=leg.get("market_key"), odds=leg.get("odds"), model_pct=leg.get("model_pct"))
                    if pl:
                        leg = {**leg, "pick_detail": pl.replace("**", "")}
                extra.append(leg)
            out["blocks"] = [{"type": "singles", "items": extra}]
        return out

    if intent in ("btts_acca", "multi_leg_btts"):
        n = min(10, max(2, int(params.get("leg_count") or 3)))
        detailed = bool(params.get("detailed"))
        ranked_only = bool(params.get("ranked_only"))
        if ranked_only:
            legs = build_ranked_btts_legs(packets, limit=n, detailed=detailed)
            lines = [f"Top **{n}** BTTS Yes picks on today's card (ranked by model + data bar)."]
            if len(legs) < n:
                lines.append(
                    f"Only **{len(legs)}** qualified — I won't invent legs for a {n}-fold."
                )
            if not legs:
                lines.append("No BTTS legs with prices and model support — try mixed acca or refresh.")
                out["blocks"] = [{"type": "text", "lines": lines}]
            else:
                out["blocks"] = [
                    {"type": "text", "lines": lines},
                    {"type": "suggest_legs", "items": enrich_leg_list(legs, packets)},
                ]
            return out
        built = build_multi_leg_btts_acca(packets, target_legs=n, detailed=detailed)
        lines = [
            f"BTTS acca — requested **{built.get('requested_count', n)}** legs, "
            f"**{built.get('qualified_count', 0)}** on card."
        ]
        intro_extra = (built.get("rationale") or [])[:1]
        if intro_extra:
            lines.extend(intro_extra)
        if not built.get("legs"):
            out["blocks"] = [{"type": "text", "lines": lines}]
        else:
            out["blocks"] = [
                {"type": "text", "lines": lines},
                {"type": "accas", "items": enrich_acca_items([built])},
            ]
        return out

    if intent == "win_btts_combo":
        n = min(10, max(1, int(params.get("leg_count") or 3)))
        detailed = bool(params.get("detailed"))
        combos = build_win_btts_combo_suggestions(packets, limit=n, detailed=detailed)
        lines = [
            f"Top **{n}** win + BTTS combo legs (priced combo markets from the snapshot)."
        ]
        if detailed:
            lines.append("Detailed reasoning per pick below — all figures from live fixture data.")
        if len(combos) < n:
            lines.append(
                f"Only **{len(combos)}** combos cleared the bar — no invented stats to fill a {n}-picker."
            )
        if not combos:
            lines.append(
                "No home/away win+BTTS combos with book prices right now — try bet builder on a named fixture."
            )
            out["blocks"] = [{"type": "text", "lines": lines}]
        else:
            out["blocks"] = [
                {"type": "text", "lines": lines},
                {"type": "suggest_legs", "items": enrich_leg_list(combos, packets)},
            ]
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
                    {"type": "accas", "items": enrich_acca_items([mixed])},
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
            out["blocks"] = [{"type": "accas", "items": enrich_acca_items(accas)}]
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
            out["blocks"] = [{"type": "accas", "items": enrich_acca_items(mixed)}]
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

    if intent == "live":
        live_hits = [p for p in packets if p.get("is_live")]
        if not live_hits:
            out["blocks"] = [
                {
                    "type": "text",
                    "lines": ["No in-play fixtures in the current window — refresh during match hours."],
                }
            ]
        else:
            lines = [f"**{len(live_hits)}** fixture(s) in play:"]
            for pkt in live_hits[:12]:
                snip = _live_snippet(pkt)
                if snip:
                    lines.append(f"{_match_label(pkt)} — {snip}.")
            out["blocks"] = [
                {"type": "text", "lines": lines},
                {"type": "fixtures", "items": live_hits[:10], "compact": False},
            ]
        return out

    if intent == "small_stakes":
        stake = rec.get("small_stake_picks") or build_small_stake_picks(packets)
        lines = list(stake.get("summary_lines") or [])
        picks = stake.get("picks") or []
        if not picks:
            lines.append(
                "No value legs cleared the bar (need value flag, edge, prices, and analyzable data). "
                "Try **value bets** for the wider scan."
            )
            out["blocks"] = [{"type": "text", "lines": lines}]
        else:
            lines.append(
                f"**{stake.get('bettable_count', 0)}** small-stake candidate(s) "
                f"(max ~{stake.get('max_stake_pct')}% bankroll per pick in this phase)."
            )
            out["blocks"] = [
                {"type": "text", "lines": lines},
                {"type": "small_stakes", "items": picks},
            ]
        return out

    if intent == "value":
        hits = [p for p in packets if p.get("has_value_bet") and is_analyzable(p)]
        dual = [p for p in hits if p.get("has_value_dual_agree")]
        stake = rec.get("small_stake_picks") or build_small_stake_picks(packets, limit=3)
        picks = stake.get("picks") or []
        if not hits:
            out["blocks"] = [{"type": "text", "lines": ["No value-flagged fixtures with full model data in this window."]}]
        else:
            intro = [f"**{len(hits)}** value-flagged fixture(s) with full model data."]
            if dual:
                intro.append(f"**{len(dual)}** with dual-finder agreement (model + consensus).")
            if picks:
                intro.append(
                    f"Top stake ideas: ask **small stakes** for model % vs line + suggested % bankroll "
                    f"({len(picks)} ranked below)."
                )
            blocks: List[Dict[str, Any]] = [
                {"type": "text", "lines": intro},
                {"type": "fixtures", "items": hits[:10], "compact": True},
            ]
            if picks:
                blocks.append({"type": "small_stakes", "items": picks[:3]})
            out["blocks"] = blocks
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
                out["blocks"] = _card_overview_blocks(packets, rec)
                ideas = build_best_acca_ideas(rec, max_ideas=2)
                if ideas:
                    out["blocks"].append({"type": "accas", "items": ideas})
                out["blocks"].append(
                    {
                        "type": "text",
                        "lines": [
                            "Ask about the whole card (live, value, leagues) or name a fixture for stats / table / bet builder.",
                            "Accas: **best acca**, **suggest legs**, **BTTS acca**.",
                        ],
                    }
                )
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
                    "lines": ["For accas: best acca, suggest legs, or BTTS / mixed acca."],
                }
            )
        out["blocks"] = blocks
        return out

    out["blocks"] = [{"type": "text", "lines": _HELP_LINES}]
    return out
