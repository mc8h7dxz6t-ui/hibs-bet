"""
Structured per-fixture insights: conservative pick, rationale, confidence, scoreline.
Odds-only mode when data coverage is insufficient (configurable leagues / DQ threshold).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

# Smaller European / Nordic leagues: prefer book prices over model picks when coverage is thin.
_ODDS_ONLY_LEAGUE_DEFAULT = frozenset(
    {
        "BELGIUM_FIRST",
        "DENMARK_SL",
        "GREECE_SL",
        "AUSTRIA_BL",
        "EREDIVISIE",
        "PRIMEIRA",
    }
)

# Pick-menu keys → value_bets / identify_value_bets outcome keys
_MENU_KEY_TO_VALUE_BET = {
    "home_win": "home",
    "away_win": "away",
    "draw": "draw",
    "btts_yes": "btts_yes",
    "btts_no": "btts_no",
    "over_15": "over15",
    "under_15": "under15",
    "over_25": "over25",
    "under_25": "under25",
    "over_35": "over35",
    "under_35": "under35",
    "home_and_btts": "home_and_btts",
    "away_and_btts": "away_and_btts",
    "draw_and_btts": "draw_and_btts",
}


def _value_bet_key(menu_key: str) -> str:
    return _MENU_KEY_TO_VALUE_BET.get(menu_key, menu_key)


_PICK_LABELS = {
    "home_or_draw": "Home or Draw",
    "away_or_draw": "Away or Draw",
    "home_win": "Home Win",
    "away_win": "Away Win",
    "home_or_away": "Home or Away Win",
    "over_25": "Over 2.5",
    "under_25": "Under 2.5",
    "over_15": "Over 1.5",
    "under_15": "Under 1.5",
    "btts_yes": "BTTS Yes",
    "btts_no": "BTTS No",
    "home_and_btts": "Home Win & BTTS",
    "away_and_btts": "Away Win & BTTS",
    "avoid": "AVOID",
    "odds_only": "Odds only (insufficient data for a pick)",
}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _odds_only_leagues() -> frozenset:
    raw = (os.getenv("HIBS_ODDS_ONLY_LEAGUES") or "").strip()
    if raw:
        return frozenset(x.strip().upper() for x in raw.split(",") if x.strip())
    return _ODDS_ONLY_LEAGUE_DEFAULT


def should_use_odds_only(fixture: Dict[str, Any], prediction: Dict[str, Any]) -> bool:
    """Return True when we surface book prices only, not a model pick."""
    if prediction.get("prediction_unavailable"):
        return True
    league = str(fixture.get("league") or "").upper()
    if league in _odds_only_leagues():
        dq = fixture.get("data_quality") or prediction.get("data_quality") or {}
        pct = float(dq.get("score_pct") or 0)
        threshold = _env_float("HIBS_ODDS_ONLY_DQ_MAX", 78.0)
        if pct < threshold:
            return True
    min_pct = _env_float("HIBS_INSIGHT_MIN_DATA_PCT", 62.0)
    dq = fixture.get("data_quality") or prediction.get("data_quality") or {}
    if float(dq.get("score_pct") or 0) < min_pct:
        return True
    n_h = int(fixture.get("home_recent_n") or 0)
    n_a = int(fixture.get("away_recent_n") or 0)
    if n_h < 2 and n_a < 2:
        return True
    return False


def _most_likely_scoreline(lam_h: float, lam_a: float) -> str:
    """Discrete score from rounded lambdas (Poisson means), capped for display."""
    h = max(0, min(4, int(round(max(0.05, lam_h)))))
    a = max(0, min(4, int(round(max(0.05, lam_a)))))
    return f"{h}-{a}"


def _pick_conservative(
    probs: Dict[str, float],
    btts: float,
    over25: float,
    lam_h: float,
    lam_a: float,
    margin: float,
) -> Tuple[str, str, float]:
    """
    Choose safest structured pick. Returns (pick_key, pick_label, confidence 0-100).
  margin: minimum edge over second-best for outright picks.
    """
    ph, pd, pa = probs.get("home", 0.0), probs.get("draw", 0.0), probs.get("away", 0.0)
    hdc = ph + pd
    adc = pa + pd
    hoa = ph + pa
    spread = max(ph, pd, pa) - sorted([ph, pd, pa])[1]

    # Very flat 1X2 → double chance or avoid
    if spread < 0.06 and max(ph, pd, pa) < 0.42:
        if hdc >= adc and hdc >= hoa:
            return "home_or_draw", _PICK_LABELS["home_or_draw"], round(hdc * 100, 1)
        if adc >= hoa:
            return "away_or_draw", _PICK_LABELS["away_or_draw"], round(adc * 100, 1)
        return "avoid", _PICK_LABELS["avoid"], round(max(hdc, adc, hoa) * 100, 1)

    # Strong favourite → outright only if clear
    fav = max(("home", ph), ("draw", pd), ("away", pa), key=lambda x: x[1])
    if fav[1] >= 0.52 and spread >= margin:
        if fav[0] == "home":
            return "home_win", _PICK_LABELS["home_win"], round(ph * 100, 1)
        if fav[0] == "away":
            return "away_win", _PICK_LABELS["away_win"], round(pa * 100, 1)
        return "avoid", _PICK_LABELS["avoid"], round(pd * 100, 1)

    # Moderate favourite → prefer double chance
    if ph >= pa and hdc >= 0.58:
        return "home_or_draw", _PICK_LABELS["home_or_draw"], round(hdc * 100, 1)
    if pa > ph and adc >= 0.58:
        return "away_or_draw", _PICK_LABELS["away_or_draw"], round(adc * 100, 1)

    # Goals markets when 1X2 is muddy but totals signal is strong
    if over25 >= 0.58 and over25 > (1.0 - over25) + 0.12:
        return "over_25", _PICK_LABELS["over_25"], round(over25 * 100, 1)
    if over25 <= 0.42:
        return "under_25", _PICK_LABELS["under_25"], round((1.0 - over25) * 100, 1)
    if btts >= 0.58:
        return "btts_yes", _PICK_LABELS["btts_yes"], round(btts * 100, 1)
    if btts <= 0.40:
        return "btts_no", _PICK_LABELS["btts_no"], round((1.0 - btts) * 100, 1)

    if hoa >= 0.72:
        return "home_or_away", _PICK_LABELS["home_or_away"], round(hoa * 100, 1)

    return "avoid", _PICK_LABELS["avoid"], round(max(hdc, adc, hoa, ph, pa) * 100, 1)


def _implied_prob_pct(odds: Any) -> Optional[float]:
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if o <= 1.0:
        return None
    return round(100.0 / o, 1)


def _top_value_snapshot(prediction: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    vb = prediction.get("value_bets") or {}
    if not vb:
        return None
    key = prediction.get("best_bet")
    row = vb.get(key) if key and key in vb else None
    if row is None:
        key, row = max(
            vb.items(),
            key=lambda kv: float((kv[1] or {}).get("edge_pct") or 0),
        )
    if not row:
        return None
    return {
        "key": key,
        "market_label": row.get("market_label") or str(key).replace("_", " ").title(),
        "model_probability_pct": row.get("model_probability_pct"),
        "implied_probability_pct": row.get("implied_probability_pct"),
        "edge_pct": row.get("edge_pct"),
        "odds": row.get("odds"),
    }


def _build_rationale_metrics(
    fixture: Dict[str, Any],
    prediction: Dict[str, Any],
    pick_key: str,
    lam_h: float,
    lam_a: float,
    conf: float,
) -> List[Dict[str, Any]]:
    """Short labelled figures for rationale tiles (UI)."""
    core: List[Dict[str, Any]] = []
    optional: List[Dict[str, Any]] = []
    probs = prediction.get("probabilities_pct") or {}
    ph, pd, pa = probs.get("home"), probs.get("draw"), probs.get("away")
    if ph is not None and pd is not None and pa is not None:
        spread = max(ph, pd, pa) - sorted([ph, pd, pa])[1]
        fav = "home" if ph >= pd and ph >= pa else ("away" if pa >= ph and pa >= pd else "draw")
        core.append(
            {
                "label": "1X2 model",
                "value": f"H {ph}% · D {pd}% · A {pa}%",
                "note": f"Lean {fav} (+{spread:.0f} pts vs 2nd).",
            }
        )
    xg_total = lam_h + lam_a
    src = fixture.get("xg_source") or prediction.get("xg_source") or "source unknown"
    core.append(
        {
            "label": "xG / source",
            "value": f"{lam_h:.2f}–{lam_a:.2f} ({xg_total:.2f} total)",
            "note": str(src),
        }
    )
    btts_pct = prediction.get("btts_probability_pct")
    o25 = prediction.get("over25_probability_pct")
    o15 = prediction.get("over15_probability_pct")
    if btts_pct is not None or o25 is not None:
        parts = []
        if btts_pct is not None:
            parts.append(f"BTTS {btts_pct}%")
        if o25 is not None:
            parts.append(f"O2.5 {o25}%")
        if o15 is not None:
            parts.append(f"O1.5 {o15}%")
        note = "High-scoring lean." if (o25 or 0) >= 58 else (
            "Low-scoring lean." if (o25 or 100) <= 42 else "Balanced totals."
        )
        core.append({"label": "Goals signal", "value": " · ".join(parts), "note": note})
    val = _top_value_snapshot(prediction)
    if val and val.get("edge_pct") is not None:
        core.append(
            {
                "label": "Value edge",
                "value": f"+{val['edge_pct']}% {val.get('market_label', '')}".strip(),
                "note": (
                    f"Model {val.get('model_probability_pct')}% vs "
                    f"implied {val.get('implied_probability_pct')}%"
                    + (f" @ {val['odds']:.2f}" if val.get("odds") else "")
                    + "."
                ),
            }
        )
    bo = prediction.get("bookmaker_odds") or {}
    if bo.get("home") and not val:
        ih = _implied_prob_pct(bo.get("home"))
        id_ = _implied_prob_pct(bo.get("draw"))
        ia = _implied_prob_pct(bo.get("away"))
        if ih is not None and id_ is not None and ia is not None:
            optional.append(
                {
                    "label": "Book implied",
                    "value": f"H {ih}% · D {id_}% · A {ia}%",
                    "note": (
                        f"Prices {bo['home']:.2f} / {bo['draw']:.2f} / {bo['away']:.2f}."
                        if bo.get("draw")
                        else "From primary book line."
                    ),
                }
            )
    hp = fixture.get("home_position") or {}
    ap = fixture.get("away_position") or {}
    if hp.get("position") and ap.get("position"):
        optional.append(
            {
                "label": "Table",
                "value": f"{fixture.get('home', 'Home')} {hp['position']} · {fixture.get('away', 'Away')} {ap['position']}",
                "note": f"{hp.get('points', '—')} vs {ap.get('points', '—')} pts.",
            }
        )
    dq = fixture.get("data_quality") or prediction.get("data_quality") or {}
    dq_pct = dq.get("score_pct")
    if dq_pct is not None:
        optional.append(
            {
                "label": "Data coverage",
                "value": f"{dq_pct}% inputs",
                "note": (
                    "Full-scope — multi-market reads reliable."
                    if dq.get("full_scope")
                    else (
                        "Strong — verify thin blocks."
                        if dq.get("strong_scope")
                        else "Below 80% — treat value edges cautiously."
                    )
                ),
            }
        )
    pick_label = _PICK_LABELS.get(pick_key, pick_key)
    if pick_key not in ("avoid", "odds_only"):
        optional.append(
            {
                "label": "Structured pick",
                "value": f"{pick_label} @ {conf}%",
                "note": "Probability-first selection (not a stake tip).",
            }
        )
    th = prediction.get("team_strength_home")
    ta = prediction.get("team_strength_away")
    fh = prediction.get("form_home")
    fa = prediction.get("form_away")
    if th is not None and ta is not None:
        optional.append(
            {
                "label": "Strength / form",
                "value": f"Str {th}% / {ta}%",
                "note": (
                    f"Form {fh}% / {fa}%."
                    if fh is not None and fa is not None
                    else "Model strength index."
                ),
            }
        )
    return (core + optional)[:6]


def _build_rationale_summary(
    fixture: Dict[str, Any],
    prediction: Dict[str, Any],
    pick_key: str,
    pick_label: str,
    conf: float,
    lam_h: float,
    lam_a: float,
) -> str:
    """One short paragraph tying figures to the pick."""
    parts: List[str] = []
    probs = prediction.get("probabilities_pct") or {}
    ph, pd, pa = probs.get("home"), probs.get("draw"), probs.get("away")
    if ph is not None and pd is not None and pa is not None:
        fav = max([("home", ph), ("draw", pd), ("away", pa)], key=lambda x: x[1])
        parts.append(
            f"The model reads 1X2 as H {ph}% · D {pd}% · A {pa}% "
            f"(favourite {fav[0]} {fav[1]}%) with xG {lam_h:.2f}–{lam_a:.2f} "
            f"({lam_h + lam_a:.2f} goals expected)."
        )
    btts_pct = prediction.get("btts_probability_pct")
    o25 = prediction.get("over25_probability_pct")
    if btts_pct is not None and o25 is not None:
        parts.append(f"Goals markets: BTTS {btts_pct}%, over 2.5 {o25}%.")
    val = _top_value_snapshot(prediction)
    if val and val.get("edge_pct") is not None:
        parts.append(
            f"Largest priced edge is {val.get('market_label')}: "
            f"model {val.get('model_probability_pct')}% vs book implied "
            f"{val.get('implied_probability_pct')}% (+{val['edge_pct']}% edge)."
        )
    n_h = int(fixture.get("home_recent_n") or 0)
    n_a = int(fixture.get("away_recent_n") or 0)
    if n_h >= 3 or n_a >= 3:
        hb = float(fixture.get("home_btts_rate") or 0) * 100
        ab = float(fixture.get("away_btts_rate") or 0) * 100
        if hb or ab:
            parts.append(
                f"Recent samples (H {n_h} / A {n_a} games) show BTTS {hb:.0f}% / {ab:.0f}%."
            )
    if pick_key == "avoid":
        parts.append("No outcome clears the conservative bar — we label this AVOID.")
    else:
        parts.append(f"Structured pick: {pick_label} at {conf}% model confidence.")
    dq = fixture.get("data_quality") or prediction.get("data_quality") or {}
    if dq.get("score_pct") is not None:
        parts.append(f"Input coverage is {dq['score_pct']}%.")
    return " ".join(parts)


def _odds_only_metrics(fixture: Dict[str, Any], prediction: Dict[str, Any]) -> List[Dict[str, Any]]:
    metrics: List[Dict[str, Any]] = []
    bo = prediction.get("bookmaker_odds") or {}
    if bo.get("home") and bo.get("draw") and bo.get("away"):
        ih = _implied_prob_pct(bo["home"])
        id_ = _implied_prob_pct(bo["draw"])
        ia = _implied_prob_pct(bo["away"])
        metrics.append(
            {
                "label": "Book 1X2",
                "value": f"{bo['home']:.2f} / {bo['draw']:.2f} / {bo['away']:.2f}",
                "note": (
                    f"Implied H {ih}% · D {id_}% · A {ia}%."
                    if ih is not None
                    else "Model pick withheld."
                ),
            }
        )
    lo = prediction.get("line_odds") or {}
    side = []
    for k, label in (
        ("btts_yes", "BTTS Y"),
        ("over25", "O2.5"),
        ("under25", "U2.5"),
    ):
        if lo.get(k):
            side.append(f"{label} {lo[k]:.2f}")
    if side:
        metrics.append({"label": "Side markets", "value": ", ".join(side), "note": "Prices only — no model %."})
    dq = fixture.get("data_quality") or {}
    if dq.get("score_pct") is not None:
        metrics.append(
            {
                "label": "Data coverage",
                "value": f"{dq['score_pct']}% inputs",
                "note": "Below threshold for structured picks.",
            }
        )
    league = str(fixture.get("league") or "")
    if league:
        metrics.append({"label": "League mode", "value": "Odds only", "note": f"{league}: prices until coverage improves."})
    return metrics[:4]


def _odds_only_summary(fixture: Dict[str, Any], prediction: Dict[str, Any]) -> str:
    bo = prediction.get("bookmaker_odds") or {}
    parts: List[str] = []
    if bo.get("home") and bo.get("draw") and bo.get("away"):
        ih = _implied_prob_pct(bo["home"])
        id_ = _implied_prob_pct(bo["draw"])
        ia = _implied_prob_pct(bo["away"])
        parts.append(
            f"Book 1X2 is {bo['home']:.2f} / {bo['draw']:.2f} / {bo['away']:.2f}"
            + (
                f" (implied H {ih}% · D {id_}% · A {ia}%)."
                if ih is not None
                else "."
            )
        )
        parts.append("We show prices only — the model pick is withheld because data is thin or restricted.")
    lo = prediction.get("line_odds") or {}
    side = []
    for k, label in (("btts_yes", "BTTS Y"), ("over25", "O2.5"), ("under25", "U2.5")):
        if lo.get(k):
            side.append(f"{label} {lo[k]:.2f}")
    if side:
        parts.append("Side markets: " + ", ".join(side) + ".")
    dq = fixture.get("data_quality") or {}
    if dq.get("score_pct") is not None:
        parts.append(f"Input coverage {dq['score_pct']}% — below our minimum for structured picks.")
    return " ".join(parts)


def _rationale_bullets(
    fixture: Dict[str, Any],
    prediction: Dict[str, Any],
    pick_key: str,
    lam_h: float,
    lam_a: float,
    pick_label: str,
    conf: float,
) -> List[str]:
    """Numeric fact lines — mirror figures shown in rationale_metrics."""
    bullets: List[str] = []
    probs = prediction.get("probabilities_pct") or {}
    ph = probs.get("home")
    pd = probs.get("draw")
    pa = probs.get("away")
    if ph is not None and pd is not None and pa is not None:
        bullets.append(
            f"1X2 model: H {ph}% · D {pd}% · A {pa}% · xG {lam_h:.2f}–{lam_a:.2f}."
        )
    btts_pct = prediction.get("btts_probability_pct")
    o25 = prediction.get("over25_probability_pct")
    if btts_pct is not None and o25 is not None:
        bullets.append(f"Goals: BTTS {btts_pct}% · over 2.5 {o25}%.")
    val = _top_value_snapshot(prediction)
    if val and val.get("edge_pct") is not None:
        bullets.append(
            f"Value: {val.get('market_label')} — model {val.get('model_probability_pct')}% "
            f"vs implied {val.get('implied_probability_pct')}% (+{val['edge_pct']}% edge)."
        )
    n_h = int(fixture.get("home_recent_n") or 0)
    n_a = int(fixture.get("away_recent_n") or 0)
    if n_h >= 3 or n_a >= 3:
        hb = float(fixture.get("home_btts_rate") or 0) * 100
        ab = float(fixture.get("away_btts_rate") or 0) * 100
        if hb or ab:
            bullets.append(f"Form (last {n_h}/{n_a}): BTTS {hb:.0f}% / {ab:.0f}%.")
    hp = fixture.get("home_position") or {}
    ap = fixture.get("away_position") or {}
    if hp.get("position") and ap.get("position"):
        bullets.append(
            f"Table: {fixture.get('home', 'Home')} {hp.get('position')} · "
            f"{fixture.get('away', 'Away')} {ap.get('position')}."
        )
    dq = fixture.get("data_quality") or prediction.get("data_quality") or {}
    if dq.get("score_pct") is not None:
        bullets.append(f"Data coverage {dq.get('score_pct')}% — size stakes conservatively.")
    if pick_key == "avoid":
        bullets.append("AVOID: no outcome clears the conservative risk bar.")
    elif pick_key != "odds_only":
        bullets.append(f"Pick: {pick_label} @ {conf}% model confidence.")
    return bullets[:4]


def _odds_only_bullets(fixture: Dict[str, Any], prediction: Dict[str, Any]) -> List[str]:
    bo = prediction.get("bookmaker_odds") or {}
    lines: List[str] = []
    if bo.get("home") and bo.get("draw") and bo.get("away"):
        ih = _implied_prob_pct(bo["home"])
        id_ = _implied_prob_pct(bo["draw"])
        ia = _implied_prob_pct(bo["away"])
        lines.append(
            f"Book 1X2: {bo['home']:.2f} / {bo['draw']:.2f} / {bo['away']:.2f}"
            + (
                f" (implied H {ih}% · D {id_}% · A {ia}%)."
                if ih is not None
                else "."
            )
        )
    lo = prediction.get("line_odds") or {}
    parts = []
    for k, label in (
        ("btts_yes", "BTTS Y"),
        ("over25", "O2.5"),
        ("under25", "U2.5"),
    ):
        if lo.get(k):
            parts.append(f"{label} {lo[k]:.2f}")
    if parts:
        lines.append("Side markets: " + ", ".join(parts) + ".")
    dq = fixture.get("data_quality") or {}
    if dq.get("score_pct") is not None:
        lines.append(f"Data coverage {dq.get('score_pct')}% — below threshold for structured picks.")
    lines.append("No model pick — prices only until coverage improves.")
    return lines[:4]


def build_structured_insight(
    fixture: Dict[str, Any],
    prediction: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Professional structured card for UI / API.
    """
    home = prediction.get("home") or fixture.get("home") or "Home"
    away = prediction.get("away") or fixture.get("away") or "Away"
    match_line = f"{home} vs {away}"

    if should_use_odds_only(fixture, prediction):
        return {
            "match": match_line,
            "pick": _PICK_LABELS["odds_only"],
            "pick_key": "odds_only",
            "rationale": _odds_only_bullets(fixture, prediction),
            "rationale_metrics": _odds_only_metrics(fixture, prediction),
            "rationale_summary": _odds_only_summary(fixture, prediction),
            "confidence_pct": None,
            "predicted_scoreline": None,
            "mode": "odds_only",
            "disclaimer": "Prices from book feeds; not a model recommendation.",
        }

    lam_h = float(prediction.get("expected_goals_home") or prediction.get("lambda_side_home") or 1.2)
    lam_a = float(prediction.get("expected_goals_away") or prediction.get("lambda_side_away") or 1.1)
    probs = prediction.get("probabilities") or {}
    btts = float(prediction.get("btts_probability") or 0.5)
    over25 = float(prediction.get("over25_probability_pct") or 50) / 100.0
    if not probs:
        return {
            "match": match_line,
            "pick": _PICK_LABELS["avoid"],
            "pick_key": "avoid",
            "rationale": ["Model probabilities unavailable; treat as pass."],
            "confidence_pct": None,
            "predicted_scoreline": None,
            "mode": "avoid",
            "disclaimer": None,
        }

    margin = _env_float("HIBS_INSIGHT_PICK_MARGIN", 0.08)
    pick_key, pick_label, conf = _pick_conservative(probs, btts, over25, lam_h, lam_a, margin)
    rationale = _rationale_bullets(
        fixture, prediction, pick_key, lam_h, lam_a, pick_label, conf
    )
    scoreline = _most_likely_scoreline(lam_h, lam_a)

    return {
        "match": match_line,
        "pick": pick_label,
        "pick_key": pick_key,
        "rationale": rationale,
        "rationale_metrics": _build_rationale_metrics(
            fixture, prediction, pick_key, lam_h, lam_a, conf
        ),
        "rationale_summary": _build_rationale_summary(
            fixture, prediction, pick_key, pick_label, conf, lam_h, lam_a
        ),
        "confidence_pct": conf,
        "predicted_scoreline": scoreline,
        "mode": "prediction",
        "disclaimer": "Conservative, data-backed view — not financial advice. Gamble responsibly 18+.",
    }


