"""Merge optional supplemental sources into one dict (fail-soft per source)."""

import os
from datetime import datetime
from typing import Any, Dict

from hibs_predictor.cache import Cache


def collect_supplemental(fixture: Dict[str, Any], league_code: str, enriched: Dict[str, Any]) -> Dict[str, Any]:
    if os.getenv("HIBS_ENABLE_SUPPLEMENTAL", "1").lower() in ("0", "false", "no"):
        return {}

    cache = Cache()
    fid = fixture.get("fixture", {}).get("id") or ""
    key = f"supplemental_{fid}_{league_code}"
    hit = cache.get(key, ttl_hours=6)
    if hit:
        return hit

    out: Dict[str, Any] = {}
    home = (fixture.get("home", {}) or {}).get("name", "")
    heavy = os.getenv("HIBS_ENABLE_HEAVY_SCRAPERS", "0").lower() in ("1", "true", "yes")

    try:
        from hibs_predictor.scrapers import statsbomb_open as sb

        comps = sb.load_competitions()
        out["statsbomb_competition_count"] = len(comps)
    except Exception as exc:
        out["statsbomb_error"] = str(exc)

    if heavy:
        try:
            from hibs_predictor.scrapers import understat_client as us

            row = us.find_fixture_row(league_code, datetime.now().year, home, (fixture.get("away", {}) or {}).get("name", ""))
            if row:
                out["understat"] = us.extract_xg_from_row(row)
        except Exception as exc:
            out["understat_error"] = str(exc)

        try:
            from hibs_predictor.scrapers import fbref_client as fr

            rows = fr.fetch_squad_stats_table(league_code)
            if rows:
                sr = fr.squad_row_for_team(rows, home)
                if sr:
                    out["fbref_home_squad"] = {"squad": sr.get("squad"), "stat_keys": list(sr.get("cells", {}).keys())[:12]}
        except Exception as exc:
            out["fbref_error"] = str(exc)

    try:
        from hibs_predictor.scrapers import sofascore_client as ss

        ent = ss.first_team_hit(home)
        if ent and ent.get("id"):
            ev = ss.team_last_xg_summary(int(ent["id"]))
            out["sofascore_team_events"] = ev[:5]
    except Exception as exc:
        out["sofascore_error"] = str(exc)

    cache.set(key, out, ttl_hours=6)
    return out
