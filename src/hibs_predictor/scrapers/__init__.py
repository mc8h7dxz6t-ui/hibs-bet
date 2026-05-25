"""Supplemental data sources (open APIs + rate-limited public pages).

See ``source_registry.SOURCE_CATALOG`` for FBref, Understat, SofaScore,
StatsBomb open, WhoScored (experimental), and planned sites (Transfermarkt,
FootyStats, SoccerStats, DataMB) with ToS / implementation notes.
"""

from hibs_predictor.scrapers.supplemental import collect_supplemental
from hibs_predictor.scrapers.source_registry import SOURCE_CATALOG, sources_by_status
from hibs_predictor.scrapers.scraper_six import SCRAPER_SIX, annotate_scraper_six, scraper_six_plan_summary

__all__ = [
    "collect_supplemental",
    "SOURCE_CATALOG",
    "sources_by_status",
    "SCRAPER_SIX",
    "annotate_scraper_six",
    "scraper_six_plan_summary",
]
