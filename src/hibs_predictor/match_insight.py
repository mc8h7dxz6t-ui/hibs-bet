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


def _poisson_pmf(lam: float, k: int) -> float:
    import math

    lam = max(0.08, float(lam))
    try:
        return math.exp(-lam) * (lam**k) / math.factorial(k)
    except (OverflowError, ValueError):
        return 0.0


def _most_likely_scoreline(lam_h: float, lam_a: float, *, max_goals: int = 6) -> str:
    """Poisson joint argmax on calibrated side lambdas (same grid as betting_engine totals)."""
    top = poisson_top_scorelines(lam_h, lam_a, top_n=1, max_goals=max_goals)
    return top[0]["score"] if top else "0-0"


def poisson_top_scorelines(
    lam_h: float,
    lam_a: float,
    *,
    top_n: int = 3,
    max_goals: int = 6,
) -> List[Dict[str, Any]]:
    """Top-N joint Poisson scorelines with percentage mass (same grid as betting_engine)."""
    cap = max(3, min(8, int(max_goals)))
    scored: List[Dict[str, Any]] = []
    for h in range(cap + 1):
        for a in range(cap + 1):
            p = _poisson_pmf(lam_h, h) * _poisson_pmf(lam_a, a)
            scored.append({"score": f"{h}-{a}", "pct": round(p * 100.0, 1)})
    scored.sort(key=lambda row: (-float(row["pct"]), row["score"]))
    n = max(1, min(int(top_n), len(scored)))
    return scored[:n]


def _calibrated_lambdas_for_scoreline(prediction: Dict[str, Any]) -> Tuple[float, float]:
    """Prefer HA+Elo side lambdas; fall back to raw expected goals."""
    lam_h = prediction.get("lambda_side_home")
    lam_a = prediction.get("lambda_side_away")
    try:
        if lam_h is not None and lam_a is not None:
            return max(0.08, float(lam_h)), max(0.08, float(lam_a))
    except (TypeError, ValueError):
        pass
    return (
        max(0.08, float(prediction.get("expected_goals_home") or 1.2)),
        max(0.08, float(prediction.get("expected_goals_away") or 1.1)),
    )


