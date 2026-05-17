"""Build the product-facing Insights page from existing fixture packets."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from hibs_predictor.assistant_recommendations import (
    build_assistant_recommendations,
    build_bet_builder_suggestions,
    is_analyzable,
)
from hibs_predictor.data_coverage import data_coverage_status
from hibs_predictor.match_insight import build_assistant_packet


def _num(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _fmt_match(pkt: Dict[str, Any]) -> str:
    return f"{pkt.get('home', '?')} vs {pkt.get('away', '?')}"


def _top_probability_rows(packets: List[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for pkt in packets:
        for item in pkt.get("pick_menu") or []:
            key = item.get("key")
            if key in ("avoid", "odds_only") or item.get("model_pct") is None:
                continue
            if key in ("home_or_draw", "away_or_draw", "home_or_away") and item.get("odds") is None:
                # Keep double-chance in the model menu, but do not present it as an actionable top price without book odds.
                continue
            rows.append(
                {
                    "fixture_id": pkt.get("id"),
                    "match": _fmt_match(pkt),
                    "league": pkt.get("league_name") or pkt.get("league"),
                    "kickoff_time": pkt.get("kickoff_time"),
                    "market_key": key,
                    "market_label": item.get("label") or key,
                    "model_pct": item.get("model_pct"),
                    "odds": item.get("odds"),
                    "data_quality_pct": pkt.get("data_quality_pct"),
                    "is_value": bool(item.get("is_value")),
                    "edge_pct": item.get("edge_pct"),
                }
            )
    rows.sort(key=lambda r: (_num(r.get("model_pct")), _num(r.get("data_quality_pct"))), reverse=True)
    return rows[:limit]


def _value_opportunities(packets: List[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for pkt in packets:
        for item in pkt.get("value_bets_display") or []:
            rows.append(
                {
                    "fixture_id": pkt.get("id"),
                    "match": _fmt_match(pkt),
                    "league": pkt.get("league_name") or pkt.get("league"),
                    "kickoff_time": pkt.get("kickoff_time"),
                    "market_label": item.get("market_label") or item.get("outcome"),
                    "odds": item.get("odds"),
                    "edge_pct": item.get("edge_pct"),
                    "roi_percent": item.get("roi_percent"),
                    "data_quality_pct": pkt.get("data_quality_pct"),
                }
            )
    rows.sort(key=lambda r: (_num(r.get("edge_pct")), _num(r.get("roi_percent"))), reverse=True)
    return rows[:limit]


def _data_quality_alerts(packets: List[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []
    for pkt in packets:
        dq = pkt.get("data_quality") or {}
        pct = pkt.get("data_quality_pct")
        missing = [
            b.get("label")
            for b in (dq.get("blocks") or [])
            if isinstance(b, dict) and not b.get("ok")
        ]
        if pct is None or _num(pct) < 80 or missing:
            alerts.append(
                {
                    "fixture_id": pkt.get("id"),
                    "match": _fmt_match(pkt),
                    "league": pkt.get("league_name") or pkt.get("league"),
                    "data_quality_pct": pct,
                    "missing": missing[:3],
                    "xg_source": pkt.get("xg_source") or "unknown",
                    "analyzable": is_analyzable(pkt),
                }
            )
    alerts.sort(key=lambda r: (_num(r.get("data_quality_pct"), -1), r.get("match") or ""))
    return alerts[:limit]


def _form_xg_table_angles(packets: List[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for pkt in packets:
        ps = pkt.get("probability_scores") or {}
        hp = pkt.get("home_position") or {}
        ap = pkt.get("away_position") or {}
        hf = pkt.get("home_form_summary") or {}
        af = pkt.get("away_form_summary") or {}
        bullets: List[str] = []
        if ps.get("xg_home") is not None and ps.get("xg_away") is not None:
            bullets.append(f"xG lean {ps.get('xg_home')}–{ps.get('xg_away')} from {pkt.get('xg_source') or 'model blend'}.")
        if hp.get("position") and ap.get("position"):
            bullets.append(f"Table: {pkt.get('home')} {hp.get('position')} vs {pkt.get('away')} {ap.get('position')}.")
        if hf.get("played") or af.get("played"):
            bullets.append(
                f"Form: {pkt.get('home')} W{hf.get('wins', 0)} D{hf.get('draws', 0)} L{hf.get('losses', 0)}; "
                f"{pkt.get('away')} W{af.get('wins', 0)} D{af.get('draws', 0)} L{af.get('losses', 0)}."
            )
        if not bullets:
            continue
        rows.append(
            {
                "fixture_id": pkt.get("id"),
                "match": _fmt_match(pkt),
                "league": pkt.get("league_name") or pkt.get("league"),
                "kickoff_time": pkt.get("kickoff_time"),
                "bullets": bullets[:3],
                "data_quality_pct": pkt.get("data_quality_pct"),
            }
        )
    rows.sort(key=lambda r: _num(r.get("data_quality_pct")), reverse=True)
    return rows[:limit]


def build_insights(fixtures: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a compact handicapper-style insights payload for templates/API."""
    packets = [build_assistant_packet(f) for f in fixtures]
    recommendations = build_assistant_recommendations(packets)
    return {
        "packets": packets,
        "recommendations": recommendations,
        "summary": recommendations.get("deep_dive_summary") or {},
        "top_probabilities": _top_probability_rows(packets),
        "value_opportunities": _value_opportunities(packets),
        "data_quality_alerts": _data_quality_alerts(packets),
        "angles": _form_xg_table_angles(packets),
        "bet_builders": build_bet_builder_suggestions(packets, limit=8),
        "coverage": data_coverage_status(),
    }
