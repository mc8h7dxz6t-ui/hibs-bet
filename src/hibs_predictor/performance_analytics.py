"""Dedicated performance / track-record views (separate from Insights handicapping UI)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from hibs_predictor.prediction_log import (
    _monitor_combined_day,
    monitor_summary_dict,
    monitor_today_dict,
    monitor_yesterday_dict,
    prediction_log_enabled,
    pred_log_sync_cron_status,
    report_summary_dict,
)


def _day_scorecard(day: Dict[str, Any], *, label: str) -> Dict[str, Any]:
    """Compact W/L for model 1X2 and value legs."""
    kickoff = day.get("kickoff") or day
    scored = day.get("scored") or {}
    bp_k = kickoff.get("best_pick") or {}
    vp_k = kickoff.get("value_pick") or {}
    bp_s = scored.get("best_pick") or {}
    vp_s = scored.get("value_pick") or {}
    return {
        "label": label,
        "date_local": day.get("date_local") or kickoff.get("date_local"),
        "kickoff": {
            "n": kickoff.get("n_logged", 0),
            "model": bp_k,
            "value": vp_k,
            "model_record": _record_str(bp_k),
            "value_record": _record_str(vp_s if vp_s.get("settled") else vp_k, value=True),
        },
        "scored": {
            "n": scored.get("n_logged", 0),
            "model": bp_s,
            "value": vp_s,
            "model_record": _record_str(bp_s),
            "value_record": _record_str(vp_s, value=True),
        },
    }


def _record_str(
    tally: Dict[str, Any],
    *,
    value: bool = False,
) -> str:
    w = int(tally.get("wins") or 0)
    l = int(tally.get("losses") or 0)
    p = int(tally.get("pending") or 0)
    if value:
        a = int(tally.get("attempts") or 0)
        if not a:
            return "—"
    elif not (w or l or p):
        return "—"
    base = f"{w}/{w + l}" if (w + l) else f"0/0"
    if p:
        base += f" (+{p} pending)"
    if value and tally.get("hit_rate_pct") is not None and (w + l):
        base += f" · {tally['hit_rate_pct']}%"
    return base


def performance_daily_history(*, days: int = 14) -> List[Dict[str, Any]]:
    """One row per calendar day (display TZ): kickoff vs FT-recorded tallies."""
    out: List[Dict[str, Any]] = []
    for offset in range(0, -int(days), -1):
        if offset == 0:
            label = "Today"
        elif offset == -1:
            label = "Yesterday"
        else:
            label = f"{-offset}d ago"
        combined = _monitor_combined_day(day_offset=offset, empty_label=label.lower())
        out.append(_day_scorecard(combined, label=label))
    return out


def _high_confidence_rows(rows: List[Dict[str, Any]], *, min_pct: float = 55.0) -> List[Dict[str, Any]]:
    """Fixtures where the model 1X2 lean was at least min_pct (most probable list)."""
    picked: List[Dict[str, Any]] = []
    for row in rows or []:
        pct = row.get("model_pct")
        if pct is None:
            continue
        try:
            if float(pct) < min_pct:
                continue
        except (TypeError, ValueError):
            continue
        picked.append(row)
    picked.sort(key=lambda r: (-(float(r.get("model_pct") or 0)), r.get("match") or ""))
    return picked


def build_performance_page_dict(*, history_days: int = 14) -> Dict[str, Any]:
    """
    Full payload for /performance — prediction log only; does not touch fixture enrich/DQ.
    """
    history_days = max(7, min(60, int(history_days)))
    rolling = monitor_summary_dict()
    yesterday = monitor_yesterday_dict()
    today = monitor_today_dict()
    audit = report_summary_dict()

    ys = yesterday.get("scored") or {}
    yk = yesterday.get("kickoff") or yesterday
    ts = today.get("scored") or {}
    tk = today.get("kickoff") or today

    return {
        "ok": True,
        "enabled": prediction_log_enabled(),
        "history_days": history_days,
        "display_tz_label": yesterday.get("display_tz_label") or today.get("display_tz_label") or "local",
        "pred_log_sync_cron": pred_log_sync_cron_status(),
        "rolling": rolling,
        "audit": audit,
        "yesterday": yesterday,
        "today": today,
        "daily_history": performance_daily_history(days=history_days),
        "primary_view_hint": (
            "Use <strong>Results recorded</strong> for your track record (e.g. 9/10 when sync ran that day). "
            "<strong>Kickoff day</strong> only lists matches that started that calendar day — "
            "often empty mid-week when friendlies kicked off earlier."
        ),
        "yesterday_scored": {
            "rows": ys.get("rows") or [],
            "high_confidence": _high_confidence_rows(ys.get("rows") or []),
            "best_pick": ys.get("best_pick") or {},
            "value_pick": ys.get("value_pick") or {},
            "message": ys.get("message"),
        },
        "yesterday_kickoff": {
            "rows": yk.get("rows") or [],
            "high_confidence": _high_confidence_rows(yk.get("rows") or []),
            "best_pick": yk.get("best_pick") or {},
            "value_pick": yk.get("value_pick") or {},
            "message": yk.get("message"),
        },
        "today_scored": {
            "rows": ts.get("rows") or [],
            "high_confidence": _high_confidence_rows(ts.get("rows") or []),
            "best_pick": ts.get("best_pick") or {},
            "value_pick": ts.get("value_pick") or {},
            "message": ts.get("message"),
        },
        "today_kickoff": {
            "rows": tk.get("rows") or [],
            "high_confidence": _high_confidence_rows(tk.get("rows") or []),
            "best_pick": tk.get("best_pick") or {},
            "value_pick": tk.get("value_pick") or {},
            "message": tk.get("message"),
        },
    }
