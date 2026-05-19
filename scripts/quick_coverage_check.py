#!/usr/bin/env python3
"""Quick local xG / data-quality snapshot across sample leagues."""

from __future__ import annotations

import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.chdir(ROOT)

# Sample: UK + one mid-tier EU + one cup
SAMPLE_LEAGUES = [
    "SCOTLAND",
    "EPL",
    "CHAMPIONSHIP",
    "LEAGUE_ONE",
    "EREDIVISIE",
    "BELGIUM_FIRST",
    "UCL",
]
MAX_PER_LEAGUE = 3


def run_pass(label: str) -> None:
    from hibs_predictor.config import LEAGUES
    from hibs_predictor.data_aggregator import DataAggregator
    from hibs_predictor.web import fetch_next_48h_fixtures, _safe_enrich

    agg = DataAggregator()
    xg_counts: Counter = Counter()
    dq_buckets: Counter = Counter()
    by_league: dict = defaultdict(list)
    thin = []
    n = 0

    print(f"\n=== {label} ===")
    print(f"MAX_DATA={os.getenv('HIBS_MAX_DATA', '(unset)')}  SCRAPE_XG={os.getenv('HIBS_SCRAPE_XG', '1')}")

    for code in SAMPLE_LEAGUES:
        if code not in LEAGUES:
            continue
        try:
            fixtures = fetch_next_48h_fixtures(code)[:MAX_PER_LEAGUE]
        except Exception as exc:
            print(f"  [{code}] fetch error: {exc!r}")
            continue
        if not fixtures:
            print(f"  [{code}] no fixtures in window")
            continue
        for fx in fixtures:
            def _team_name(side: str) -> str:
                raw = fx.get(side)
                if isinstance(raw, dict):
                    return str(raw.get("name") or "?")
                if isinstance(raw, str):
                    return raw
                teams = fx.get("teams") or {}
                blk = teams.get(side) if isinstance(teams, dict) else {}
                return str((blk or {}).get("name") or "?") if isinstance(blk, dict) else "?"

            home = _team_name("home")
            away = _team_name("away")
            try:
                en = _safe_enrich(fx, code)
            except Exception as exc:
                print(f"  [{code}] {home} v {away}: enrich failed {exc!r}")
                continue
            src = str(en.get("xg_source") or "unknown")
            dq = en.get("data_quality") or {}
            pct = float(dq.get("score_pct") or 0)
            xg_counts[src] += 1
            if pct >= 85:
                dq_buckets["full_85+"] += 1
            elif pct >= 70:
                dq_buckets["70-84"] += 1
            elif pct >= 50:
                dq_buckets["50-69"] += 1
            else:
                dq_buckets["under_50"] += 1
            by_league[code].append((src, pct, home, away))
            if src in ("goals_proxy", "unknown") or pct < 70:
                thin.append((code, home, away, src, pct))
            n += 1

    print(f"\nFixtures enriched: {n}")
    print("\nxG source mix:")
    for src, c in xg_counts.most_common():
        print(f"  {src:28} {c:3}  ({100 * c / max(1, n):.0f}%)")
    print("\nData quality (score_pct):")
    for k in ("full_85+", "70-84", "50-69", "under_50"):
        c = dq_buckets.get(k, 0)
        print(f"  {k:12} {c:3}  ({100 * c / max(1, n):.0f}%)")
    goals_proxy = xg_counts.get("goals_proxy", 0)
    print(f"\ngoals_proxy only: {goals_proxy}/{n} ({100 * goals_proxy / max(1, n):.0f}%)")
    print("\nPer fixture:")
    for code in SAMPLE_LEAGUES:
        for src, pct, h, a in by_league.get(code, []):
            print(f"  {code:14} {h:16} v {a:16}  xG={src:22} DQ={pct:.0f}%")
    if thin:
        print("\nThinnest rows (goals_proxy/unknown or DQ < 70%):")
        for code, h, a, src, pct in thin[:12]:
            print(f"  {code:14} {h:18} v {a:18}  xG={src:22} DQ={pct:.0f}%")
        if len(thin) > 12:
            print(f"  ... and {len(thin) - 12} more")


if __name__ == "__main__":
    os.environ.setdefault("HIBS_FETCH_DAYS", "5")
    run_pass("Current .env (no overrides)")
    os.environ["HIBS_MAX_DATA"] = "1"
    os.environ.setdefault("HIBS_SCRAPE_XG", "1")
    run_pass("With HIBS_MAX_DATA=1")
