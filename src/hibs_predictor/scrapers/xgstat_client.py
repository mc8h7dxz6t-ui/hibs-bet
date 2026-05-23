"""xGStat.com — probe-only stub (no stable public JSON API found)."""

from __future__ import annotations

from typing import Any, Dict

import requests

_HEADERS = {"User-Agent": "hibs-bet/1.0 (endpoint probe only)"}
_CANDIDATE_URLS = (
    "https://xgstat.com/",
    "https://www.xgstat.com/api/leagues",
)


def probe_public_api() -> Dict[str, Any]:
    """Return whether any candidate URL responds with JSON (none wired yet)."""
    for url in _CANDIDATE_URLS:
        try:
            r = requests.get(url, headers=_HEADERS, timeout=10)
            ctype = (r.headers.get("content-type") or "").lower()
            if r.status_code == 200 and "json" in ctype:
                return {"ok": True, "url": url, "status": "json_found_not_wired"}
        except Exception:
            continue
    return {
        "ok": False,
        "status": "deferred",
        "note": "No documented public JSON feed — backlog only (probe checks site HTML).",
    }
