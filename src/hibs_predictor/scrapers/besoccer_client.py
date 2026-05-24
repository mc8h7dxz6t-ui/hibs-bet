"""BeSoccer — probe-only stub (no documented public API).

Site HTML is reachable; internal JSON endpoints are undocumented and often geo-gated.
Standings/context fallbacks: SoccerStats, API-Football, FotMob league xG.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import requests

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html;q=0.9",
}
_CANDIDATE_URLS: Tuple[Tuple[str, str], ...] = (
    ("root", "https://www.besoccer.com/"),
    ("besoccerApi", "https://www.besoccer.com/besoccerApi/team/home?id=2016"),
)
_NOTE = (
    "No stable documented JSON API — not wired. Alternatives: API-Football stats/injuries, "
    "SoccerStats tables, FotMob xG where mapped."
)


def probe_public_api() -> Dict[str, Any]:
    """HEAD/GET on site + best-effort internal API paths; production parser not implemented."""
    results: List[Dict[str, Any]] = []
    json_hit = False
    for label, url in _CANDIDATE_URLS:
        try:
            r = requests.get(url, headers=_HEADERS, timeout=12)
            ctype = (r.headers.get("content-type") or "").lower()
            entry: Dict[str, Any] = {"path": label, "http": r.status_code, "content_type": ctype[:60]}
            if r.status_code == 200 and "json" in ctype:
                json_hit = True
                entry["json"] = True
            results.append(entry)
        except Exception as exc:
            results.append({"path": label, "error": str(exc)[:80]})
    root_ok = any(x.get("path") == "root" and x.get("http") == 200 for x in results)
    return {
        "ok": root_ok and not json_hit,
        "status": "deferred",
        "note": _NOTE,
        "probes": results,
        "production_alternative": "api_football_soccerstats_fotmob",
    }
