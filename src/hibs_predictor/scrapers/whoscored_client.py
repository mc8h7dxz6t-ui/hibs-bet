"""WhoScored (whoscored.com) — pages are JavaScript-heavy.

Advanced per-match *event* data (xThreat-style feeds, full event streams) is not
available here: it is proprietary, not exposed as a stable public API, and bulk
scraping conflicts with typical site terms. This project uses **API-Football**
for fixtures, finished-match results, standings form strings, and injuries.

Uses Playwright only for optional page fetch experiments when installed; there is
no production pipeline from WhoScored into model features. Respect WhoScored ToS
and rate limits if you extend this module.
"""

from typing import Any, Dict, Optional


def fetch_match_summary_table(url: str) -> Dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "reason": "playwright_not_installed", "hint": "pip install playwright && playwright install chromium"}

    out: Dict[str, Any] = {"ok": False, "url": url, "rows": []}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=45000)
            html = page.content()
            browser.close()
        out["ok"] = True
        out["html_length"] = len(html)
        # Structured extraction would target their React tables; keep raw size as proof of fetch.
        return out
    except Exception as exc:
        out["reason"] = str(exc)
        return out