def build_pick_menu(fixture: Dict[str, Any], prediction: Dict[str, Any]) -> List[Dict[str, Any]]:
    """All modelled markets for per-fixture dropdown (model %, book price, value flag)."""
    si = prediction.get("structured_insight") or build_structured_insight(fixture, prediction)
    rec_key = si.get("pick_key") or "avoid"
    probs = prediction.get("probabilities_pct") or {}
    ph = float(probs.get("home") or 0)
    pd = float(probs.get("draw") or 0)
    pa = float(probs.get("away") or 0)
    book = prediction.get("bookmaker_odds") or {}
    lo = prediction.get("line_odds") or {}
    vb = prediction.get("value_bets") or {}

    def _item(
        key: str,
        label: str,
        model_pct: Optional[float],
        odds: Optional[float] = None,
    ) -> Dict[str, Any]:
        vb_key = _value_bet_key(key)
        row: Dict[str, Any] = {
            "key": key,
            "label": label,
            "model_pct": round(model_pct, 1) if model_pct is not None else None,
            "odds": round(float(odds), 2) if odds is not None and float(odds) > 1.0 else None,
            "recommended": key == rec_key,
            "is_value": vb_key in vb,
        }
        if vb_key in vb:
            row["edge_pct"] = vb[vb_key].get("edge_pct")
            row["roi_pct"] = vb[vb_key].get("roi_percent")
        return row

    menu: List[Dict[str, Any]] = []
    if si.get("mode") == "odds_only":
        if book.get("home"):
            menu.append(_item("home", "Home (book)", None, book.get("home")))
            menu.append(_item("draw", "Draw (book)", None, book.get("draw")))
            menu.append(_item("away", "Away (book)", None, book.get("away")))
        for lk, lbl in (
            ("btts_yes", "BTTS Yes"),
            ("btts_no", "BTTS No"),
            ("over25", "Over 2.5"),
            ("under25", "Under 2.5"),
        ):
            if lo.get(lk):
                menu.append(_item(lk, f"{lbl} (book)", None, lo.get(lk)))
        return menu

    menu.append(_item("home_win", "Home Win", ph, book.get("home")))
    menu.append(_item("draw", "Draw", pd, book.get("draw")))
    menu.append(_item("away_win", "Away Win", pa, book.get("away")))
    menu.append(_item("home_or_draw", "Home or Draw", ph + pd, lo.get("home_or_draw")))
    menu.append(_item("away_or_draw", "Away or Draw", pa + pd, lo.get("away_or_draw")))
    menu.append(_item("home_or_away", "Home or Away", ph + pa, lo.get("home_or_away")))
    btts = prediction.get("btts_probability_pct")
    if btts is not None:
        menu.append(_item("btts_yes", "BTTS Yes", float(btts), lo.get("btts_yes")))
        menu.append(_item("btts_no", "BTTS No", 100.0 - float(btts), lo.get("btts_no")))
    o25 = prediction.get("over25_probability_pct")
    if o25 is not None:
        menu.append(_item("over_25", "Over 2.5", float(o25), lo.get("over25")))
        menu.append(_item("under_25", "Under 2.5", 100.0 - float(o25), lo.get("under25")))
    o15 = prediction.get("over15_probability_pct")
    if o15 is not None:
        menu.append(_item("over_15", "Over 1.5", float(o15), lo.get("over15")))
        menu.append(_item("under_15", "Under 1.5", 100.0 - float(o15), lo.get("under15")))
    o35 = prediction.get("over35_probability_pct")
    if o35 is not None:
        menu.append(_item("over_35", "Over 3.5", float(o35), lo.get("over35")))
        menu.append(_item("under_35", "Under 3.5", 100.0 - float(o35), lo.get("under35")))
    sab = prediction.get("score_and_btts_pct") or {}
    if sab.get("home_win_and_btts"):
        menu.append(_item("home_and_btts", "Home Win & BTTS", float(sab["home_win_and_btts"]), None))
    if sab.get("draw_and_btts"):
        menu.append(_item("draw_and_btts", "Draw & BTTS", float(sab["draw_and_btts"]), None))
    if sab.get("away_win_and_btts"):
        menu.append(_item("away_and_btts", "Away Win & BTTS", float(sab["away_win_and_btts"]), None))
    if rec_key == "avoid":
        for it in menu:
            it["recommended"] = False
        menu.insert(0, _item("avoid", "AVOID", None, None))
        menu[0]["recommended"] = True
    return menu


