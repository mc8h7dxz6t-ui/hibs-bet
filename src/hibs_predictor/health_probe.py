"""Lightweight latency and scraper-shape probes for the dashboard health panel."""

import json
import os
import time
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv

from hibs_predictor.data_aggregator import _env_first_usable
from hibs_predictor.scrapers.statsbomb_open import OPEN_BASE


def _ms_since(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


def cache_disk_summary() -> Dict[str, Any]:
    """Summarise on-disk JSON cache (TTL metadata + size) for /api/health — no writes."""
    try:
        from hibs_predictor.cache import Cache

        c = Cache()
        root = c.cache_dir
        n_files = 0
        bytes_total = 0
        with_ttl = 0
        if root.exists():
            for path in root.glob("*.json"):
                try:
                    bytes_total += path.stat().st_size
                    n_files += 1
                    with open(path, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    if isinstance(data, dict) and data.get("ttl_hours") is not None:
                        with_ttl += 1
                except (OSError, json.JSONDecodeError, TypeError, ValueError):
                    continue
        return {
            "cache_dir": str(root.resolve()),
            "files": n_files,
            "bytes_approx": bytes_total,
            "entries_with_ttl_metadata": with_ttl,
            "ttl_note": "Entries written via Cache.set store cached_at + ttl_hours; prune_stale() removes expired JSON.",
        }
    except Exception as exc:
        return {
            "cache_dir": ".cache",
            "files": 0,
            "bytes_approx": 0,
            "entries_with_ttl_metadata": 0,
            "error": str(exc)[:160],
        }


def gather_health() -> Dict[str, Any]:
    """Return API latencies and scraper status for /api/health (best-effort, no crash)."""
    load_dotenv()
    apis: List[Dict[str, Any]] = []
    scrapers: List[Dict[str, Any]] = []

    # --- API-Football (timezone is small + requires key; same env resolution as DataAggregator) ---
    key = _env_first_usable("API_SPORTS_FOOTBALL_KEY", "API_SPORTS_KEY", "APISPORTS_KEY")
    t0 = time.perf_counter()
    if key:
        try:
            r = requests.get(
                "https://v3.football.api-sports.io/timezone",
                headers={"x-apisports-key": key},
                timeout=15,
            )
            ms = _ms_since(t0)
            ok = r.status_code == 200
            apis.append(
                {
                    "id": "api_football",
                    "label": "API-Football",
                    "ms": ms,
                    "ok": ok,
                    "error": None if ok else f"HTTP {r.status_code}",
                }
            )
        except Exception as exc:
            apis.append(
                {
                    "id": "api_football",
                    "label": "API-Football",
                    "ms": None,
                    "ok": False,
                    "error": str(exc)[:160],
                }
            )
    else:
        apis.append(
            {
                "id": "api_football",
                "label": "API-Football",
                "ms": None,
                "ok": False,
                "error": "API_SPORTS_FOOTBALL_KEY / API_SPORTS_KEY / APISPORTS_KEY not set",
            }
        )

    # --- Football-Data.org (same aliases as DataAggregator) ---
    fdo = _env_first_usable("FOOTBALL_DATA_ORG_KEY", "FOOTBALL_DATA_KEY")
    t0 = time.perf_counter()
    if fdo:
        try:
            r = requests.get(
                "https://api.football-data.org/v4/competitions",
                headers={"X-Auth-Token": fdo},
                timeout=15,
            )
            ms = _ms_since(t0)
            ok = r.status_code == 200
            apis.append(
                {
                    "id": "football_data_org",
                    "label": "Football-Data.org",
                    "ms": ms,
                    "ok": ok,
                    "error": None if ok else f"HTTP {r.status_code}",
                }
            )
        except Exception as exc:
            apis.append(
                {
                    "id": "football_data_org",
                    "label": "Football-Data.org",
                    "ms": None,
                    "ok": False,
                    "error": str(exc)[:160],
                }
            )
    else:
        apis.append(
            {
                "id": "football_data_org",
                "label": "Football-Data.org",
                "ms": None,
                "ok": False,
                "error": "not configured",
            }
        )

    # --- The Odds API ---
    odds_key = os.getenv("ODDS_API_KEY", "")
    t0 = time.perf_counter()
    if odds_key:
        try:
            r = requests.get(
                "https://api.the-odds-api.com/v4/sports/",
                params={"apiKey": odds_key},
                timeout=15,
            )
            ms = _ms_since(t0)
            ok = r.status_code == 200
            apis.append(
                {
                    "id": "odds_api",
                    "label": "The Odds API",
                    "ms": ms,
                    "ok": ok,
                    "error": None if ok else f"HTTP {r.status_code}",
                }
            )
        except Exception as exc:
            apis.append(
                {
                    "id": "odds_api",
                    "label": "The Odds API",
                    "ms": None,
                    "ok": False,
                    "error": str(exc)[:160],
                }
            )
    else:
        apis.append(
            {
                "id": "odds_api",
                "label": "The Odds API",
                "ms": None,
                "ok": False,
                "error": "not configured",
            }
        )

    # --- StatsBomb open-data (GitHub raw) ---
    t0 = time.perf_counter()
    try:
        r = requests.get(f"{OPEN_BASE}/competitions.json", timeout=20)
        ms = _ms_since(t0)
        ok = r.status_code == 200
        data = r.json() if ok and r.content else []
        n = len(data) if isinstance(data, list) else 0
        if ok and n > 0:
            err_c = None
            err_t = None
            ok_flag = True
        elif ok:
            err_c = "LAYOUT_BROKEN"
            err_t = "Empty or invalid competitions payload"
            ok_flag = False
        else:
            err_c = "ERROR"
            err_t = f"HTTP {r.status_code}"
            ok_flag = False
        scrapers.append(
            {
                "id": "statsbomb_open",
                "label": "StatsBomb (open)",
                "ms": ms,
                "ok": ok_flag,
                "error_code": err_c,
                "error": err_t,
            }
        )
    except Exception as exc:
        msg = str(exc)
        code = "LAYOUT_BROKEN" if "LAYOUT_BROKEN" in msg.upper() else "ERROR"
        scrapers.append(
            {
                "id": "statsbomb_open",
                "label": "StatsBomb (open)",
                "ms": None,
                "ok": False,
                "error_code": code,
                "error": msg[:160],
            }
        )

    # --- Understat (AJAX league data; try current + previous season) ---
    t0 = time.perf_counter()
    try:
        from datetime import date

        from hibs_predictor.scrapers.understat_client import fetch_league_matches

        rows: List[Dict[str, Any]] = []
        for y in (date.today().year, date.today().year - 1):
            rows = fetch_league_matches("EPL", y)
            if len(rows) > 20:
                break
        ms = _ms_since(t0)
        ok = len(rows) > 20
        scrapers.append(
            {
                "id": "understat",
                "label": "Understat",
                "ms": ms,
                "ok": ok,
                "error_code": None if ok else "LAYOUT_BROKEN",
                "error": None if ok else f"League AJAX returned {len(rows)} rows (expected 20+)",
            }
        )
    except Exception as exc:
        msg = str(exc)
        code = "LAYOUT_BROKEN" if "LAYOUT_BROKEN" in msg.upper() else "ERROR"
        scrapers.append(
            {
                "id": "understat",
                "label": "Understat",
                "ms": _ms_since(t0),
                "ok": False,
                "error_code": code,
                "error": msg[:160],
            }
        )

    # --- Sofascore public search (light; often 403 off residential IP too) ---
    t0 = time.perf_counter()
    try:
        from hibs_predictor.scrapers import sofascore_client as ss

        hit, blocked = ss.probe_team_search("Arsenal")
        ms = _ms_since(t0)
        if hit:
            scrapers.append(
                {
                    "id": "sofascore",
                    "label": "Sofascore",
                    "ms": ms,
                    "ok": True,
                    "error_code": None,
                    "error": None,
                }
            )
        elif blocked:
            scrapers.append(
                {
                    "id": "sofascore",
                    "label": "Sofascore",
                    "ms": ms,
                    "ok": False,
                    "error_code": "BLOCKED",
                    "error": "HTTP 403 — API blocked from this network (optional; core 1X2 unaffected)",
                }
            )
        else:
            scrapers.append(
                {
                    "id": "sofascore",
                    "label": "Sofascore",
                    "ms": ms,
                    "ok": False,
                    "error_code": "ERROR",
                    "error": "empty search result",
                }
            )
    except Exception as exc:
        msg = str(exc)
        code = "LAYOUT_BROKEN" if "LAYOUT_BROKEN" in msg.upper() else "ERROR"
        scrapers.append(
            {
                "id": "sofascore",
                "label": "Sofascore",
                "ms": _ms_since(t0),
                "ok": False,
                "error_code": code,
                "error": msg[:160],
            }
        )

    # --- FotMob daily matches (date + timezone) ---
    t0 = time.perf_counter()
    try:
        from hibs_predictor.scrapers.fotmob_client import probe_matches_api

        pr = probe_matches_api()
        ms = _ms_since(t0)
        ok = bool(pr.get("ok"))
        scrapers.append(
            {
                "id": "fotmob",
                "label": "FotMob",
                "ms": ms,
                "ok": ok,
                "error_code": None if ok else "LAYOUT_BROKEN",
                "error": None if ok else pr.get("error") or f"leagues={pr.get('league_count', 0)}",
            }
        )
    except Exception as exc:
        scrapers.append(
            {
                "id": "fotmob",
                "label": "FotMob",
                "ms": _ms_since(t0),
                "ok": False,
                "error_code": "ERROR",
                "error": str(exc)[:160],
            }
        )

    # --- Wikipedia standings (EPL table sample) ---
    t0 = time.perf_counter()
    try:
        from hibs_predictor.scrapers.wikipedia_standings import fetch_league_table

        rows = fetch_league_table("EPL")
        ms = _ms_since(t0)
        ok = len(rows) >= 10
        scrapers.append(
            {
                "id": "wikipedia",
                "label": "Wikipedia",
                "ms": ms,
                "ok": ok,
                "error_code": None if ok else "LAYOUT_BROKEN",
                "error": None if ok else f"rows={len(rows)}",
            }
        )
    except Exception as exc:
        scrapers.append(
            {
                "id": "wikipedia",
                "label": "Wikipedia",
                "ms": _ms_since(t0),
                "ok": False,
                "error_code": "ERROR",
                "error": str(exc)[:160],
            }
        )

    # --- SoccerStats latest.asp ---
    t0 = time.perf_counter()
    try:
        from hibs_predictor.scrapers.soccerstats_standings import fetch_league_table

        rows = fetch_league_table("EPL")
        ms = _ms_since(t0)
        ok = len(rows) >= 10
        scrapers.append(
            {
                "id": "soccerstats",
                "label": "SoccerStats",
                "ms": ms,
                "ok": ok,
                "error_code": None if ok else "LAYOUT_BROKEN",
                "error": None if ok else f"rows={len(rows)}",
            }
        )
    except Exception as exc:
        scrapers.append(
            {
                "id": "soccerstats",
                "label": "SoccerStats",
                "ms": _ms_since(t0),
                "ok": False,
                "error_code": "ERROR",
                "error": str(exc)[:160],
            }
        )

    # --- Deferred / probe-only sources ---
    for sid, label, mod_path, fn in (
        ("transfermarkt", "Transfermarkt", "hibs_predictor.scrapers.transfermarkt_client", "probe_availability"),
        ("xgstat", "xGStat", "hibs_predictor.scrapers.xgstat_client", "probe_public_api"),
        ("besoccer", "BeSoccer", "hibs_predictor.scrapers.besoccer_client", "probe_public_api"),
    ):
        t0 = time.perf_counter()
        try:
            import importlib

            mod = importlib.import_module(mod_path)
            pr = getattr(mod, fn)()
            ms = _ms_since(t0)
            deferred = str(pr.get("status") or "") == "deferred" or str(pr.get("status") or "") == "not_available"
            scrapers.append(
                {
                    "id": sid,
                    "label": label,
                    "ms": ms,
                    "ok": bool(pr.get("ok")) if not deferred else False,
                    "error_code": "DEFERRED" if deferred else (None if pr.get("ok") else "ERROR"),
                    "error": pr.get("note") or pr.get("error"),
                }
            )
        except Exception as exc:
            scrapers.append(
                {
                    "id": sid,
                    "label": label,
                    "ms": _ms_since(t0),
                    "ok": False,
                    "error_code": "ERROR",
                    "error": str(exc)[:160],
                }
            )

    return {
        "apis": apis,
        "scrapers": scrapers,
        "latency_ok_ms": 200,
        "cache_disk": cache_disk_summary(),
    }
