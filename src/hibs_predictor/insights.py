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
from hibs_predictor.prediction_log import report_summary_dict


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


def _trust_digest(packets: List[Dict[str, Any]]) -> Dict[str, Any]:
    labels: Dict[str, int] = {}
    weak_counts: Dict[str, int] = {}
    for pkt in packets:
        label = pkt.get("trust_label") or "Unknown"
        labels[label] = labels.get(label, 0) + 1
        for field in pkt.get("weak_fields") or []:
            key = str(field)
            weak_counts[key] = weak_counts.get(key, 0) + 1
    weak_sorted = sorted(weak_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return {
        "labels": labels,
        "weak_fields": [{"label": k, "count": v} for k, v in weak_sorted[:8]],
        "fixture_count": len(packets),
    }


def _avoid_watchlist(packets: List[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for pkt in packets:
        si = pkt.get("structured_insight") or {}
        rejected = pkt.get("value_bets_rejected") or {}
        weak = pkt.get("weak_fields") or []
        if si.get("pick_key") != "avoid" and not rejected and _num(pkt.get("data_quality_pct")) >= 70:
            continue
        reasons: List[str] = []
        if si.get("pick_key") == "avoid":
            reasons.append("model says avoid")
        if rejected:
            reasons.append("value guardrails blocked " + ", ".join(list(rejected.keys())[:3]))
        if weak:
            reasons.append("thin " + ", ".join(str(x) for x in weak[:2]))
        rows.append(
            {
                "fixture_id": pkt.get("id"),
                "match": _fmt_match(pkt),
                "league": pkt.get("league_name") or pkt.get("league"),
                "kickoff_time": pkt.get("kickoff_time"),
                "data_quality_pct": pkt.get("data_quality_pct"),
                "reasons": reasons[:3],
            }
        )
    rows.sort(key=lambda r: (_num(r.get("data_quality_pct")), r.get("match") or ""))
    return rows[:limit]


def _audit_snapshot() -> Dict[str, Any]:
    try:
        report = report_summary_dict()
    except Exception as exc:
        return {"ok": False, "message": f"audit unavailable: {exc!r}"}
    if not report.get("ok"):
        return {"ok": False, "message": "Prediction audit not enabled yet."}
    if not report.get("n_used_metrics"):
        return {
            "ok": True,
            "message": report.get("message") or "No scored predictions yet; enable logging and sync results after matches finish.",
            "n_used_metrics": 0,
            "brier_by_data_quality_bucket": report.get("brier_by_data_quality_bucket") or [],
        }
    return {
        "ok": True,
        "n_used_metrics": report.get("n_used_metrics"),
        "brier_score_1x2": report.get("brier_score_1x2"),
        "log_loss_1x2": report.get("log_loss_1x2"),
        "value_hit_rate": report.get("value_hit_rate"),
        "brier_by_data_quality_bucket": report.get("brier_by_data_quality_bucket") or [],
    }


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
        "trust_digest": _trust_digest(packets),
        "avoid_watchlist": _avoid_watchlist(packets),
        "audit": _audit_snapshot(),
    }
