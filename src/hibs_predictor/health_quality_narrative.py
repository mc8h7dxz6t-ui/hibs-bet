"""Attach human-readable ``prediction_effect`` hints to /api/health for dashboard transparency."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from dotenv import load_dotenv

_API_EFFECT: Dict[str, str] = {
    "api_football": "Core: fixtures, injuries, team stats, squad depth (players/squads), and most xG/odds paths. If down, enrichment falls back to Football-Data or proxies — expect lower data_quality and weaker Poisson inputs.",
    "football_data_org": "Backup fixture list when API-Football is unavailable. Does not replace all stats or injuries.",
    "odds_api": "Secondary / cross-check odds when enabled. Improves implied-probability checks and dual-source odds diff.",
}

_SCRAPER_EFFECT: Dict[str, str] = {
    "statsbomb_open": "Open-data JSON (no key). Competition list always; optional per-fixture goals-in-window proxy when enabled. Rarely shifts 1X2 unless blended priors are on.",
    "understat": "League-page xG when the embed parses. Heavy + light paths can feed optional xG blend in the betting engine.",
    "fbref": "Squad aggregates + schedule xG from HTML when heavy scrapers run. May 403 from datacenter IPs — set HIBS_FBREF_BLOCKED=1 on VPS; curl_cffi rarely helps on VPS. Understat + FotMob + API xG cover gaps.",
    "fotmob": "Daily match JSON fixture fallback when API lists are empty. League-table xG for UEFA cups + optional domestic. Primary xG fallback when FBref blocked.",
    "soccerstats": "Scraped league tables when API standings are thin; Norway/Finland/Scotland L1-L2 supported.",
    "sofascore": "Recent-match listing from public endpoints. Often 403 outside a browser; no core impact when absent.",
    "transfermarkt": "Deferred probe-only (ToS). Production squad/injury context uses API-Football injuries + players/squads — not Transfermarkt HTML.",
    "xgstat": "Deferred — no public JSON API. xG from Understat, FotMob, API fixture/recent-match paths instead.",
    "besoccer": "Deferred — no stable JSON API. Standings/stats from SoccerStats, API-Football, FotMob where mapped.",
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
        "prediction_effect": "When enabled, stores snapshots for post-match calibration (Brier, etc.). pred-log-sync joins FT scores and API Expected Goals when available. Does not change live 1X2 probabilities.",
    }


def _clv_log_line() -> Dict[str, Any]:
    load_dotenv()
    try:
        from hibs_predictor.prediction_log import _clv_enabled, _enabled as prediction_audit_enabled

        audit_on = prediction_audit_enabled()
        clv_on = _clv_enabled()
    except Exception:
        audit_on = clv_on = False
    return {
        "id": "clv_log",
        "label": "CLV logging (opening + closing odds)",
        "ok": audit_on and clv_on,
        "ms": None,
        "prediction_effect": (
            "When HIBS_CLV_LOG_ENABLED=1, snapshots store opening 1X2 and best-bet odds; "
            "pred-log-sync joins closing 1X2 from API-Football and computes clv_pp. "
            "Does not change live probabilities."
            if clv_on
            else "Set HIBS_CLV_LOG_ENABLED=1 with prediction audit on to track beat-close % by league."
        ),
    }


def _calibration_cache_line() -> Dict[str, Any]:
    load_dotenv()
    try:
        from hibs_predictor.historic_calibration import calibration_cache_path

        path = calibration_cache_path()
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            n = len(data.get("leagues") or {})
            gen = data.get("generated_at") or "unknown"
            return {
                "id": "calibration_cache",
                "label": "League calibration shrink cache",
                "ok": n > 0,
                "ms": None,
                "prediction_effect": (
                    f"{path}: {n} league(s), generated {gen}. "
                    "Engine reads shrink factors before value gates. Refresh weekly via calibration-fit."
                ),
            }
        return {
            "id": "calibration_cache",
            "label": "League calibration shrink cache",
            "ok": False,
            "ms": None,
            "prediction_effect": (
                f"No cache at {path} yet. Run python -m hibs_predictor.main calibration-fit "
                "after pred-log-sync accumulates scored rows."
            ),
        }
    except Exception as exc:
        return {
            "id": "calibration_cache",
            "label": "League calibration shrink cache",
            "ok": False,
            "ms": None,
            "prediction_effect": f"Cache probe failed: {exc!s}"[:160],
        }


def _audit_ops_summary() -> Dict[str, Any]:
    """CLV beat-close + calibration cache stats for /api/health and status page."""
    load_dotenv()
    out: Dict[str, Any] = {"prediction_log_enabled": False, "clv_log_enabled": False}
    try:
        from hibs_predictor.prediction_log import (
            _clv_enabled,
            _enabled as prediction_audit_enabled,
            clv_beat_close_by_league,
        )

        out["prediction_log_enabled"] = prediction_audit_enabled()
        out["clv_log_enabled"] = _clv_enabled()
        out["clv_by_league"] = clv_beat_close_by_league()
    except Exception as exc:
        out["clv_by_league"] = {"enabled": False, "leagues": [], "error": str(exc)[:120]}
    try:
        from hibs_predictor.historic_calibration import calibration_cache_path

        path = calibration_cache_path()
        out["calibration_cache_path"] = path
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            out["calibration_cache"] = {
                "ok": True,
                "generated_at": data.get("generated_at"),
                "baseline_brier": data.get("baseline_brier"),
                "n_leagues": len(data.get("leagues") or {}),
                "leagues": list((data.get("leagues") or {}).keys())[:12],
            }
        else:
            out["calibration_cache"] = {"ok": False, "message": "Run calibration-fit after scored audit rows exist."}
    except Exception as exc:
        out["calibration_cache"] = {"ok": False, "message": str(exc)[:120]}
    return out


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
        _clv_log_line(),
        _calibration_cache_line(),
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

    out["audit_ops"] = _audit_ops_summary()
    clv = out["audit_ops"].get("clv_by_league") or {}
    if int(clv.get("n_clv_rows") or 0) > 0 and clv.get("beat_close_pct") is not None:
        bullets.append(
            f"CLV audit: {clv['n_clv_rows']} value-bet row(s), beat-close {clv['beat_close_pct']}% overall "
            f"(see /status audit section or /api/audit/summary)."
        )
    cal = out["audit_ops"].get("calibration_cache") or {}
    if cal.get("ok") and cal.get("n_leagues"):
        bullets.append(
            f"League calibration cache: {cal['n_leagues']} league shrink factor(s) "
            f"(generated {cal.get('generated_at', '?')})."
        )

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
    try:
        from hibs_predictor.xg_priority_chain import xg_priority_chain_dict

        out["xg_priority_chain"] = xg_priority_chain_dict()
    except Exception:
        pass
    return out
