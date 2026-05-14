"""FBref squad tables — HTML fetch + parse (follow robots.txt; cache aggressively)."""

import re
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

_HEADERS = {"User-Agent": "hibs-bet/1.0 (research enrichment)"}

# fbref /en/comps/{id}/{season}/ — season like 2024-2025
FBREF_LEAGUE = {
    "EPL": ("9", "Premier-League"),
    "LA_LIGA": ("12", "La-Liga"),
    "SERIE_A": ("11", "Serie-A"),
    "BUNDESLIGA": ("20", "Bundesliga"),
    "LIGUE_1": ("13", "Ligue-1"),
}


def _season_label(now_year: int, month: int) -> str:
    if month >= 7:
        return f"{now_year}-{now_year + 1}"
    return f"{now_year - 1}-{now_year}"


def fetch_squad_stats_table(league_code: str, season_label: Optional[str] = None) -> List[Dict[str, Any]]:
    meta = FBREF_LEAGUE.get(league_code)
    if not meta:
        return []
    from datetime import datetime

    now = datetime.now()
    sl = season_label or _season_label(now.year, now.month)
    comp_id, comp_slug = meta
    url = f"https://fbref.com/en/comps/{comp_id}/{sl}/{sl}-Stats-{comp_slug}-Stats"
    r = requests.get(url, headers=_HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table", id=re.compile(r"stats_squads_standard_for"))
    if not table:
        table = soup.find("table", attrs={"class": re.compile(r"stats_table")})
    if not table:
        return []
    rows_out: List[Dict[str, Any]] = []
    thead = table.find("thead")
    headers: List[str] = []
    if thead:
        for th in thead.find_all("th"):
            tid = th.get("data-stat") or th.get_text(strip=True)
            headers.append(str(tid))
    for tr in table.find("tbody").find_all("tr") if table.find("tbody") else []:
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