def build_probability_scores(prediction: Dict[str, Any]) -> Dict[str, Any]:
    """Win / score / goals profile for UI."""
    probs = prediction.get("probabilities_pct") or {}
    return {
        "home_win_pct": probs.get("home"),
        "draw_pct": probs.get("draw"),
        "away_win_pct": probs.get("away"),
        "btts_pct": prediction.get("btts_probability_pct"),
        "over15_pct": prediction.get("over15_probability_pct"),
        "over25_pct": prediction.get("over25_probability_pct"),
        "over35_pct": prediction.get("over35_probability_pct"),
        "confidence_pct": prediction.get("confidence_pct"),
        "xg_home": prediction.get("expected_goals_home"),
        "xg_away": prediction.get("expected_goals_away"),
    }


def _compact_result_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in (rows or [])[:10]:
        out.append(
            {
                "result": r.get("result"),
                "score": r.get("score"),
                "opponent": r.get("opponent"),
                "home_away": r.get("home_away"),
                "date": r.get("date"),
                "gf": r.get("gf"),
                "ga": r.get("ga"),
                "xg_for": r.get("xg_for"),
            }
        )
    return out


def _form_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary = {"played": 0, "wins": 0, "draws": 0, "losses": 0, "gf": 0, "ga": 0, "btts": 0, "over25": 0}
    for r in rows or []:
        summary["played"] += 1
        res = str(r.get("result") or "").upper()
        if res == "W":
            summary["wins"] += 1
        elif res == "D":
            summary["draws"] += 1
        elif res == "L":
            summary["losses"] += 1
        try:
            gf = int(r.get("gf") if r.get("gf") is not None else str(r.get("score") or "0-0").split("-")[0])
            ga = int(r.get("ga") if r.get("ga") is not None else str(r.get("score") or "0-0").split("-")[1])
        except Exception:
            gf = ga = 0
        summary["gf"] += gf
        summary["ga"] += ga
        if gf > 0 and ga > 0:
            summary["btts"] += 1
        if gf + ga > 2:
            summary["over25"] += 1
    return summary