def _norm_team_key(name: Any) -> str:
    import re
    import unicodedata

    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    for suffix in (" fc", " afc", " cf", " sc", " united", " city"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    return text


def derive_motivation_context(
    fixture: Dict[str, Any],
    *,
    table_rows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Deterministic end-of-season motivation from table position + points gap.
    No invented stats — requires standings rows with position, points, played.
    """
    rows = table_rows or fixture.get("league_table_rows") or []
    if len(rows) < 4:
        return {"home": [], "away": [], "labels": []}

    def _leader_points(rs: List[Dict[str, Any]]) -> Optional[int]:
        top = min((int(r.get("position") or 999) for r in rs), default=999)
        for r in rs:
            if int(r.get("position") or 999) == top:
                try:
                    return int(r.get("points") or 0)
                except (TypeError, ValueError):
                    return None
        return None

    def _team_row(team: str) -> Optional[Dict[str, Any]]:
        key = _norm_team_key(team)
        for r in rows:
            if _norm_team_key(r.get("team")) == key:
                return r
        return None

    def _flags(side: str, pos: Dict[str, Any]) -> List[str]:
        flags: List[str] = []
        try:
            rank = int(pos.get("position") or 0)
            pts = int(pos.get("points") or 0)
            played = int(pos.get("played") or 0)
        except (TypeError, ValueError):
            return flags
        if rank < 1 or played < 1:
            return flags
        n_teams = len(rows)
        leader_pts = _leader_points(rows)
        max_played = max(int(r.get("played") or 0) for r in rows) or played
        remaining = max(0, max_played - played)
        if leader_pts is not None and rank == 1 and remaining <= 3:
            gap = pts - max(
                (int(r.get("points") or 0) for r in rows if int(r.get("position") or 999) > 1),
                default=0,
            )
            if gap >= 6:
                flags.append("title_won")
        if leader_pts is not None and remaining <= 2:
            if pts <= leader_pts - 15 and rank > 1:
                flags.append("nothing_to_play_for")
            elif rank >= n_teams - 1 and pts <= leader_pts - 12:
                flags.append("relegation_done")
        if remaining <= 4 and rank <= 2 and leader_pts is not None and pts >= leader_pts - 3:
            flags.append("title_race")
        if remaining <= 4 and rank >= n_teams - 2:
            flags.append("relegation_battle")
        return flags

    home = fixture.get("home") or "Home"
    away = fixture.get("away") or "Away"
    hp = fixture.get("home_position") or {}
    ap = fixture.get("away_position") or {}
    hr = _team_row(str(home)) or hp
    ar = _team_row(str(away)) or ap
    home_flags = _flags("home", hr if isinstance(hr, dict) else {})
    away_flags = _flags("away", ar if isinstance(ar, dict) else {})
    label_map = {
        "title_won": "already won league",
        "nothing_to_play_for": "little left to play for",
        "relegation_done": "relegation settled",
        "title_race": "title race",
        "relegation_battle": "relegation battle",
    }
    labels: List[str] = []
    for team, flags in ((home, home_flags), (away, away_flags)):
        for f in flags:
            labels.append(f"{team}: {label_map.get(f, f)}")
    return {"home": home_flags, "away": away_flags, "labels": labels}


def _motivation_lambda_nudge(flags: List[str]) -> float:
    """Tiny λ multiplier from motivation (engine + scoreline; max ±6%)."""
    nudge = 1.0
    if "title_won" in flags or "nothing_to_play_for" in flags or "relegation_done" in flags:
        nudge *= 0.97
    if "title_race" in flags or "relegation_battle" in flags:
        nudge *= 1.02
    return max(0.94, min(1.06, nudge))


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
    from hibs_predictor.fixture_utils import fixture_team_name, position_points, position_rank

    hp_rank = position_rank(hp)
    ap_rank = position_rank(ap)
    if hp_rank and ap_rank:
        optional.append(
            {
                "label": "Table",
                "value": f"{fixture_team_name(fixture, 'home') or 'Home'} {hp_rank} · {fixture_team_name(fixture, 'away') or 'Away'} {ap_rank}",
                "note": f"{position_points(hp) or '—'} vs {position_points(ap) or '—'} pts.",
            }
        )
    inj_n = len(fixture.get("fixture_injuries") or [])
    if inj_n:
        optional.append(
            {
                "label": "Injuries",
                "value": f"{inj_n} listed",
                "note": "API absence feed — may affect squad strength.",
            }
        )
    mot = derive_motivation_context(fixture)
    if mot.get("labels"):
        optional.append(
            {
                "label": "Motivation",
                "value": "; ".join(mot["labels"][:2]),
                "note": "From table position + games remaining (deterministic).",
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
    venue_metric = _venue_form_metric_line(fixture, prediction)
    if venue_metric:
        optional.append(venue_metric)
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


def _injury_rationale_line(fixture: Dict[str, Any]) -> Optional[str]:
    """One-line squad availability when injury feed + availability scores exist."""
    meta = fixture.get("team_news_meta") or {}
    h_n = int(meta.get("home_absences") or 0)
    a_n = int(meta.get("away_absences") or 0)
    if h_n == 0 and a_n == 0:
        return None
    h_av = fixture.get("attack_availability_home")
    a_av = fixture.get("attack_availability_away")
    if h_av is None and a_av is None:
        return None
    parts = []
    if h_n:
        parts.append(f"home {h_n} out ({int(float(h_av or 1) * 100)}% attack avail)")
    if a_n:
        parts.append(f"away {a_n} out ({int(float(a_av or 1) * 100)}% attack avail)")
    return "Squad news: " + ", ".join(parts) + "."


def build_player_insight_block(fixture: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Top league scorers per side for structured_insight (display only)."""
    home = fixture.get("home_top_scorers") or []
    away = fixture.get("away_top_scorers") or []
    if not home and not away:
        return None
    meta = fixture.get("team_news_meta") or {}
    out: Dict[str, Any] = {
        "home": home[:3],
        "away": away[:3],
        "source": "api_sports_topscorers",
    }
    home_abs = meta.get("home_scorers_absent") or []
    away_abs = meta.get("away_scorers_absent") or []
    if home_abs:
        out["home_scorers_absent"] = home_abs
    if away_abs:
        out["away_scorers_absent"] = away_abs
    lineup_meta = fixture.get("lineup_meta") or {}
    home_out = lineup_meta.get("home_scorers_out_of_xi") or []
    away_out = lineup_meta.get("away_scorers_out_of_xi") or []
    if home_out:
        out["home_scorers_out_of_xi"] = home_out
    if away_out:
        out["away_scorers_out_of_xi"] = away_out
    if fixture.get("lineup_confirmed"):
        out["lineup_confirmed"] = True
        fl = fixture.get("fixture_lineups") or {}
        if fl.get("home"):
            out["home_formation"] = (fl["home"] or {}).get("formation")
        if fl.get("away"):
            out["away_formation"] = (fl["away"] or {}).get("formation")
    return out


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
    venue_metric = _venue_form_metric_line(fixture, prediction)
    if venue_metric:
        bullets.append(f"{venue_metric['label']}: {venue_metric['value']}.")
    inj_line = _injury_rationale_line(fixture)
    if inj_line:
        bullets.append(inj_line)
    pi = build_player_insight_block(fixture)
    if pi:
        for side_key, label in (("home_scorers_absent", fixture.get("home", "Home")), ("away_scorers_absent", fixture.get("away", "Away"))):
            for row in pi.get(side_key) or []:
                name = row.get("name") or "?"
                goals = row.get("goals")
                g_txt = f" ({goals}g)" if goals is not None else ""
                bullets.append(f"Top scorer {name}{g_txt} on API absence feed ({label}).")
        for side_key, label in (
            ("home_scorers_out_of_xi", fixture.get("home", "Home")),
            ("away_scorers_out_of_xi", fixture.get("away", "Away")),
        ):
            for row in pi.get(side_key) or []:
                name = row.get("name") or "?"
                goals = row.get("goals")
                g_txt = f" ({goals}g)" if goals is not None else ""
                inj = " · also on injury feed" if row.get("on_injury_feed") else ""
                bullets.append(f"Top scorer {name}{g_txt} not in confirmed XI ({label}){inj}.")
    if not fixture.get("lineup_confirmed"):
        from hibs_predictor.lineup_enrich import lineup_confidence_multiplier, minutes_to_kickoff

        mins = minutes_to_kickoff(fixture)
        if mins is not None and 0 <= mins <= 120:
            bullets.append("Starting XIs not confirmed yet — treat model confidence cautiously near kickoff.")
    hp = fixture.get("home_position") or {}
    ap = fixture.get("away_position") or {}
    from hibs_predictor.fixture_utils import fixture_team_name, position_rank

    hp_rank = position_rank(hp)
    ap_rank = position_rank(ap)
    if hp_rank and ap_rank:
        bullets.append(
            f"Table: {fixture_team_name(fixture, 'home') or 'Home'} {hp_rank} · "
            f"{fixture_team_name(fixture, 'away') or 'Away'} {ap_rank}."
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

    lam_h, lam_a = _calibrated_lambdas_for_scoreline(prediction)
    motivation = derive_motivation_context(fixture)
    lam_h *= _motivation_lambda_nudge(motivation.get("home") or [])
    lam_a *= _motivation_lambda_nudge(motivation.get("away") or [])
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
    from hibs_predictor.lineup_enrich import lineup_confidence_multiplier

    conf = round(conf * lineup_confidence_multiplier(fixture), 1)
    rationale = _rationale_bullets(
        fixture, prediction, pick_key, lam_h, lam_a, pick_label, conf
    )
    scoreline = _most_likely_scoreline(lam_h, lam_a)
    venue_form = build_venue_form_block(fixture, prediction)
    player_insight = build_player_insight_block(fixture)

    out: Dict[str, Any] = {
        "match": match_line,
        "pick": pick_label,
        "pick_key": pick_key,
        "venue_form": venue_form,
        "rationale": rationale,
        "rationale_metrics": _build_rationale_metrics(
            fixture, prediction, pick_key, lam_h, lam_a, conf
        ),
        "rationale_summary": _build_rationale_summary(
            fixture, prediction, pick_key, pick_label, conf, lam_h, lam_a
        ),
        "confidence_pct": conf,
        "predicted_scoreline": scoreline,
        "scoreline_note": (
            f"Poisson argmax on calibrated λ {lam_h:.2f}–{lam_a:.2f} "
            f"(xG source: {fixture.get('xg_source') or 'unknown'})."
        ),
        "motivation_context": motivation,
        "mode": "prediction",
        "disclaimer": "Conservative, data-backed view — not financial advice. Gamble responsibly 18+.",
    }
    if motivation.get("labels"):
        out["motivation_labels"] = motivation["labels"]
    if player_insight:
        out["player_insight"] = player_insight
    return out


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
    menu.sort(
        key=lambda it: (
            0 if it.get("recommended") else 1,
            -(float(it.get("model_pct") or 0)),
            str(it.get("label") or ""),
        )
    )
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


def _wdl_counts(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"wins": 0, "draws": 0, "losses": 0}
    for r in rows or []:
        res = str(r.get("result") or "").upper()
        if res == "W":
            counts["wins"] += 1
        elif res == "D":
            counts["draws"] += 1
        elif res == "L":
            counts["losses"] += 1
    return counts


def build_venue_form_block(
    fixture: Dict[str, Any],
    prediction: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Venue-specific form already used in team strength (home_home_factor / away_away_factor)."""
    pred = prediction or {}
    home_factor = fixture.get("home_home_factor")
    away_factor = fixture.get("away_away_factor")
    if home_factor is None and away_factor is None:
        return None
    home_rows = [
        r
        for r in fixture.get("home_last10") or []
        if str(r.get("home_away") or "").upper() == "H"
    ]
    away_rows = [
        r
        for r in fixture.get("away_last10") or []
        if str(r.get("home_away") or "").upper() == "A"
    ]
    block: Dict[str, Any] = {}
    if home_factor is not None:
        hc = _wdl_counts(home_rows)
        block["home_at_home"] = {
            "factor": round(float(home_factor), 3),
            "n": len(home_rows),
            "wdl": _wdl_string(home_rows),
            **hc,
            "form_pct": pred.get("form_home"),
        }
    if away_factor is not None:
        ac = _wdl_counts(away_rows)
        block["away_on_road"] = {
            "factor": round(float(away_factor), 3),
            "n": len(away_rows),
            "wdl": _wdl_string(away_rows),
            **ac,
            "form_pct": pred.get("form_away"),
        }
    return block or None


def _venue_form_metric_line(fixture: Dict[str, Any], prediction: Dict[str, Any]) -> Optional[Dict[str, str]]:
    vf = build_venue_form_block(fixture, prediction)
    if not vf:
        return None
    parts: List[str] = []
    notes: List[str] = []
    h = vf.get("home_at_home") or {}
    a = vf.get("away_on_road") or {}
    if h.get("n"):
        parts.append(f"H@H {h.get('wdl') or '—'} (n={h['n']})")
        if h.get("factor") is not None:
            notes.append(f"home factor {h['factor']}")
    if a.get("n"):
        parts.append(f"A@A {a.get('wdl') or '—'} (n={a['n']})")
        if a.get("factor") is not None:
            notes.append(f"away factor {a['factor']}")
    fh = prediction.get("form_home")
    fa = prediction.get("form_away")
    if fh is not None and fa is not None:
        notes.append(f"overall form {fh}% / {fa}%")
    if not parts:
        return None
    return {
        "label": "Venue form",
        "value": " · ".join(parts),
        "note": "; ".join(notes) + "." if notes else "Home/away splits from last 10.",
    }


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


def _wdl_string(rows: List[Dict[str, Any]]) -> str:
    letters: List[str] = []
    for r in rows or []:
        res = str(r.get("result") or "").upper()
        if res in ("W", "D", "L"):
            letters.append(res)
        if len(letters) >= 10:
            break
    return "".join(letters)


def _competition_display(fixture_row: Dict[str, Any]) -> str:
    title = fixture_row.get("league_name") or fixture_row.get("league") or ""
    meta = fixture_row.get("competition_meta") if isinstance(fixture_row.get("competition_meta"), dict) else {}
    rnd = meta.get("api_round") or meta.get("round")
    if rnd and title:
        return f"{title} · {rnd}"
    return str(title) if title else str(fixture_row.get("league") or "")


def _supplemental_tags(sup: Any) -> List[str]:
    if not isinstance(sup, dict):
        return []
    tags: List[str] = []
    for key, label in (
        ("understat", "understat"),
        ("understat_light", "understat"),
        ("soccerstats_positions", "soccerstats"),
        ("fbref_schedule", "fbref"),
        ("fbref_home_squad", "fbref"),
        ("statsbomb_open_team_proxy", "statsbomb"),
        ("sofascore_xg", "sofascore"),
    ):
        if sup.get(key):
            tags.append(label)
    return sorted(set(tags))


def _packet_has_value_dual_agree(value_bets_display: List[Any], value_bets: Any = None) -> bool:
    for v in value_bets_display or []:
        if isinstance(v, dict) and v.get("value_dual_agree"):
            return True
    if isinstance(value_bets, dict):
        for row in value_bets.values():
            if isinstance(row, dict) and row.get("value_dual_agree"):
                return True
    return False


def build_assistant_packet(fixture_row: Dict[str, Any]) -> Dict[str, Any]:
    """Single fixture payload for Betting Assistant + API."""
    p = fixture_row.get("prediction") or {}
    ps = p.get("probability_scores") or {}
    dq = fixture_row.get("data_quality") or {}
    home_last10 = fixture_row.get("home_last10") or []
    away_last10 = fixture_row.get("away_last10") or []
    value_bets_display = p.get("value_bets_display") or []
    value_bets = p.get("value_bets") or {}
    hist = p.get("historic_calibration") if isinstance(p.get("historic_calibration"), dict) else {}
    shrink = hist.get("calibration_shrink") if isinstance(hist.get("calibration_shrink"), dict) else None
    return {
        "id": fixture_row.get("id"),
        "home": fixture_row.get("home"),
        "away": fixture_row.get("away"),
        "date": fixture_row.get("date"),
        "kickoff_time": fixture_row.get("kickoff_time"),
        "league": fixture_row.get("league"),
        "league_name": fixture_row.get("league_name"),
        "competition_display": _competition_display(fixture_row),
        "competition_meta": fixture_row.get("competition_meta") or {},
        "home_recent_n": len(home_last10),
        "away_recent_n": len(away_last10),
        "home_last10_wdl": _wdl_string(home_last10),
        "away_last10_wdl": _wdl_string(away_last10),
        "home_form": _compact_result_rows(home_last10),
        "away_form": _compact_result_rows(away_last10),
        "home_form_summary": _form_summary(home_last10),
        "away_form_summary": _form_summary(away_last10),
        "home_position": fixture_row.get("home_position") or {},
        "away_position": fixture_row.get("away_position") or {},
        "fixture_injuries": fixture_row.get("fixture_injuries") or [],
        "attack_availability_home": fixture_row.get("attack_availability_home"),
        "attack_availability_away": fixture_row.get("attack_availability_away"),
        "team_news_meta": fixture_row.get("team_news_meta") or {},
        "home_top_scorers": fixture_row.get("home_top_scorers") or [],
        "away_top_scorers": fixture_row.get("away_top_scorers") or [],
        "lineup_confirmed": bool(fixture_row.get("lineup_confirmed")),
        "fixture_lineups": fixture_row.get("fixture_lineups"),
        "lineup_meta": fixture_row.get("lineup_meta") or {},
        "xg_source": fixture_row.get("xg_source"),
        "structured_insight": p.get("structured_insight"),
        "pick_menu": p.get("pick_menu"),
        "probability_scores": ps,
        "prediction_quality_hint": p.get("prediction_quality_hint") or {},
        "league_model_profile": p.get("league_model_profile") or {},
        "matchup_calibration": p.get("matchup_calibration"),
        "historic_calibration": hist or None,
        "calibration_shrink": shrink,
        "value_bets": value_bets,
        "value_bets_alt": p.get("value_bets_alt") or {},
        "value_bets_rejected": p.get("value_bets_rejected") or {},
        "value_bets_display": value_bets_display,
        "has_value_bet": fixture_row.get("has_value_bet"),
        "has_value_dual_agree": _packet_has_value_dual_agree(value_bets_display, value_bets),
        "line_odds": p.get("line_odds") or {},
        "bookmaker_odds": p.get("bookmaker_odds") or {},
        "best_odds_1x2": fixture_row.get("best_odds_1x2") or {},
        "sharp_anchor_implied": fixture_row.get("sharp_anchor_implied") or {},
        "bet_confidence": p.get("bet_confidence"),
        "bet_confidence_min_value": p.get("bet_confidence_min_value"),
        "prediction_unavailable": bool(p.get("prediction_unavailable")),
        "data_quality": dq,
        "data_quality_pct": dq.get("score_pct"),
        "field_scores": dq.get("field_scores") or {},
        "weak_fields": dq.get("weak_fields") or [],
        "trust_label": dq.get("trust_label"),
        "supplemental": fixture_row.get("supplemental") or {},
        "supplemental_tags": _supplemental_tags(fixture_row.get("supplemental")),
        "is_live": bool(fixture_row.get("is_live")),
        "live_score": fixture_row.get("live_score"),
        "live_status": fixture_row.get("live_status"),
        "live_minute": fixture_row.get("live_minute"),
        "live_status_long": fixture_row.get("live_status_long"),
        "live_xg_home": fixture_row.get("live_xg_home"),
        "live_xg_away": fixture_row.get("live_xg_away"),
        "live_stats": fixture_row.get("live_stats"),
        "live_last_event": fixture_row.get("live_last_event"),
    }


def attach_structured_insight(fixture: Dict[str, Any], prediction: Dict[str, Any]) -> Dict[str, Any]:
    """Mutate prediction dict with structured_insight, pick_menu, probability_scores."""
    prediction["structured_insight"] = build_structured_insight(fixture, prediction)
    prediction["pick_menu"] = build_pick_menu(fixture, prediction)
    prediction["probability_scores"] = build_probability_scores(prediction)
    return prediction
