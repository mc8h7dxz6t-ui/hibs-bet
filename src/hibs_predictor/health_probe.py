"""Lightweight latency and scraper-shape probes for the dashboard health panel."""

import os
import time
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv

from hibs_predictor.scrapers.statsbomb_open import OPEN_BASE


def _ms_since(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


def gather_health() -> Dict[str, Any]:
    """Return API latencies and scraper status for /api/health (best-effort, no crash)."""
    load_dotenv()
    apis: List[Dict[str, Any]] = []
    scrapers: List[Dict[str, Any]] = []

    # --- API-Football (timezone is small + requires key) ---
    key = os.getenv("API_SPORTS_FOOTBALL_KEY", "")
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
                "error": "API_SPORTS_FOOTBALL_KEY not set",
            }
        )

    # --- Football-Data.org ---
    fdo = os.getenv("FOOTBALL_DATA_ORG_KEY", "")
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

    # --- Understat (optional: detect HTML without embedded JSON) ---
    t0 = time.perf_counter()
    try:
        from hibs_predictor.scrapers.understat_client import _extract_json_array

        headers = {"User-Agent": "hibs-bet/1.0 (health probe)"}
        r = requests.get("https://understat.com/league/EPL/2025", headers=headers, timeout=18)
        ms = _ms_since(t0)
        if r.status_code != 200:
            scrapers.append(
                {
                    "id": "understat",
                    "label": "Understat",
                    "ms": ms,
                    "ok": False,
                    "error_code": "ERROR",
                    "error": f"HTTP {r.status_code}",
                }
            )
        else:
            parsed = _extract_json_array(r.text)
            if parsed is None and len(r.text) > 5000:
                scrapers.append(
                    {
                        "id": "understat",
                        "label": "Understat",
                        "ms": ms,
                        "ok": False,
                        "error_code": "LAYOUT_BROKEN",
                        "error": "No embedded matches JSON (page layout may have changed)",
                    }
                )
            else:
                scrapers.append(
                    {
                        "id": "understat",
                        "label": "Understat",
                        "ms": ms,
                        "ok": True,
                        "error_code": None,
                        "error": None,
                    }
                )
    except Exception as exc:
        msg = str(exc)
        code = "LAYOUT_BROKEN" if "LAYOUT_BROKEN" in msg.upper() else "ERROR"
        scrapers.append(
            {
                "id": "understat",
                "label": "Understat",
                "ms": None,
                "ok": False,
                "error_code": code,
                "error": msg[:160],
            }
        )

    # --- Sofascore public search (light) ---
    t0 = time.perf_counter()
    try:
        from hibs_predictor.scrapers import sofascore_client as ss

        hit = ss.first_team_hit("Arsenal")
        ms = _ms_since(t0)
        scrapers.append(
            {
                "id": "sofascore",
                "label": "Sofascore",
                "ms": ms,
                "ok": bool(hit),
                "error_code": None if hit else "ERROR",
                "error": None if hit else "empty search result",
            }
        )
    except Exception as exc:
        msg = str(exc)
        code = "LAYOUT_BROKEN" if "LAYOUT_BROKEN" in msg.upper() else "ERROR"
        scrapers.append(
            {
                "id": "sofascore",
                "label": "Sofascore",
                "ms": None,
                "ok": False,
                "error_code": code,
                "error": msg[:160],
            }
        )

    return {"apis": apis, "scrapers": scrapers, "latency_ok_ms": 200}
