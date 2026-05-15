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


def compute_fixture_data_quality(enriched: Dict[str, Any]) -> Dict[str, Any]:
    """
    Weighted coverage of inputs used by the model (IDs, recency, stats, table, xG, odds, side markets).

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
    add("Team IDs", "team_ids", 5.0, 5.0 if (hid and aid) else 0.0)

    fx = enriched.get("fixture") or {}
    fid = fx.get("id") if isinstance(fx, dict) else None
    if fid is None:
        fid = enriched.get("id")
    add("Fixture id (API)", "fixture_id", 5.0, 5.0 if fid not in (None, "", 0, "0") else 0.0)

    n_h = float(enriched.get("home_recent_n") or 0)
    n_a = float(enriched.get("away_recent_n") or 0)
    add("Home match history", "recent_home", 8.0, 8.0 * min(1.0, n_h / 8.0))
    add("Away match history", "recent_away", 8.0, 8.0 * min(1.0, n_a / 8.0))

    hs = enriched.get("home_stats") or {}
    aws = enriched.get("away_stats") or {}
    add("Home season stats", "stats_home", 9.0, 9.0 if _has_stats(hs) else 0.0)
    add("Away season stats", "stats_away", 9.0, 9.0 if _has_stats(aws) else 0.0)

    hp = enriched.get("home_position") or {}
    ap = enriched.get("away_position") or {}
    add("Home league position", "stand_home", 5.0, 5.0 if _position_ok(hp) else 0.0)
    add("Away league position", "stand_away", 5.0, 5.0 if _position_ok(ap) else 0.0)

    src = (enriched.get("xg_source") or "unknown").lower()
    if src == "api_fixture_xg":
        xg_pts = 18.0
    elif src == "stats_api_xg":
        xg_pts = 15.0
    elif src in ("understat_xg", "scraped_recent_xg", "scottish_fbref_xg", "scottish_fbref_avg_xg"):
        xg_pts = 15.0
    elif src in ("partial_scraped_xg", "mixed_api_goals_proxy", "partial_single_side", "partial_xg"):
        xg_pts = 10.0
    else:
        xg_pts = 4.0
    add("Expected goals (xG) source", "xg", 18.0, xg_pts)

    book = bool(enriched.get("odds_available")) or all(
        enriched.get(k) is not None and float(enriched.get(k) or 0) > 1.0
        for k in ("odds_home", "odds_draw", "odds_away")
    )
    add("1X2 book prices", "book_1x2", 19.0, 19.0 if book else 0.0)

    mo = enriched.get("market_odds") or {}
    side_ok = bool((mo.get("btts") or {}).get("yes")) or bool((mo.get("totals_2_5") or {}).get("over"))
    add("Side markets (BTTS / totals)", "side_markets", 4.0, 4.0 if side_ok else 0.0)

    sup = enriched.get("supplemental") or {}
    add("Supplemental context", "supplemental", 3.0, 3.0 if isinstance(sup, dict) and len(sup) > 0 else 1.0)

    inj = enriched.get("fixture_injuries")
    inj_pts = 3.0 if isinstance(inj, list) and fid not in (None, "", 0, "0") else 0.0
    add("Injury feed", "injuries", 3.0, inj_pts)

    # Max theoretical = 100.0
    pct = max(0.0, min(100.0, round(score, 1)))
    return {
        "score_pct": pct,
        "blocks": blocks,
        "full_scope": pct >= 85.0,
        "strong_scope": pct >= 80.0,
    }
