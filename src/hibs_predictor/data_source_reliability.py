"""
Best-effort probes for hibs-bet external sources (APIs + scrapers + open data).

Run: ``python3 -m hibs_predictor.main data-sources-probe``

Results are factual (HTTP status, parse success) — not a legal/ToS endorsement.
"""

from __future__ import annotations

import os
import time
from datetime import date
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv

from hibs_predictor.data_source_policy import policy_summary_dict


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


def run_all_probes() -> Dict[str, Any]:
    load_dotenv()
    out: Dict[str, Any] = {"policy": policy_summary_dict(), "sources": []}
    rows: List[Dict[str, Any]] = []

    # --- StatsBomb open (GitHub) ---
    t0 = time.perf_counter()
    sb_row: Dict[str, Any] = {"id": "statsbomb_open", "kind": "open_data", "ok": False, "ms": None, "detail": {}}
    try:
        from hibs_predictor.scrapers.statsbomb_open import (
            OPEN_BASE,
            latest_open_season_meta,
            load_matches,
            summarize_matches_in_policy_window,
        )

        r = requests.get(f"{OPEN_BASE}/competitions.json", timeout=22)
        sb_row["ms"] = _ms(t0)
        sb_row["ok"] = r.status_code == 200
        sb_row["detail"]["competitions_http"] = r.status_code
        if r.ok:
            meta = latest_open_season_meta("LA_LIGA")
            sb_row["detail"]["sample_league_meta"] = meta
            if meta:
                t1 = time.perf_counter()
                mlist = load_matches(int(meta["competition_id"]), int(meta["season_id"]))
                sb_row["detail"]["sample_matches_n"] = len(mlist or [])
                sb_row["detail"]["matches_fetch_ms"] = _ms(t1)
                lo = date.fromisoformat(out["policy"]["window_start_utc"][:10])
                hi = date.fromisoformat(out["policy"]["window_end_utc"][:10])
                summ = summarize_matches_in_policy_window("LA_LIGA", lo, hi)
                sb_row["detail"]["policy_window_match_count_la_liga"] = summ.get("match_count_in_window")
                sb_row["detail"]["policy_window_note"] = summ.get("note")
    except Exception as exc:
        sb_row["ms"] = _ms(t0)
        sb_row["error"] = str(exc)[:200]
    rows.append(sb_row)

    # --- Understat (EPL page + JSON extract) ---
    t0 = time.perf_counter()
    us_row: Dict[str, Any] = {"id": "understat", "kind": "scrape", "ok": False, "ms": None, "detail": {}}
    try:
        from hibs_predictor.scrapers.understat_client import _extract_json_array

        headers = {"User-Agent": "hibs-bet/1.0 (reliability probe)"}
        ok_any = False
        best_url = ""
        best_n = 0
        for y in (date.today().year, date.today().year - 1):
            url = f"https://understat.com/league/EPL/{y}"
            r = requests.get(url, headers=headers, timeout=22)
            if not r.ok:
                continue
            parsed = _extract_json_array(r.text)
            n = len(parsed) if parsed else 0
            if n > best_n:
                best_n = n
                best_url = url
            if parsed:
                ok_any = True
        us_row["ms"] = _ms(t0)
        us_row["ok"] = ok_any
        us_row["detail"]["best_url"] = best_url
        us_row["detail"]["embedded_rows"] = best_n
        if not ok_any:
            us_row["detail"]["parse"] = "no_embedded_json_in_tried_years"
    except Exception as exc:
        us_row["ms"] = _ms(t0)
        us_row["error"] = str(exc)[:200]
    rows.append(us_row)

    # --- FBref (one squad table page) ---
    t0 = time.perf_counter()
    fb_row: Dict[str, Any] = {"id": "fbref", "kind": "scrape", "ok": False, "ms": None, "detail": {}}
    try:
        from hibs_predictor.scrapers import fbref_client as fr

        t1 = time.perf_counter()
        squad = fr.fetch_squad_stats_table("EPL")
        fb_row["ms"] = _ms(t0)
        fb_row["ok"] = len(squad) > 3
        fb_row["detail"]["squad_rows"] = len(squad)
    except Exception as exc:
        fb_row["ms"] = _ms(t0)
        fb_row["error"] = str(exc)[:200]
    rows.append(fb_row)

    # --- Sofascore (search) ---
    t0 = time.perf_counter()
    ss_row: Dict[str, Any] = {"id": "sofascore", "kind": "undocumented_api", "ok": False, "ms": None, "detail": {}}
    try:
        from hibs_predictor.scrapers import sofascore_client as ss

        hit = ss.first_team_hit("Celtic")
        ss_row["ms"] = _ms(t0)
        ss_row["ok"] = bool(hit and hit.get("id"))
        ss_row["detail"]["team_id"] = (hit or {}).get("id")
    except Exception as exc:
        ss_row["ms"] = _ms(t0)
        ss_row["error"] = str(exc)[:200]
    rows.append(ss_row)

    # --- WhoScored (documentary) ---
    rows.append(
        {
            "id": "whoscored",
            "kind": "blocked",
            "ok": False,
            "ms": 0.0,
            "detail": {
                "reason": "No production integration — JS app, no public event API; see whoscored_client stub.",
            },
        }
    )

    # --- API-Football ---
    t0 = time.perf_counter()
    api_row: Dict[str, Any] = {"id": "api_football", "kind": "api", "ok": False, "ms": None, "detail": {}}
    key = os.getenv("API_SPORTS_FOOTBALL_KEY", "")
    if not key:
        api_row["detail"]["error"] = "API_SPORTS_FOOTBALL_KEY not set"
    else:
        try:
            r = requests.get(
                "https://v3.football.api-sports.io/timezone",
                headers={"x-apisports-key": key},
                timeout=18,
            )
            api_row["ms"] = _ms(t0)
            api_row["ok"] = r.status_code == 200
            api_row["detail"]["http"] = r.status_code
        except Exception as exc:
            api_row["ms"] = _ms(t0)
            api_row["error"] = str(exc)[:200]
    rows.append(api_row)

    out["sources"] = rows
    reliable = [r["id"] for r in rows if r.get("ok")]
    flaky = [r["id"] for r in rows if not r.get("ok") and r.get("kind") not in ("blocked",)]
    out["summary"] = {
        "reliable_now": reliable,
        "not_ok": [r["id"] for r in rows if not r.get("ok")],
        "integrate_recommended": [x for x in ("statsbomb_open", "api_football", "understat", "fbref") if x in reliable],
        "note": "Sofascore often returns 403 in server/datacenter environments; treat as optional.",
    }
    return out
