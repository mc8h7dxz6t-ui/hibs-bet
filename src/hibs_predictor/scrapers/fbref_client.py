"""FBref squad tables — HTML fetch + parse (follow robots.txt; cache aggressively)."""

from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from hibs_predictor.cache import Cache

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": "https://fbref.com/",
}

# fbref /en/comps/{id}/{season}/ — season like 2024-2025
FBREF_LEAGUE = {
    "EPL": ("9", "Premier-League"),
    "LA_LIGA": ("12", "La-Liga"),
    "SERIE_A": ("11", "Serie-A"),
    "BUNDESLIGA": ("20", "Bundesliga"),
    "LIGUE_1": ("13", "Ligue-1"),
}


class FbrefFetchError(Exception):
    """Non-OK FBref HTTP response (403/429 common from datacenter IPs)."""

    def __init__(self, message: str, *, blocked: bool = False, http_status: Optional[int] = None):
        super().__init__(message)
        self.blocked = blocked
        self.http_status = http_status


def fbref_blocked_env() -> bool:
    """When set, skip all FBref HTML fetches (typical on VPS/datacenter IPs that get 403)."""
    return (os.getenv("HIBS_FBREF_BLOCKED") or "").strip().lower() in ("1", "true", "yes", "on")


def _http_get(url: str, *, timeout: int = 30) -> requests.Response:
    try:
        from curl_cffi import requests as curl_requests  # type: ignore

        session = curl_requests.Session(impersonate="chrome120")
        return session.get(url, headers=_HEADERS, timeout=timeout)
    except ImportError:
        return requests.get(url, headers=_HEADERS, timeout=timeout)


def fetch_fbref_html(
    url: str,
    *,
    cache_key: Optional[str] = None,
    cache: Optional[Cache] = None,
    ttl_hours: float = 12.0,
) -> str:
    """Fetch one FBref HTML page with cache, browser-like headers, and one 429 retry."""
    if fbref_blocked_env():
        raise FbrefFetchError("HIBS_FBREF_BLOCKED=1 — FBref HTML skipped on this host", blocked=True)

    c = cache or Cache()
    if cache_key:
        hit = c.get(cache_key, ttl_hours=ttl_hours)
        if isinstance(hit, str) and hit.strip():
            return hit

    for attempt in range(2):
        r = _http_get(url)
        if r.status_code == 403:
            raise FbrefFetchError(
                "HTTP 403 — FBref blocked from this network (optional; core 1X2 unaffected)",
                blocked=True,
                http_status=403,
            )
        if r.status_code == 429 and attempt == 0:
            time.sleep(2.0)
            continue
        try:
            r.raise_for_status()
        except requests.HTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            raise FbrefFetchError(str(exc)[:160], blocked=status in (403, 451), http_status=status) from exc
        html = r.text or ""
        if cache_key and html.strip():
            c.set(cache_key, html, ttl_hours=ttl_hours)
        return html
    raise FbrefFetchError("HTTP 429 — FBref rate limited", http_status=429)


def _season_labels(league_code: str, season_label: Optional[str]) -> List[str]:
    if season_label:
        return [season_label]
    from hibs_predictor.season import fbref_season_labels

    return fbref_season_labels(league_code)


def _squad_stats_url(comp_id: str, comp_slug: str, season_label: str) -> str:
    sl = season_label
    return f"https://fbref.com/en/comps/{comp_id}/{sl}/{sl}-Stats-{comp_slug}-Stats"


def fetch_squad_stats_table(league_code: str, season_label: Optional[str] = None) -> List[Dict[str, Any]]:
    meta = FBREF_LEAGUE.get(league_code)
    if not meta:
        return []
    comp_id, comp_slug = meta
    cache = Cache()
    last_exc: Optional[Exception] = None
    for sl in _season_labels(league_code, season_label):
        url = _squad_stats_url(comp_id, comp_slug, sl)
        cache_key = f"fbref_squad_{league_code}_{sl}"
        try:
            html = fetch_fbref_html(url, cache_key=cache_key, cache=cache, ttl_hours=12.0)
            rows = _parse_squad_table(html)
            if rows:
                return rows
        except Exception as exc:
            last_exc = exc
            continue
    if last_exc:
        raise last_exc
    return []


def _parse_squad_table(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id=re.compile(r"stats_squads_standard_for"))
    if not table:
        table = soup.find("table", attrs={"class": re.compile(r"stats_table")})
    if not table:
        return []
    rows_out: List[Dict[str, Any]] = []
    thead = table.find("thead")
    if thead:
        for th in thead.find_all("th"):
            th.get("data-stat") or th.get_text(strip=True)
    tbody = table.find("tbody")
    if not tbody:
        return []
    for tr in tbody.find_all("tr"):
        if "partial_table" in tr.get("class", []):
            continue
        cells = {}
        for td in tr.find_all(["th", "td"]):
            stat = td.get("data-stat")
            if not stat:
                continue
            cells[stat] = td.get_text(strip=True)
        squad = cells.get("squad") or cells.get("team")
        if squad:
            rows_out.append({"squad": squad, "cells": cells})
    return rows_out


def squad_row_for_team(rows: List[Dict[str, Any]], team_name: str) -> Optional[Dict[str, Any]]:
    t = (team_name or "").lower()
    for row in rows:
        s = (row.get("squad") or "").lower()
        if t in s or s in t:
            return row
    return None


def probe_squad_table(league_code: str = "EPL") -> Dict[str, Any]:
    """Health/reliability probe — never raises; surfaces 403 as blocked."""
    if fbref_blocked_env():
        return {
            "ok": False,
            "blocked": True,
            "skipped_env": True,
            "http_status": None,
            "squad_rows": 0,
            "error": "HIBS_FBREF_BLOCKED=1 — FBref HTML skipped on this host (optional)",
        }
    try:
        rows = fetch_squad_stats_table(league_code)
        ok = len(rows) >= 5
        return {
            "ok": ok,
            "blocked": False,
            "squad_rows": len(rows),
            "error": None if ok else f"squad_rows={len(rows)}",
        }
    except FbrefFetchError as exc:
        return {
            "ok": False,
            "blocked": exc.blocked,
            "http_status": exc.http_status,
            "squad_rows": 0,
            "error": str(exc)[:160],
        }
    except Exception as exc:
        return {
            "ok": False,
            "blocked": False,
            "http_status": None,
            "squad_rows": 0,
            "error": str(exc)[:160],
        }
