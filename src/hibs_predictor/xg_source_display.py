"""Human-readable xG source labels and confidence tiers for dashboard UI."""

from __future__ import annotations

from typing import Any, Dict, Optional

from hibs_predictor.historic_calibration import xg_quality_tier


_LABELS: Dict[str, str] = {
    "api_fixture_xg": "API match xG (both teams)",
    "stats_api_xg": "Stats API match xG",
    "understat_xg": "Understat match xG",
    "understat_team_xg": "Understat team rolling xG",
    "fotmob_league_xg": "FotMob season table (team attack vs opponent defence)",
    "scraped_recent_xg": "Recent finished matches with API xG stats",
    "api_season_team_xg": "API season goals profile (attack vs defence blend)",
    "sofascore_xg": "SofaScore team xG averages",
    "fbref_schedule_xg": "FBref schedule xG",
    "scottish_fbref_xg": "FBref Scottish schedule xG",
    "fbref_schedule_avg_xg": "FBref schedule team averages",
    "scottish_fbref_avg_xg": "FBref Scottish team averages",
    "statsbomb_goals_proxy_xg": "StatsBomb open data goals proxy (not measured xG)",
    "form_derived_xg": "Recent goals only (re-labelled; treat as estimate)",
    "partial_scraped_xg": "Mixed: one side from scrape, other from model",
    "mixed_api_goals_proxy": "Part API xG, part goals estimate",
    "goals_proxy": "Goals-only estimate (no measured xG for this fixture)",
    "unknown": "xG source unknown",
}


_HINTS: Dict[str, str] = {
    "api_fixture_xg": "Measured expected goals for this fixture from API-Football.",
    "stats_api_xg": "Measured match xG from the stats feed.",
    "understat_xg": "Fixture-level xG from Understat (strong for big leagues).",
    "understat_team_xg": "Team rolling xG from Understat when the exact match row is missing.",
    "fotmob_league_xg": "Season table xG per team — useful for cups; not specific to this kick-off.",
    "scraped_recent_xg": "Average xG from each team's last games where API published xG.",
    "api_season_team_xg": "Season attack/defence rates from API team stats (no fixture xG).",
    "sofascore_xg": "Team xG averages from SofaScore.",
    "statsbomb_goals_proxy_xg": "Goals scored/conceded proxy — weaker than measured xG.",
    "form_derived_xg": "Same goals-based estimate; label upgraded only when form is deep.",
    "mixed_api_goals_proxy": "One side had API xG; the other uses a goals-based fill.",
    "goals_proxy": "Poisson rates from recent goals when no measured xG was found.",
    "unknown": "Run enrich again or check API quota if this persists.",
}


def xg_source_label(xg_source: Any) -> str:
    s = str(xg_source or "unknown").strip().lower()
    if s in _LABELS:
        return _LABELS[s]
    if "understat" in s:
        return _LABELS["understat_xg"]
    if "fotmob" in s:
        return _LABELS["fotmob_league_xg"]
    if "fbref" in s:
        return "FBref xG"
    if "proxy" in s or "goals" in s:
        return _LABELS["goals_proxy"]
    return s.replace("_", " ").title() if s else _LABELS["unknown"]


def xg_confidence_tier(
    xg_source: Any,
    *,
    meta: Optional[Dict[str, Any]] = None,
    home_recent_n: float = 0.0,
    away_recent_n: float = 0.0,
) -> str:
    """
    Product-facing trust bucket: strong | usable | thin | proxy.

    Aligns with historic_calibration tiers but splits league-table and goals proxies.
    """
    s = str(xg_source or "").strip().lower()
    meta = meta or {}
    tier = xg_quality_tier(s)
    if tier == "high":
        if s == "fotmob_league_xg":
            try:
                hn = int(meta.get("home_n") or 0)
                an = int(meta.get("away_n") or 0)
            except (TypeError, ValueError):
                hn = an = 0
            if hn >= 8 and an >= 8:
                return "usable"
            return "thin"
        return "strong"
    if s in ("scraped_recent_xg", "api_season_team_xg"):
        if home_recent_n >= 4 and away_recent_n >= 4:
            return "usable"
        return "thin"
    if s in ("statsbomb_goals_proxy_xg", "form_derived_xg", "goals_proxy", "mixed_api_goals_proxy"):
        return "proxy"
    if tier == "medium":
        return "usable"
    return "thin"


def xg_source_hint(
    xg_source: Any,
    *,
    meta: Optional[Dict[str, Any]] = None,
    confidence: Optional[str] = None,
) -> str:
    s = str(xg_source or "unknown").strip().lower()
    base = _HINTS.get(s) or _HINTS.get("unknown", "")
    conf = confidence or xg_confidence_tier(s, meta=meta)
    if conf == "proxy":
        return f"{base} Confidence: proxy — treat edges cautiously."
    if conf == "thin":
        return f"{base} Confidence: thin — cross-check with form and odds."
    if conf == "usable":
        return f"{base} Confidence: usable."
    return f"{base} Confidence: strong."


def attach_xg_display_fields(target: Dict[str, Any], enriched: Optional[Dict[str, Any]] = None) -> None:
    """Set xg_source_label, xg_confidence_tier, xg_source_hint on a fixture row or enriched dict."""
    src = target.get("xg_source")
    if enriched and not src:
        src = enriched.get("xg_source")
    meta = (enriched or target).get("scraped_xg_meta") or {}
    try:
        nh = float((enriched or target).get("home_recent_n") or 0)
        na = float((enriched or target).get("away_recent_n") or 0)
    except (TypeError, ValueError):
        nh = na = 0.0
    conf = xg_confidence_tier(src, meta=meta, home_recent_n=nh, away_recent_n=na)
    target["xg_source_label"] = xg_source_label(src)
    target["xg_confidence_tier"] = conf
    target["xg_source_hint"] = xg_source_hint(src, meta=meta, confidence=conf)
