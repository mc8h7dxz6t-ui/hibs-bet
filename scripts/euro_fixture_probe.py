#!/usr/bin/env python3
"""Probe European/international leagues: config vs provider fixtures (next N days)."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.chdir(ROOT)

EURO_CODES = [
    "LA_LIGA", "SERIE_A", "BUNDESLIGA", "LIGUE_1", "EREDIVISIE", "PRIMEIRA",
    "BELGIUM_FIRST", "DENMARK_SL", "GREECE_SL", "AUSTRIA_BL",
    "NORWAY_ELITESERIEN", "FINLAND_VEIKKAUSLIIGA",
    "WORLD_CUP", "EUROS", "NATIONS_LEAGUE",
    "UCL", "EUROPA_LEAGUE", "UECL",
]


def _raw_counts(league_code: str, days: int) -> dict:
    from hibs_predictor.config import LEAGUES
    from hibs_predictor.data_aggregator import DataAggregator
    from hibs_predictor.web import (
        _normalize_api_sports,
        _normalize_fdo,
        _normalize_fotmob,
        _fixture_fetch_season_candidates,
        _api_football_season_year,
    )
    from hibs_predictor.scrapers import fotmob_client

    league = LEAGUES.get(league_code, {})
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days)
    date_from = now.strftime("%Y-%m-%d")
    date_to = cutoff.strftime("%Y-%m-%d")
    agg = DataAggregator()
    seasons = _fixture_fetch_season_candidates(
        league.get("football_data_org_id"), date_from, date_to, now
    )
    out = {"api_sports": 0, "fdo": 0, "fotmob": 0, "errors": []}

    api_id = league.get("api_sports_id")
    if api_id and "api_sports" in agg.clients:
        try:
            for season in seasons:
                raw = agg.clients["api_sports"].fetch_fixtures_by_league(
                    int(api_id), int(season), date_from=date_from, date_to=date_to
                )
                n = 0
                for f in raw or []:
                    norm = _normalize_api_sports(f, league_code)
                    if not norm:
                        continue
                    try:
                        fd = datetime.fromisoformat(str(norm["date"]).replace("Z", "+00:00"))
                        if now <= fd <= cutoff:
                            n += 1
                    except Exception:
                        pass
                if n:
                    out["api_sports"] = n
                    break
        except Exception as exc:
            out["errors"].append(f"api_sports:{exc!r}")

    comp = league.get("football_data_org_id")
    if comp and "football_data_org" in agg.clients:
        try:
            for season in seasons:
                raw = agg.clients["football_data_org"].fetch_fixtures(
                    comp, season, status=None, date_from=date_from, date_to=date_to
                )
                n = 0
                for m in raw or []:
                    st = str(m.get("status") or "").upper()
                    if st in ("FINISHED", "AWARDED", "CANCELLED", "POSTPONED", "ABANDONED", "SUSPENDED"):
                        continue
                    norm = _normalize_fdo(m, league_code)
                    if not norm:
                        continue
                    try:
                        fd = datetime.fromisoformat(str(norm["date"]).replace("Z", "+00:00"))
                        if now <= fd <= cutoff:
                            n += 1
                    except Exception:
                        pass
                if n:
                    out["fdo"] = n
                    break
        except Exception as exc:
            out["errors"].append(f"fdo:{exc!r}")

    if league_code in getattr(fotmob_client, "FOTMOB_LEAGUE_IDS", {}):
        try:
            raw = fotmob_client.fixtures_for_league(
                league_code, now.date(), cutoff.date()
            )
            n = 0
            for m in raw or []:
                norm = _normalize_fotmob(m, league_code)
                if not norm:
                    continue
                try:
                    fd = datetime.fromisoformat(str(norm["date"]).replace("Z", "+00:00"))
                    if now <= fd <= cutoff:
                        n += 1
                except Exception:
                    pass
            out["fotmob"] = n
        except Exception as exc:
            out["errors"].append(f"fotmob:{exc!r}")
    else:
        out["fotmob"] = -1  # no mapping

    return out


def main() -> None:
    os.environ.setdefault("HIBS_FETCH_DAYS", "7")
    days = int(os.getenv("HIBS_FETCH_DAYS", "7"))
    cache_dir = os.getenv("HIBS_CACHE_DIR", ".cache-staging")
    os.environ["HIBS_CACHE_DIR"] = cache_dir

    from hibs_predictor.config import LEAGUES
    from hibs_predictor.web import fetch_next_48h_fixtures

    print(f"Probe window: {days} days | cache: {cache_dir}")
    print(f"Now (UTC): {datetime.now(timezone.utc).isoformat()}")
    clients = []
    try:
        from hibs_predictor.data_aggregator import DataAggregator
        clients = list(DataAggregator().clients.keys())
    except Exception as exc:
        print(f"Aggregator init: {exc!r}")
    print(f"Active clients: {clients}\n")

    print(f"{'code':<18} {'name':<28} {'feed':>5} {'AS':>4} {'FDO':>4} {'FM':>4}  notes")
    print("-" * 95)
    for code in EURO_CODES:
        lg = LEAGUES.get(code, {})
        name = (lg.get("name") or code)[:28]
        try:
            feed = fetch_next_48h_fixtures(code)
            feed_n = len(feed)
        except Exception as exc:
            feed_n = -1
            feed_err = str(exc)[:60]
        else:
            feed_err = ""

        raw = _raw_counts(code, days)
        fm = raw["fotmob"]
        fm_s = "—" if fm == -1 else str(fm)
        notes = []
        if feed_err:
            notes.append(feed_err)
        if raw["errors"]:
            notes.append("; ".join(raw["errors"])[:80])
        if fm == -1 and not lg.get("football_data_org_id"):
            notes.append("no FDO id")
        if fm == -1 and code not in ("WORLD_CUP", "EUROS", "NATIONS_LEAGUE", "UECL"):
            if code == "UECL":
                notes.append("FotMob id not mapped")
            elif code in ("BELGIUM_FIRST", "DENMARK_SL", "GREECE_SL", "AUSTRIA_BL"):
                notes.append("FotMob id not mapped")
        if feed_n == 0 and raw["api_sports"] == 0 and raw["fdo"] == 0 and (fm <= 0):
            if code in ("WORLD_CUP", "EUROS", "NATIONS_LEAGUE"):
                notes.append("off-season / no fixtures in window")
            elif code in ("UCL", "EUROPA_LEAGUE", "UECL"):
                notes.append("UEFA club — check season/knockout")
        print(
            f"{code:<18} {name:<28} {feed_n:>5} {raw['api_sports']:>4} {raw['fdo']:>4} {fm_s:>4}  "
            + (" | ".join(notes) if notes else "")
        )


if __name__ == "__main__":
    main()
