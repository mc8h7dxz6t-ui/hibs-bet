"""Shared scraper health classification for /api/health and probes."""

from __future__ import annotations

from typing import Any, Dict, Optional


def http_status_from_exc(exc: BaseException) -> Optional[int]:
    resp = getattr(exc, "response", None)
    if resp is not None:
        try:
            return int(resp.status_code)
        except (TypeError, ValueError, AttributeError):
            return None
    return None


def scraper_error_code(
    *,
    ok: bool,
    blocked: bool = False,
    http_status: Optional[int] = None,
    deferred: bool = False,
    layout_broken: bool = False,
) -> Optional[str]:
    """Map probe outcome to dashboard severity: green ok, amber BLOCKED/DEFERRED, red ERROR/LAYOUT_BROKEN."""
    if ok:
        return None
    if deferred:
        return "DEFERRED"
    if blocked or http_status in (403, 429, 451):
        return "BLOCKED"
    if http_status is not None:
        return "ERROR"
    if layout_broken:
        return "LAYOUT_BROKEN"
    return "ERROR"


def scraper_row(
    *,
    sid: str,
    label: str,
    ms: Optional[float],
    ok: bool,
    error: Optional[str] = None,
    blocked: bool = False,
    http_status: Optional[int] = None,
    deferred: bool = False,
    layout_broken: bool = False,
) -> Dict[str, Any]:
    code = scraper_error_code(
        ok=ok,
        blocked=blocked,
        http_status=http_status,
        deferred=deferred,
        layout_broken=layout_broken,
    )
    return {
        "id": sid,
        "label": label,
        "ms": ms,
        "ok": ok,
        "error_code": code,
        "error": error,
    }
