"""Per-fixture data coverage score (0–100) for prediction confidence / UI gating."""

from typing import Any, Dict, List, Optional


def _has_stats(stats: Optional[Dict[str, Any]]) -> bool:
    if not stats:
        return False
    try:
        played = int(stats.get("played") or 0)
    except (TypeError, ValueError):
        played = 0
    gf = float(stats.get("goals_for") or 0)
    ga = float(stats.get("goals_against") or 0)
    return played > 0 or gf > 0 or ga > 0


def _position_ok(pos: Optional[Dict[str, Any]]) -> bool:
    if not pos:
        return False
    p = pos.get("position")
    if p is None:
        return False
    try:
        return int(p) >= 1
    except (TypeError, ValueError):
        return False


def _standings_pts(pos: Optional[Dict[str, Any]]) -> float:
    """Full table credit when position is known; prior-season rows still count."""
    if _position_ok(pos):
        return 5.0
    if not pos:
        return 0.0
    try:
        played = int(pos.get("played") or 0)
        points = int(pos.get("points") or 0)
    except (TypeError, ValueError):
        return 0.0
    if played > 0 and points > 0:
        return 3.5
    return 0.0


def _supplemental_pts(sup: Any) -> float:
    if not isinstance(sup, dict) or not sup:
        return 1.0
    useful = [
        k
        for k in sup
        if not str(k).endswith("_error")
        and k not in ("heavy_skipped",)
        and sup.get(k) not in (None, "", [], {})
    ]
    high_value = any(
        sup.get(k)
        for k in (
            "understat_light",
            "understat",
            "fbref_schedule",
            "statsbomb_open_team_proxy",
            "sofascore_xg",
            "fotmob_xg",
            "soccerstats_positions",
            "api_squad_depth",
        )
    )
    if high_value:
        return 3.0
    return 3.0 if len(useful) >= 3 else (2.0 if useful else 1.0)


def _supplemental_understat_source(sup: Any) -> Optional[str]:
    if not isinstance(sup, dict):
        return None
    for key in ("understat_light_source", "understat_source"):
        tag = sup.get(key)
        if isinstance(tag, str) and tag.strip():
            return tag.strip().lower()
    for key in ("understat_light", "understat"):
        us = sup.get(key)
        if not isinstance(us, dict):
            continue
        try:
            uh = float(us.get("xg_home"))
            ua = float(us.get("xg_away"))
        except (TypeError, ValueError):
            continue
        if uh > 0.04 and ua > 0.04 and (uh + ua) < 6.5:
            if sup.get("understat_light_team_rolling"):
                return "understat_team_xg"
            return "understat_xg"
    return None


def _effective_xg_source(enriched: Dict[str, Any]) -> str:
    src = (enriched.get("xg_source") or "unknown").lower()
    if src not in ("unknown", "goals_proxy", "mixed_api_goals_proxy", ""):
        return src
    from_sup = _supplemental_understat_source(enriched.get("supplemental"))
    if from_sup:
        return from_sup
    meta = enriched.get("scraped_xg_meta") or {}
    if meta.get("team_rolling"):
        return "understat_team_xg"
    return src


