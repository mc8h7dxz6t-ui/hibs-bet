"""Catalog of public / scrape-style football data sources (planning + honesty).

Many sites below prohibit or discourage bulk scraping in their terms of use.
Anything marked ``wired`` is already used (best-effort, rate-limited) from
``collect_supplemental`` or related modules. ``experimental`` may exist only as
a stub or optional Playwright probe. ``planned`` is not implemented — treat as
product backlog, not a promise of extraction quality.
"""

from __future__ import annotations

from typing import Any, Dict, List

# Keys: id (stable), label, focus (one line), status, module (optional), notes
SOURCE_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "fbref",
        "label": "FBref",
        "focus": "Deep squad tables, advanced metrics, Opta-backed stats on many leagues",
        "status": "wired",
        "module": "hibs_predictor.scrapers.fbref_client",
        "notes": "HTML tables; follow Sports Reference robots; heavy path in collect_supplemental.",
    },
    {
        "id": "understat",
        "label": "Understat",
        "focus": "Shot-level xG and league JSON embedded in public pages",
        "status": "wired",
        "module": "hibs_predictor.scrapers.understat_client",
        "notes": "Light + heavy modes; limited league set; respect low request rate.",
    },
    {
        "id": "sofascore",
        "label": "Sofascore",
        "focus": "Live + historical team feeds, ratings-style summaries",
        "status": "wired",
        "module": "hibs_predictor.scrapers.sofascore_client",
        "notes": "Best-effort public JSON endpoints; shape changes — fail-soft in supplemental.",
    },
    {
        "id": "wikipedia",
        "label": "Wikipedia",
        "focus": "Season league tables / standings text for supported codes",
        "status": "wired",
        "module": "hibs_predictor.scrapers.wikipedia_standings",
        "notes": "MediaWiki API; used when API standings thin out.",
    },
    {
        "id": "statsbomb_open",
        "label": "StatsBomb Open Data",
        "focus": "Free competition + match JSON (goals proxy, not full xG pipeline)",
        "status": "wired",
        "module": "hibs_predictor.scrapers.statsbomb_open",
        "notes": "Opt-in via HIBS_ENABLE_STATSBOMB_OPEN_MATCHES; policy window gated.",
    },
    {
        "id": "whoscored",
        "label": "WhoScored",
        "focus": "Rich match analytics, event streams, ratings (mostly behind JS)",
        "status": "experimental",
        "module": "hibs_predictor.scrapers.whoscored_client",
        "notes": "Optional Playwright fetch test only; no production feature pipeline — ToS + stability.",
    },
    {
        "id": "transfermarkt",
        "label": "Transfermarkt",
        "focus": "Transfers, market values, injuries, squad depth",
        "status": "planned",
        "module": None,
        "notes": "Structured HTML but strict robots; needs dedicated parser + legal review before use.",
    },
    {
        "id": "footystats",
        "label": "FootyStats",
        "focus": "League/team totals, O/U, corners, clean sheets style aggregates",
        "status": "planned",
        "module": None,
        "notes": "Often paginated + login walls; evaluate official export/API if any.",
    },
    {
        "id": "soccerstats",
        "label": "SoccerStats",
        "focus": "League trends, goal timing, H2H-style tables",
        "status": "planned",
        "module": None,
        "notes": "Simple HTML layout (easier to parse) but still check robots/ToS.",
    },
    {
        "id": "datamb",
        "label": "DataMB",
        "focus": "Wide league coverage, visual-heavy metrics",
        "status": "planned",
        "module": None,
        "notes": "Chart-heavy sites are brittle for scrapers; prefer licensed feeds if available.",
    },
]


def sources_by_status(status: str) -> List[Dict[str, Any]]:
    """Return catalog rows matching status: wired | experimental | planned."""
    s = status.strip().lower()
    return [row for row in SOURCE_CATALOG if str(row.get("status", "")).lower() == s]
