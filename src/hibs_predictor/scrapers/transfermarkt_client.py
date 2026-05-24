"""Transfermarkt — probe-only (no production HTML scrape).

Structured HTML exists but site terms discourage automated extraction. Production squad
and injury context uses API-Football (``injuries``, ``players/squads``) instead.
"""

from __future__ import annotations

from typing import Any, Dict

import requests

_HEADERS = {
    "User-Agent": "hibs-bet/1.0 (metadata probe only; no bulk scrape)",
    "Accept-Language": "en",
}
ROBOTS_URL = "https://www.transfermarkt.com/robots.txt"
_PRODUCTION_NOTE = (
    "Probe-only (robots + ToS). Production path: API-Football injuries + players/squads "
    "(HIBS_ENABLE_API_SQUAD_DEPTH=1). Transfermarkt HTML parser deferred."
)


def probe_availability() -> Dict[str, Any]:
    """Check site reachability without parsing squad/injury pages."""
    try:
        r = requests.get(ROBOTS_URL, headers=_HEADERS, timeout=12)
        ok = r.status_code == 200 and "User-agent" in (r.text or "")
        return {
            "ok": ok,
            "status": "deferred",
            "note": _PRODUCTION_NOTE,
            "robots_http": r.status_code,
            "production_alternative": "api_football_injuries_squads",
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "deferred",
            "note": _PRODUCTION_NOTE,
            "error": str(exc)[:160],
            "production_alternative": "api_football_injuries_squads",
        }