def _xg_points(src: str, n_h: float, n_a: float, enriched: Optional[Dict[str, Any]] = None) -> float:
    s = (src or "unknown").lower()
    meta = (enriched or {}).get("scraped_xg_meta") or {}
    if s in ("api_fixture_xg", "api_statistics_xg"):
        return 18.0
    if s == "stats_api_xg":
        return 15.0
    if s == "understat_xg":
        if meta.get("match_confident") or meta.get("understat_key"):
            return 16.0
        return 15.0
    if s == "understat_team_xg":
        try:
            hn = int(meta.get("home_n") or 0)
            an = int(meta.get("away_n") or 0)
        except (TypeError, ValueError):
            hn = an = 0
        if hn >= 5 and an >= 5:
            return 15.0
        if hn >= 3 and an >= 3:
            return 14.0
        return 14.0
    if s in (
        "scraped_recent_xg",
        "scottish_fbref_xg",
        "scottish_fbref_avg_xg",
        "fbref_schedule_xg",
        "fbref_schedule_avg_xg",
    ):
        return 15.0
    if s == "api_season_team_xg":
        if meta.get("api_season_xg_measured"):
            return 15.0
        return 14.0
    if s == "sofascore_xg":
        return 13.5
    if s == "fotmob_league_xg":
        try:
            hn = int(meta.get("home_n") or 0)
            an = int(meta.get("away_n") or 0)
        except (TypeError, ValueError):
            hn = an = 0
        if hn >= 10 and an >= 10:
            return 14.0
        return 13.0
    if s == "statsbomb_goals_proxy_xg":
        return 11.0
    if s in ("form_derived_xg",):
        return 9.0
    if s in ("partial_scraped_xg", "mixed_api_goals_proxy", "partial_single_side", "partial_xg"):
        return 10.0
    if s == "goals_proxy":
        if n_h >= 8.0 and n_a >= 8.0:
            return 12.0
        if n_h >= 4.0 and n_a >= 4.0:
            return 10.0
        return 6.0
    if s == "unknown":
        return 4.0
    return 6.0


def _side_markets_pts(enriched: Dict[str, Any]) -> float:
    mo = enriched.get("market_odds") or {}
    if bool((mo.get("btts") or {}).get("yes")) or bool((mo.get("totals_2_5") or {}).get("over")):
        return 4.0
    lo = enriched.get("line_odds") or {}
    if isinstance(lo, dict):
        if float(lo.get("btts_yes") or 0) > 1.0 or float(lo.get("over25") or 0) > 1.0:
            return 4.0
        if float(lo.get("over15") or 0) > 1.0 or float(lo.get("over35") or 0) > 1.0:
            return 3.0
    try:
        hb = float(enriched.get("home_btts_rate") or 0)
        ab = float(enriched.get("away_btts_rate") or 0)
        ho = float(enriched.get("home_over25_rate") or 0)
        ao = float(enriched.get("away_over25_rate") or 0)
    except (TypeError, ValueError):
        hb = ab = ho = ao = 0.0
    if hb > 0 and ab > 0 and ho > 0 and ao > 0:
        return 2.5
    return 0.0


