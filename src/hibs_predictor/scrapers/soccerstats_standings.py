"""SoccerStats.com league tables — standings fallback when APIs are thin.

Public HTML tables; cached aggressively. Respect robots.txt and low request rate.
"""

from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from hibs_predictor.cache import Cache

_HEADERS = {"User-Agent": "hibs-bet/1.0 (standings enrichment; local)"}
BASE = "https://www.soccerstats.com"

# hibs league_code → soccerstats ``league`` query param (used on latest.asp)
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
    "NORWAY_ELITESERIEN": "norway",
    "FINLAND_VEIKKAUSLIIGA": "finland",
    "SCOTLAND_L1": "scotland3",
    "SCOTLAND_L2": "scotland4",
}


def _norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    for rm in (" fc", " afc", " cf", " sc", " united", " city"):
        if s.endswith(rm):
            s = s[: -len(rm)].strip()
    return s


def _debug(msg: str) -> None:
    if os.getenv("HIBS_DEBUG", "0").lower() in ("1", "true", "yes"):
        print(msg)


def _header_row_index(trs: List[Any]) -> Tuple[int, List[str]]:
    """Return (row_index, uppercased header cells) for a standings header row."""
    for i, tr in enumerate(trs[:4]):
        cells = [td.get_text(" ", strip=True).upper() for td in tr.find_all("td")]
        if "GP" not in cells:
            continue
        if "TEAM" in cells or "CLUB" in cells or "PTS" in cells or "POINTS" in cells:
            return i, cells
    return -1, []


def _col_index(header_cells: List[str], *names: str) -> int:
    for name in names:
        if name in header_cells:
            return header_cells.index(name)
    return -1


def _parse_standings_table(table: Any) -> List[Dict[str, Any]]:
    """Extract team rows from one SoccerStats standings table."""
    trs = table.find_all("tr")
    if len(trs) < 4:
        return []

    header_idx, header_cells = _header_row_index(trs)
    if header_idx < 0:
        return []

    gp_i = _col_index(header_cells, "GP")
    pts_i = _col_index(header_cells, "PTS", "POINTS")
    gf_i = _col_index(header_cells, "GF")
    ga_i = _col_index(header_cells, "GA")

    rows_out: List[Dict[str, Any]] = []
    for tr in trs[header_idx + 1 :]:
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        texts = [td.get_text(" ", strip=True) for td in tds]
        pos_raw = (texts[0] if texts else "").replace(".", "")
        if not pos_raw.isdigit():
            continue
        pos = int(pos_raw)
        team = texts[1] if len(texts) > 1 else ""
        if not team or not re.search(r"[A-Za-z]", team):
            continue

        def _cell_int(idx: int, default: int = 0) -> int:
            if idx < 0 or idx >= len(texts):
                return default
            try:
                return int(re.sub(r"[^\d-]", "", texts[idx]) or default)
            except ValueError:
                return default

        played = _cell_int(gp_i)
        if played < 5:
            continue
        points = _cell_int(pts_i)
        if points <= 0 and pts_i < 0:
            nums = []
            for t in texts[2:]:
                try:
                    nums.append(int(re.sub(r"[^\d-]", "", t) or 0))
                except ValueError:
                    pass
            points = nums[-1] if nums else 0
            gf = nums[-3] if len(nums) >= 4 else 0
            ga = nums[-2] if len(nums) >= 4 else 0
        else:
            gf = _cell_int(gf_i)
            ga = _cell_int(ga_i)

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
    return rows_out


def _pick_best_table(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """Prefer the full-season table (highest games-played) over home/away splits."""
    candidates: List[Tuple[int, int, List[Dict[str, Any]]]] = []
    for table in soup.find_all("table"):
        rows = _parse_standings_table(table)
        if len(rows) < 3:
            continue
        max_played = max(int(r.get("played") or 0) for r in rows)
        candidates.append((max_played, len(rows), rows))
    if not candidates:
        return []
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]


def parse_latest_html(html: str) -> List[Dict[str, Any]]:
    """Parse standings from a SoccerStats latest.asp page (for tests)."""
    soup = BeautifulSoup(html, "html.parser")
    return _pick_best_table(soup)


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

    url = f"{BASE}/latest.asp"
    try:
        r = requests.get(url, params={"league": param}, headers=_HEADERS, timeout=25)
    except requests.RequestException as exc:
        _debug(f"[soccerstats] {league_code}: request failed: {exc!r}")
        return []

    if r.status_code == 404:
        _debug(f"[soccerstats] {league_code}: 404 for {r.url}")
        return []
    if r.status_code != 200:
        _debug(f"[soccerstats] {league_code}: HTTP {r.status_code} for {r.url}")
        return []

    soup = BeautifulSoup(r.content, "html.parser", from_encoding=r.apparent_encoding or "utf-8")
    rows_out = _pick_best_table(soup)

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
