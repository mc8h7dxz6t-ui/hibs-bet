"""Transfermarkt — deferred light adapter (no production scrape yet).

Structured HTML is available but robots/ToS are strict. This module exposes an
honest health probe and placeholder hooks until a reviewed parser exists.
"""

from __future__ import annotations

from typing import Any, Dict

import requests

_HEADERS = {
    "User-Agent": "hibs-bet/1.0 (metadata probe only; no bulk scrape)",
    "Accept-Language": "en",
}
ROBOTS_URL = "https://www.transfermarkt.com/robots.txt"


def probe_availability() -> Dict[str, Any]:
    """Check site reachability without parsing squad/injury pages."""
    try:
        r = requests.get(ROBOTS_URL, headers=_HEADERS, timeout=12)
        ok = r.status_code == 200 and "User-agent" in (r.text or "")
        return {
            "ok": ok,
            "status": "deferred",
            "note": "No squad/injury parser wired — use API-Football injuries until reviewed.",
            "robots_http": r.status_code,
        }
    except Exception as exc:
        return {"ok": False, "status": "deferred", "error": str(exc)[:160]}