def _field_quality_from_blocks(blocks: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Collapse low-level blocks into product-facing trust buckets."""
    by_key = {b.get("key"): b for b in blocks if isinstance(b, dict)}

    def bucket(label: str, keys: List[str]) -> Dict[str, Any]:
        max_pts = sum(float((by_key.get(k) or {}).get("max") or 0.0) for k in keys)
        earned = sum(float((by_key.get(k) or {}).get("earned") or 0.0) for k in keys)
        pct = round((earned / max_pts) * 100.0, 1) if max_pts > 0 else 0.0
        if pct >= 85:
            status = "strong"
        elif pct >= 65:
            status = "usable"
        elif pct >= 35:
            status = "thin"
        else:
            status = "missing"
        missing = [
            str((by_key.get(k) or {}).get("label") or k)
            for k in keys
            if by_key.get(k) and not by_key[k].get("ok")
        ]
        return {
            "label": label,
            "pct": pct,
            "status": status,
            "earned": round(earned, 2),
            "max": round(max_pts, 2),
            "missing": missing[:4],
        }

    return {
        "identity": bucket("Fixture identity", ["team_ids", "fixture_id"]),
        "form": bucket("Recent form", ["recent_home", "recent_away"]),
        "season_stats": bucket("Season stats", ["stats_home", "stats_away"]),
        "standings": bucket("League table", ["stand_home", "stand_away"]),
        "xg": bucket("Expected goals", ["xg"]),
        "odds": bucket("Odds markets", ["book_1x2", "side_markets"]),
        "context": bucket("Team news / context", ["supplemental", "injuries"]),
    }


def compute_fixture_data_quality(enriched: Dict[str, Any]) -> Dict[str, Any]:
    """
    Weighted coverage of inputs used by the model (IDs, recency, stats, table, xG, odds, side markets).

    Max score is 100. Block weights (points):
      team_ids 5, fixture_id 5, recent_home/away 8 each, stats_home/away 9 each,
      stand_home/away 5 each, xG 18, book_1x2 19, side_markets 4, supplemental 3, injuries 3.

    ``full_scope`` is True when score >= 85 (strong coverage for multi-market modelling).
    """
    blocks: List[Dict[str, Any]] = []
    score = 0.0

    def add(label: str, key: str, max_pts: float, earned: float) -> None:
        nonlocal score
        e = max(0.0, min(max_pts, earned))
        blocks.append(
            {
                "label": label,
                "key": key,
                "max": max_pts,
                "earned": round(e, 2),
                "ok": e >= max_pts * 0.85,
            }
        )
        score += e

    hid = (enriched.get("teams", {}) or {}).get("home", {}).get("id")
    aid = (enriched.get("teams", {}) or {}).get("away", {}).get("id")
    if not hid and enriched.get("home_id"):
        hid = enriched.get("home_id")
    if not aid and enriched.get("away_id"):
        aid = enriched.get("away_id")
    add("Team IDs", "team_ids", 5.0, 5.0 if (hid and aid) else 0.0)

    fx = enriched.get("fixture") or {}
    fid = fx.get("id") if isinstance(fx, dict) else None
    if fid is None:
        fid = enriched.get("id")
    add("Fixture id (API)", "fixture_id", 5.0, 5.0 if fid not in (None, "", 0, "0") else 0.0)

    n_h = float(enriched.get("home_recent_n") or 0)
    n_a = float(enriched.get("away_recent_n") or 0)
    home_recent_pts = 8.0 * min(1.0, n_h / 8.0)
    away_recent_pts = 8.0 * min(1.0, n_a / 8.0)
    if n_h >= 5.0 and n_a >= 5.0:
        home_recent_pts = min(8.0, home_recent_pts + 0.5)
        away_recent_pts = min(8.0, away_recent_pts + 0.5)
    add("Home match history", "recent_home", 8.0, home_recent_pts)
    add("Away match history", "recent_away", 8.0, away_recent_pts)

    hs = enriched.get("home_stats") or {}
    aws = enriched.get("away_stats") or {}
    add("Home season stats", "stats_home", 9.0, 9.0 if _has_stats(hs) else 0.0)
    add("Away season stats", "stats_away", 9.0, 9.0 if _has_stats(aws) else 0.0)

    hp = enriched.get("home_position") or {}
    ap = enriched.get("away_position") or {}
    add("Home league position", "stand_home", 5.0, _standings_pts(hp))
    add("Away league position", "stand_away", 5.0, _standings_pts(ap))

    src = _effective_xg_source(enriched)
    add("Expected goals (xG) source", "xg", 18.0, _xg_points(src, n_h, n_a, enriched))

    book = bool(enriched.get("odds_available")) or all(
        enriched.get(k) is not None and float(enriched.get(k) or 0) > 1.0
        for k in ("odds_home", "odds_draw", "odds_away")
    )
    if not book:
        pred = enriched.get("prediction") or {}
        bo = pred.get("bookmaker_odds") or {}
        book = all(float(bo.get(k) or 0) > 1.0 for k in ("home", "draw", "away"))
    add("1X2 book prices", "book_1x2", 19.0, 19.0 if book else 0.0)

    add("Side markets (BTTS / totals)", "side_markets", 4.0, _side_markets_pts(enriched))

    sup = enriched.get("supplemental") or {}
    add("Supplemental context", "supplemental", 3.0, _supplemental_pts(sup))

    inj = enriched.get("fixture_injuries")
    inj_pts = 3.0 if isinstance(inj, list) and fid not in (None, "", 0, "0") else 0.0
    add("Injury feed", "injuries", 3.0, inj_pts)

    pct = max(0.0, min(100.0, round(score, 1)))
    field_scores = _field_quality_from_blocks(blocks)
    weak_fields = [
        row["label"]
        for row in field_scores.values()
        if row.get("status") in ("thin", "missing")
    ]
    if pct >= 85 and not weak_fields:
        trust_label = "Strong data"
    elif pct >= 80:
        trust_label = "Good data, check weak fields"
    elif pct >= 65:
        trust_label = "Usable but cautious"
    else:
        trust_label = "Thin data"
    return {
        "score_pct": pct,
        "blocks": blocks,
        "field_scores": field_scores,
        "weak_fields": weak_fields[:5],
        "trust_label": trust_label,
        "full_scope": pct >= 85.0,
        "strong_scope": pct >= 80.0,
    }


def _stats_from_last10(rows: List[Any]) -> Dict[str, Any]:
    """Minimal season-stats shape when only parsed last-10 rows exist on a slim cache bundle."""
    if not rows:
        return {}
    gf = ga = 0
    for r in rows:
        if not isinstance(r, dict):
            continue
        try:
            gf += int(r.get("gf") or 0)
            ga += int(r.get("ga") or 0)
        except (TypeError, ValueError):
            continue
    n = len(rows)
    if n < 4:
        return {}
    return {"played": n, "goals_for": max(1, gf), "goals_against": max(1, ga)}


def compute_fixture_data_quality_from_row(fixture_row: Dict[str, Any]) -> Dict[str, Any]:
    """Re-score a slim dashboard/cache row using fields still present after bundle trim."""
    pred = fixture_row.get("prediction") or {}
    bo = pred.get("bookmaker_odds") or {}
    lo = pred.get("line_odds") or {}
    enriched: Dict[str, Any] = {
        "id": fixture_row.get("id"),
        "fixture": {"id": fixture_row.get("id")},
        "teams": {
            "home": {"id": fixture_row.get("home_id")},
            "away": {"id": fixture_row.get("away_id")},
        },
        "home_id": fixture_row.get("home_id"),
        "away_id": fixture_row.get("away_id"),
        "home_recent_n": len(fixture_row.get("home_last10") or []),
        "away_recent_n": len(fixture_row.get("away_last10") or []),
        "home_position": fixture_row.get("home_position") or {},
        "away_position": fixture_row.get("away_position") or {},
        "xg_source": fixture_row.get("xg_source"),
        "fixture_injuries": fixture_row.get("fixture_injuries"),
        "prediction": pred,
        "line_odds": lo,
        "odds_available": all(float(bo.get(k) or 0) > 1.0 for k in ("home", "draw", "away")),
        "odds_home": bo.get("home"),
        "odds_draw": bo.get("draw"),
        "odds_away": bo.get("away"),
        "home_btts_rate": pred.get("home_btts_rate"),
        "away_btts_rate": pred.get("away_btts_rate"),
        "home_over25_rate": pred.get("home_over25_rate"),
        "away_over25_rate": pred.get("away_over25_rate"),
        "supplemental": fixture_row.get("supplemental") or {},
    }
    hs = fixture_row.get("home_stats")
    aws = fixture_row.get("away_stats")
    if hs:
        enriched["home_stats"] = hs
    elif fixture_row.get("home_last10"):
        inferred = _stats_from_last10(fixture_row.get("home_last10") or [])
        if inferred:
            enriched["home_stats"] = inferred
    if aws:
        enriched["away_stats"] = aws
    elif fixture_row.get("away_last10"):
        inferred = _stats_from_last10(fixture_row.get("away_last10") or [])
        if inferred:
            enriched["away_stats"] = inferred
    mo = fixture_row.get("market_odds")
    if mo:
        enriched["market_odds"] = mo
    sup = enriched.get("supplemental") or {}
    if sup.get("understat_light_home_n") is not None or sup.get("understat_light_away_n") is not None:
        enriched["scraped_xg_meta"] = {
            "home_n": sup.get("understat_light_home_n"),
            "away_n": sup.get("understat_light_away_n"),
            "team_rolling": bool(sup.get("understat_light_team_rolling")),
        }
    return compute_fixture_data_quality(enriched)
