"""xGStat.com — probe-only stub (no stable public JSON API found).

xG gaps are covered by Understat, FotMob league-table xG, API-Football fixture xG,
and recent-match statistics when FBref is blocked on VPS.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import requests

_HEADERS = {"User-Agent": "hibs-bet/1.0 (endpoint probe only)"}
_CANDIDATE_URLS: Tuple[str, ...] = (
    "https://xgstat.com/",
    "https://www.xgstat.com/",
    "https://www.xgstat.com/api/leagues",
    "https://xgstat.com/api/leagues",
    "https://www.xgstat.com/api/v1/leagues",
)
_NOTE = (
    "No documented public JSON feed — backlog only. xG chain: API fixture xG → Understat → "
    "FotMob → recent-match xG / goals_proxy (see xg_priority_chain)."
)


def probe_public_api() -> Dict[str, Any]:
    """Return whether any candidate URL responds with JSON (none wired yet)."""
    probes: List[Dict[str, Any]] = []
    for url in _CANDIDATE_URLS:
        try:
            r = requests.get(url, headers=_HEADERS, timeout=10)
            ctype = (r.headers.get("content-type") or "").lower()
            probes.append({"url": url, "http": r.status_code, "content_type": ctype[:60]})
            if r.status_code == 200 and "json" in ctype:
                return {
                    "ok": True,
                    "url": url,
                    "status": "json_found_not_wired",
                    "note": _NOTE,
                    "probes": probes,
                }
        except Exception as exc:
            probes.append({"url": url, "error": str(exc)[:80]})
    return {
        "ok": False,
        "status": "deferred",
        "note": _NOTE,
        "probes": probes,
        "production_alternative": "understat_fotmob_api_xg",
    }
