#!/usr/bin/env python3
"""Count fixtures in the fetch window with data_quality >= 78% and >= 85%."""

from __future__ import annotations

import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.chdir(ROOT)

os.environ.setdefault("HIBS_FETCH_DAYS", "7")
os.environ.setdefault("HIBS_SCRAPE_XG", "1")
os.environ.setdefault("HIBS_ENABLE_SUPPLEMENTAL", "1")


def _league_filter() -> list[str] | None:
    raw = (os.getenv("HIBS_MIN_ENRICH_LEAGUES") or "").strip()
    if raw:
        return [c.strip().upper() for c in raw.split(",") if c.strip()]
    if os.getenv("HIBS_MIN_ENRICH_AUTO", "").strip().lower() not in ("1", "true", "yes", "on"):
        return None
    from datetime import datetime, timezone

    from hibs_predictor.config import ALL_LEAGUE_CODES, LEAGUES
    from hibs_predictor.web import fetch_next_48h_fixtures

    today = datetime.now(timezone.utc).date().isoformat()
    codes: list[str] = []
    for code in ALL_LEAGUE_CODES:
        if code not in LEAGUES:
            continue
        try:
            rows = fetch_next_48h_fixtures(code)
        except Exception:
            continue
        for row in rows or []:
            kick = str(row.get("kickoff_sort") or row.get("date") or "")
            if kick.startswith(today):
                codes.append(code)
                break
    return codes or None


def run(label: str) -> dict:
    from hibs_predictor.config import ALL_LEAGUE_CODES, LEAGUES
    from hibs_predictor.data_quality import (
        compute_fixture_data_quality,
        compute_fixture_data_quality_from_row,
    )
    from hibs_predictor.web import fetch_next_48h_fixtures, _safe_enrich, _slim_row_enrich_fresh

    filt = _league_filter()
    codes = [c for c in ALL_LEAGUE_CODES if c in LEAGUES and (not filt or c in filt)]

    n = g78 = g85 = 0
    by_league: dict[str, list[float]] = defaultdict(list)
    xg_src: Counter = Counter()
    thin_leagues: Counter = Counter()

    print(f"\n=== {label} ===")
    print(f"leagues={len(codes)}  HIBS_MAX_DATA={os.getenv('HIBS_MAX_DATA', '(unset)')}")

    for code in codes:
        try:
            fixtures = fetch_next_48h_fixtures(code)
        except Exception as exc:
            print(f"  [{code}] fetch error: {exc!r}")
            continue
        if not fixtures:
            thin_leagues[code] += 1
            continue
        for fx in fixtures:
            try:
                if _slim_row_enrich_fresh(fx):
                    en = fx
                    dq = compute_fixture_data_quality_from_row(fx)
                else:
                    en = _safe_enrich(fx, code)
                    dq = compute_fixture_data_quality(en)
            except Exception:
                continue
            pct = float(dq.get("score_pct") or 0)
            n += 1
            by_league[code].append(pct)
            xg_src[str(en.get("xg_source") or fx.get("xg_source") or "unknown")] += 1
            if pct >= 78:
                g78 += 1
            if pct >= 85:
                g85 += 1
            if pct < 78:
                thin_leagues[code] += 1

    print(f"fixtures enriched: {n}")
    print(f"dq >= 78%: {g78} ({100 * g78 / max(1, n):.1f}%)")
    print(f"dq >= 85%: {g85} ({100 * g85 / max(1, n):.1f}%)")
    print("\nxG sources:")
    for src, c in xg_src.most_common(12):
        print(f"  {src:28} {c}")
    if thin_leagues:
        print("\nLeagues with thin rows (dq<78 or no fixtures):")
        for lc, c in thin_leagues.most_common(20):
            print(f"  {lc:22} {c}")
    return {"n": n, "g78": g78, "g85": g85}


if __name__ == "__main__":
    before = run("baseline (current .env)")
    os.environ["HIBS_MAX_DATA"] = "1"
    os.environ.setdefault("HIBS_ENABLE_STATSBOMB_LIGHT", "1")
    after = run("with HIBS_MAX_DATA=1 + STATSBOMB_LIGHT")
    print("\n--- delta ---")
    print(f"dq>=78: {before['g78']} -> {after['g78']} (+{after['g78'] - before['g78']})")
    print(f"dq>=85: {before['g85']} -> {after['g85']} (+{after['g85'] - before['g85']})")
