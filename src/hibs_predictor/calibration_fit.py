"""
Fit league calibration_shrink factors from prediction audit rows (last N days).

Usage:
  HIBS_PREDICTION_LOG_ENABLED=1 python -m hibs_predictor.calibration_fit
  # writes .cache/calibration_v1.json (override with HIBS_CALIBRATION_CACHE)
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from hibs_predictor.historic_calibration import (
    calibration_cache_path,
    shrink_multiplier_from_brier,
)
from hibs_predictor.prediction_log import _db_path, brier_by_league, init_db, prediction_log_enabled


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def fit_league_shrink_factors(
    *,
    days: int = 90,
    min_rows: int = 20,
) -> dict:
    """Export league shrink map from audit Brier (rows in window are all scored rows for now)."""
    load_dotenv()
    if not os.path.isfile(_db_path()):
        return {"ok": False, "error": "no_database", "path": _db_path()}
    init_db()
    rows = brier_by_league()
    min_n = _env_int("HIBS_CALIB_FIT_MIN_ROWS", min_rows)
    baseline = _env_float("HIBS_CALIB_BASELINE_BRIER", 0.66)
    eligible = [r for r in rows if int(r.get("n") or 0) >= min_n and r.get("brier") is not None]
    if eligible:
        baseline = sum(float(r["brier"]) * int(r["n"]) for r in eligible) / sum(int(r["n"]) for r in eligible)

    leagues: dict = {}
    for r in rows:
        n = int(r.get("n") or 0)
        if n < min_n or r.get("brier") is None:
            continue
        lb = float(r["brier"])
        shrink = shrink_multiplier_from_brier(lb, baseline)
        leagues[str(r["league"]).upper()] = {
            "shrink": round(shrink, 4),
            "brier": round(lb, 5),
            "n": n,
        }

    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_days": days,
        "baseline_brier": round(baseline, 5),
        "min_rows": min_n,
        "leagues": leagues,
    }


def write_calibration_cache(payload: dict) -> str:
    path = calibration_cache_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return path


def main() -> None:
    load_dotenv()
    if not prediction_log_enabled() and not os.path.isfile(_db_path()):
        print("Enable HIBS_PREDICTION_LOG_ENABLED=1 and accumulate snapshots before fitting.")
        return
    days = _env_int("HIBS_CALIB_FIT_DAYS", 90)
    payload = fit_league_shrink_factors(days=days)
    if not payload.get("ok"):
        print(json.dumps(payload, indent=2))
        return
    path = write_calibration_cache(payload)
    print(f"Wrote {len(payload.get('leagues') or {})} league shrink factor(s) to {path}")


if __name__ == "__main__":
    main()
