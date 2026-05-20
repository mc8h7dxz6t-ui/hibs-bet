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
        "id": "api_sports",
        "label": "API-Football/API-Sports",
        "focus": "Fixtures, standings, team stats, recent form, injuries, odds and selected fixture statistics",
        "status": "wired",
        "module": "hibs_predictor.api_clients.ApiSportsFootballClient",
        "notes": "Documented API-Football endpoints; standings try current then previous season for completed/thin windows.",
    },
    {
        "id": "football_data_org",
        "label": "Football-Data.org",
        "focus": "Documented fixtures and standings for supported competitions",
        "status": "wired",
        "module": "hibs_predictor.api_clients.FootballDataOrgClient",
        "notes": "Official v4 API; used for fixture fallback and league-table/position fallback, including previous-season tables when current fixture windows are thin.",
    },
    {
        "id": "fotmob",
        "label": "FotMob",
        "focus": "Public daily match JSON used as a conservative fixture fallback",
        "status": "experimental",
        "module": "hibs_predictor.scrapers.fotmob_client",
        "notes": "Unauthenticated but undocumented website JSON; cached, date-scoped, and only used after primary fixture providers return nothing. Not used for standings/xG until a stable public feed is verified.",
    },
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
        "notes": "Light + heavy modes via /getLeagueData AJAX (session cookie); limited league set; respect low request rate.",
    },
    {
        "id": "sofascore",
        "label": "Sofascore",
        "focus": "Live + historical team feeds, ratings-style summaries",
        "status": "wired",
        "module": "hibs_predictor.scrapers.sofascore_client",
        "notes": "Best-effort public JSON endpoints; often HTTP 403 off server/datacenter IPs — fail-soft, optional rolling xG.",
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
        "id": "uefa",
        "label": "UEFA",
        "focus": "Official UEFA competition pages / feeds for club and international tournaments",
        "status": "planned",
        "module": None,
        "notes": "No stable documented public API confirmed; current UEFA coverage comes through Football-Data.org/API-Football competition mappings.",
    },
    {
        "id": "footballdata_io",
        "label": "footballdata.io",
        "focus": "Potential fixture/stat feed distinct from football-data.org",
        "status": "planned",
        "module": None,
        "notes": "Not integrated until a documented endpoint, auth model, and terms are verified.",
    },
    {
        "id": "xgstat",
        "label": "xGStat",
        "focus": "xG/team-stat enrichment",
        "status": "planned",
        "module": None,
        "notes": "No stable documented public endpoint verified in this pass; keep as backlog rather than scrape brittle pages.",
    },
    {
        "id": "besoccer",
        "label": "BeSoccer",
        "focus": "Fixtures, tables, team/news pages",
        "status": "planned",
        "module": None,
        "notes": "Not wired without a documented/public feed; avoid invasive page scraping.",
    },
    {
        "id": "sports_bzzoiro",
        "label": "sports.bzzoiro.com",
        "focus": "Potential fixture/stat source",
        "status": "planned",
        "module": None,
        "notes": "Unknown stability/terms; metadata-only until source ownership and permitted usage are verified.",
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
        "focus": "League table standings when API positions are missing",
        "status": "wired",
        "module": "hibs_predictor.scrapers.soccerstats_standings",
        "notes": "HTML tables.asp fallback after Wikipedia/API; cached 12h per league.",
    },
    {
        "id": "datamb",
        "label": "DataMB",
        "focus": "Wide league coverage, visual-heavy metrics",
        "status": "planned",
        "module": None,
        "notes": "Chart-heavy sites are brittle for scrapers; prefer licensed feeds if available.",
    },
    {
        "id": "soccerdata",
        "label": "soccerdata (Python)",
        "focus": "Unified FBref / WhoScored / Understat → DataFrames",
        "status": "planned",
        "module": None,
        "notes": "Wrapper over same scrape targets as custom clients; evaluate only if HTML parsers break often — not a ToS upgrade.",
    },
    {
        "id": "worldfootballr",
        "label": "worldfootballR",
        "focus": "FBref deep stats via R (+ immature Python wrapper)",
        "status": "planned",
        "module": None,
        "notes": "R-first toolchain; poor fit for this Python app unless exposed as a sidecar service.",
    },
]


def sources_by_status(status: str) -> List[Dict[str, Any]]:
    """Return catalog rows matching status: wired | experimental | planned."""
    s = status.strip().lower()
    return [row for row in SOURCE_CATALOG if str(row.get("status", "")).lower() == s]