def build_assistant_packet(fixture_row: Dict[str, Any]) -> Dict[str, Any]:
    """Single fixture payload for Betting Assistant + API."""
    p = fixture_row.get("prediction") or {}
    fix = {
        "league": fixture_row.get("league"),
        "home": fixture_row.get("home"),
        "away": fixture_row.get("away"),
        "home_recent_n": len(fixture_row.get("home_last10") or []),
        "away_recent_n": len(fixture_row.get("away_last10") or []),
        "data_quality": fixture_row.get("data_quality"),
        "home_btts_rate": p.get("home_btts_rate"),
        "away_btts_rate": p.get("away_btts_rate"),
        "home_position": fixture_row.get("home_position"),
        "away_position": fixture_row.get("away_position"),
    }
    return {
        "id": fixture_row.get("id"),
        "home": fixture_row.get("home"),
        "away": fixture_row.get("away"),
        "date": fixture_row.get("date"),
        "kickoff_time": fixture_row.get("kickoff_time"),
        "league": fixture_row.get("league"),
        "league_name": fixture_row.get("league_name"),
        "home_recent_n": len(fixture_row.get("home_last10") or []),
        "away_recent_n": len(fixture_row.get("away_last10") or []),
        "home_form": _compact_result_rows(fixture_row.get("home_last10") or []),
        "away_form": _compact_result_rows(fixture_row.get("away_last10") or []),
        "home_form_summary": _form_summary(fixture_row.get("home_last10") or []),
        "away_form_summary": _form_summary(fixture_row.get("away_last10") or []),
        "home_position": fixture_row.get("home_position") or {},
        "away_position": fixture_row.get("away_position") or {},
        "fixture_injuries": fixture_row.get("fixture_injuries") or [],
        "xg_source": fixture_row.get("xg_source"),
        "structured_insight": p.get("structured_insight"),
        "pick_menu": p.get("pick_menu"),
        "probability_scores": p.get("probability_scores"),
        "prediction_quality_hint": p.get("prediction_quality_hint") or {},
        "league_model_profile": p.get("league_model_profile") or {},
        "matchup_calibration": p.get("matchup_calibration"),
        "value_bets_rejected": p.get("value_bets_rejected") or {},
        "value_bets_display": p.get("value_bets_display") or [],
        "has_value_bet": fixture_row.get("has_value_bet"),
        "prediction_unavailable": bool(p.get("prediction_unavailable")),
        "data_quality_pct": (fixture_row.get("data_quality") or {}).get("score_pct"),
        "field_scores": (fixture_row.get("data_quality") or {}).get("field_scores") or {},
        "weak_fields": (fixture_row.get("data_quality") or {}).get("weak_fields") or [],
        "trust_label": (fixture_row.get("data_quality") or {}).get("trust_label"),
    }


def attach_structured_insight(fixture: Dict[str, Any], prediction: Dict[str, Any]) -> Dict[str, Any]:
    """Mutate prediction dict with structured_insight, pick_menu, probability_scores."""
    prediction["structured_insight"] = build_structured_insight(fixture, prediction)
    prediction["pick_menu"] = build_pick_menu(fixture, prediction)
    prediction["probability_scores"] = build_probability_scores(prediction)
    return prediction
