#!/usr/bin/env python3
"""Export high-confidence match previews as plain text (newsletter / Telegram feed)."""

from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))


def _preview_line(fixture: dict) -> str | None:
    pred = fixture.get("prediction") or {}
    if pred.get("prediction_unavailable"):
        return None
    si = pred.get("structured_insight") or {}
    pick = si.get("pick") or pred.get("predicted_outcome")
    if not pick:
        return None
    dq = (fixture.get("data_quality") or {}).get("score_pct")
    home = fixture.get("home") or "?"
    away = fixture.get("away") or "?"
    league = fixture.get("league_name") or fixture.get("league") or ""
    xg_h = pred.get("expected_goals_home")
    xg_a = pred.get("expected_goals_away")
    probs = pred.get("probabilities_pct") or {}
    line = f"{league}: {home} vs {away} — {pick}"
    if probs:
        line += f" (H {probs.get('home')}% / D {probs.get('draw')}% / A {probs.get('away')}%)"
    if xg_h is not None and xg_a is not None:
        line += f" · xG {xg_h}-{xg_a}"
    if dq is not None:
        line += f" · data {dq:.0f}%"
    return line


def main() -> None:
    parser = argparse.ArgumentParser(description="Export match preview text lines")
    parser.add_argument("--min-dq", type=float, default=85.0, help="Minimum data quality %%")
    parser.add_argument("--out", type=str, default="", help="Write to file (default stdout)")
    parser.add_argument("--json", action="store_true", help="Emit JSON array instead of text")
    args = parser.parse_args()

    from dotenv import load_dotenv

    load_dotenv(os.path.join(_ROOT, ".env"))
    from hibs_predictor.web import _load_fixtures_for_http

    bundle = _load_fixtures_for_http(include_domestic=False)
    upcoming = bundle.get("upcoming") or []
    lines = []
    for fx in upcoming:
        dq = float((fx.get("data_quality") or {}).get("score_pct") or 0)
        if dq < args.min_dq:
            continue
        text = _preview_line(fx)
        if text:
            lines.append({"fixture_id": fx.get("id"), "line": text, "dq": dq})

    if args.json:
        payload = json.dumps(lines, indent=2)
    else:
        payload = "\n".join(row["line"] for row in lines) + ("\n" if lines else "")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(payload)
        print(f"Wrote {len(lines)} line(s) to {args.out}")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
