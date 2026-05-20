"""BeSoccer — probe-only stub (no documented public API)."""

from __future__ import annotations

from typing import Any, Dict

import requests

_HEADERS = {"User-Agent": "hibs-bet/1.0 (endpoint probe only)"}


def probe_public_api() -> Dict[str, Any]:
    """Best-effort HEAD/GET on site root; production parser not implemented."""
    try:
        r = requests.get("https://www.besoccer.com/", headers=_HEADERS, timeout=12)
        ok = r.status_code == 200
        return {
            "ok": ok,
            "status": "deferred",
            "note": "Site reachable but no stable public JSON API — not wired.",
            "http": r.status_code,
        }
    except Exception as exc:
        return {"ok": False, "status": "deferred", "error": str(exc)[:160]}
