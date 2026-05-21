"""Attach human-readable ``prediction_effect`` hints to /api/health for dashboard transparency."""

from __future__ import annotations

import os
from typing import Any, Dict, List

from dotenv import load_dotenv

_API_EFFECT: Dict[str, str] = {
    "api_football": "Core: fixtures, injuries, team stats, and most xG/odds paths. If down, enrichment falls back to Football-Data or proxies — expect lower data_quality and weaker Poisson inputs.",
    "football_data_org": "Backup fixture list when API-Football is unavailable. Does not replace all stats or injuries.",
    "odds_api": "Secondary / cross-check odds when enabled. Improves implied-probability checks and dual-source odds diff.",
}

_SCRAPER_EFFECT: Dict[str, str] = {
    "statsbomb_open": "Open-data JSON (no key). Competition list always; optional per-fixture goals-in-window proxy when enabled. Rarely shifts 1X2 unless blended priors are on.",
    "understat": "League-page xG when the embed parses. Heavy + light paths can feed optional xG blend in the betting engine.",
    "fbref": "Squad aggregates from HTML when heavy scrapers run (or when not skipped). May 403 from some networks; core 1X2 still runs on APIs.",
    "sofascore": "Recent-match listing from public endpoints. Often 403 outside a browser; no core impact when absent.",
}


def _pred_audit_line() -> Dict[str, Any]:
    load_dotenv()
    try:
        from hibs_predictor.prediction_log import _enabled as prediction_audit_enabled

        on = prediction_audit_enabled()
    except Exception:
        on = False
    return {
        "id": "prediction_audit",
        "label": "Prediction audit (SQLite)",
        "ok": on,
        "ms": None,
        "prediction_effect": "When enabled, stores snapshots for post-match calibration (Brier, etc.). Does not change live 1X2 probabilities.",
    }


def augment_health_for_ui(health: Dict[str, Any]) -> Dict[str, Any]:
    """Return a shallow copy of health with ``prediction_effect`` and ``prediction_quality``."""
    load_dotenv()
    out = dict(health)
    apis: List[Dict[str, Any]] = [dict(a) for a in (health.get("apis") or [])]
    scrapers: List[Dict[str, Any]] = [dict(s) for s in (health.get("scrapers") or [])]

    for a in apis:
        aid = str(a.get("id") or "")
        a["prediction_effect"] = _API_EFFECT.get(
            aid, "Supporting API. Limited direct effect on Poisson/ML blend unless wired into enrichment."
        )
    for s in scrapers:
        sid = str(s.get("id") or "")
        s["prediction_effect"] = _SCRAPER_EFFECT.get(
            sid, "Supplemental probe; effect depends on aggregator wiring for that fixture."
        )

    heavy_enabled = os.getenv("HIBS_ENABLE_HEAVY_SCRAPERS", "1").lower() not in ("0", "false", "no")
    always_deep = os.getenv("HIBS_ALWAYS_DEEP_SCRAPE", "1").lower() not in ("0", "false", "no", "off")
    skip_strong = os.getenv("HIBS_SKIP_HEAVY_WHEN_API_STRONG", "0").lower() not in ("0", "false", "no")
    if always_deep:
        skip_strong = False

    features: List[Dict[str, Any]] = [
        _pred_audit_line(),
        {
            "id": "heavy_scrapers",
            "label": "Heavy scrapers (FBref + full Understat)",
            "ok": heavy_enabled,
            "ms": None,
            "prediction_effect": (
                "Default **on** for every fixture (`HIBS_ALWAYS_DEEP_SCRAPE` default on). "
                "Set `HIBS_SKIP_HEAVY_WHEN_API_STRONG=1` to skip heavy only when APIs already cover odds, xG, form, stats, and table positions. "
                "Set `HIBS_ENABLE_HEAVY_SCRAPERS=0` only if heavy HTML is **detrimental** (blocks, ToS, rate limits)."
                if skip_strong
                else "Default **on** for every fixture (`HIBS_ALWAYS_DEEP_SCRAPE` / `HIBS_SKIP_HEAVY_WHEN_API_STRONG=0`). "
                "Set `HIBS_SKIP_HEAVY_WHEN_API_STRONG=1` to skip heavy when APIs fully cover the same inputs."
            ),
        },
    ]

    api_football_ok = next((x.get("ok") for x in apis if x.get("id") == "api_football"), False)
    fdo_ok = next((x.get("ok") for x in apis if x.get("id") == "football_data_org"), False)

    if api_football_ok:
        overall = "strong"
        headline = "Primary football API is up; model inputs are usually in good shape."
    elif fdo_ok:
        overall = "degraded"
        headline = "API-Football is down but Football-Data may still list some fixtures; stats, injuries, and xG may be thinner — treat probabilities and value bets more cautiously."
    else:
        overall = "minimal"
        headline = "Fixture APIs impaired; expect sparse listings, lower data-quality scores, and wider uncertainty on side markets until keys/quota recover."

    bullets: List[str] = []
    if not api_football_ok:
        bullets.append("Without API-Football, live fixture xG and many enrichments may fall back to proxies — Poisson λ and ML features are noisier.")
    if not next((x.get("ok") for x in scrapers if x.get("id") == "understat"), True):
        bullets.append("Understat probe failed: optional Understat xG paths may be empty; core 1X2 still uses API-backed xG when available.")
    if not next((x.get("ok") for x in scrapers if x.get("id") == "sofascore"), True):
        bullets.append("Sofascore blocked or empty: no effect on core 1X2 when APIs supply form and odds.")

    if heavy_enabled and skip_strong:
        bullets.append(
            "Heavy scrapers (FBref + full Understat) are on; `HIBS_SKIP_HEAVY_WHEN_API_STRONG=1` skips them only when book odds, API xG, 4+ recent games each side, season stats, and league positions already cover what heavy would add."
        )
    elif heavy_enabled:
        bullets.append("Heavy scrapers run on every fixture when supplemental is on; watch FBref rate limits.")
    elif not heavy_enabled:
        bullets.append(
            "Heavy scrapers are off (`HIBS_ENABLE_HEAVY_SCRAPERS=0`) — use only when HTML scraping is detrimental; predictions rely more on APIs only."
        )

    cd = health.get("cache_disk") or {}
    cd_ok = not bool(cd.get("error"))
    cd_files = int(cd.get("files") or 0)
    cd_ttl = int(cd.get("entries_with_ttl_metadata") or 0)
    cd_dir = str(cd.get("cache_dir") or ".cache")
    features = features + [
        {
            "id": "disk_cache",
            "label": "Disk cache (TTL JSON)",
            "ok": cd_ok,
            "ms": None,
            "prediction_effect": (
                f"{cd_dir}: {cd_files} JSON file(s), {cd_ttl} with embedded ttl_hours. "
                "On startup, DataAggregator runs Cache.prune_stale() when HIBS_CACHE_PRUNE is not disabled — stale blobs are deleted using cached_at + ttl_hours "
                "(legacy files without ttl_hours use a 7-day fallback)."
            ),
        }
    ]

    out["apis"] = apis
    out["scrapers"] = scrapers
    out["features"] = features
    out["scrapers_policy"] = {
        "heavy_scrapers_default": "on" if heavy_enabled else "off",
        "skip_heavy_when_api_strong": skip_strong,
    }
    out["prediction_quality"] = {
        "overall": overall,
        "headline": headline,
        "bullets": bullets,
        "heavy_scrapers_enabled": heavy_enabled,
        "skip_heavy_when_api_strong": skip_strong,
    }
    return out
