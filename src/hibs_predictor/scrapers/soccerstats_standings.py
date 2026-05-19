"""SoccerStats.com league tables — standings fallback when APIs are thin.

Public HTML tables; cached aggressively. Respect robots.txt and low request rate.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from hibs_predictor.cache import Cache

_HEADERS = {"User-Agent": "hibs-bet/1.0 (standings enrichment; local)"}
BASE = "https://www.soccerstats.com"

# hibs league_code → soccerstats ``league`` query param
LEAGUE_PARAM: Dict[str, str] = {
    "EPL": "england",
    "CHAMPIONSHIP": "england2",
    "LEAGUE_ONE": "england3",
    "LEAGUE_TWO": "england4",
    "SCOTLAND": "scotland",
    "SCOTLAND_CHAMP": "scotland2",
    "LA_LIGA": "spain",
    "SERIE_A": "italy",
    "BUNDESLIGA": "germany",
    "LIGUE_1": "france",
    "EREDIVISIE": "netherlands",
    "PRIMEIRA": "portugal",
    "BELGIUM_FIRST": "belgium",
    "DENMARK_SL": "denmark",
    "GREECE_SL": "greece",
    "AUSTRIA_BL": "austria",
}


def _norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    for rm in (" fc", " afc", " cf", " sc", " united", " city"):
        if s.endswith(rm):
            s = s[: -len(rm)].strip()
    return s


def fetch_league_table(league_code: str, *, cache: Optional[Cache] = None) -> List[Dict[str, Any]]:
    """Parse SoccerStats overall table for a mapped league."""
    param = LEAGUE_PARAM.get((league_code or "").strip().upper())
    if not param:
        return []
    c = cache or Cache()
    key = f"soccerstats_tbl_{league_code}_{datetime.now().strftime('%Y%m')}"
    hit = c.get(key, ttl_hours=12.0)
    if isinstance(hit, list):
        return hit

    url = f"{BASE}/tables.asp"
    r = requests.get(url, params={"league": param, "tid": "r"}, headers=_HEADERS, timeout=25)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    rows_out: List[Dict[str, Any]] = []

    for table in soup.find_all("table"):
        trs = table.find_all("tr")
        if len(trs) < 8:
            continue
        header = " ".join(trs[0].get_text(" ", strip=True).lower())
        if "team" not in header and "club" not in header:
            continue
        if "pts" not in header and "points" not in header:
            continue
        for tr in trs[1:]:
            tds = tr.find_all("td")
            if len(tds) < 4:
                continue
            texts = [td.get_text(" ", strip=True) for td in tds]
            pos_raw = texts[0].replace(".", "")
            try:
                pos = int(re.sub(r"\D", "", pos_raw) or 0)
            except ValueError:
                pos = 0
            if pos < 1:
                continue
            team_cell = tds[1] if len(tds) > 1 else tds[0]
            team = team_cell.get_text(" ", strip=True)
            if not team or len(team) < 2:
                continue
            nums = []
            for t in texts[2:]:
                try:
                    nums.append(int(t))
                except ValueError:
                    pass
            played = nums[0] if len(nums) >= 1 else 0
            points = nums[-1] if nums else 0
            gf = nums[-3] if len(nums) >= 4 else 0
            ga = nums[-2] if len(nums) >= 4 else 0
            rows_out.append(
                {
                    "position": pos,
                    "team": team,
                    "played": played,
                    "points": points,
                    "goals_for": gf,
                    "goals_against": ga,
                    "source": "soccerstats",
                }
            )
        if rows_out:
            break

    c.set(key, rows_out, ttl_hours=12.0)
    return rows_out


def find_team_row(rows: List[Dict[str, Any]], team_name: str) -> Optional[Dict[str, Any]]:
    tn = _norm_name(team_name)
    if not tn:
        return None
    for row in rows:
        rt = _norm_name(str(row.get("team") or ""))
        if not rt:
            continue
        if tn == rt or tn in rt or rt in tn:
            return row
        tp = tn.split()
        rp = rt.split()
        if tp and rp and tp[0] == rp[0] and len(tp[0]) > 3:
            return row
    return None


def row_to_position_shape(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "position": row.get("position"),
        "played": row.get("played") or 0,
        "points": row.get("points") or 0,
        "goals_for": row.get("goals_for") or 0,
        "goals_against": row.get("goals_against") or 0,
        "source": "soccerstats",
    }
