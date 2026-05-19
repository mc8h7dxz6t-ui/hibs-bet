"""FBref competition schedule xG (Scottish + EFL + selected European leagues).

Fetches the competition schedule/scores page once per league+season (cached) and
resolves fixture xG by team-name match, or rolling team averages from finished rows.
Understat omits many of these comps; schedule pages often carry Opta xG columns.
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

_HEADERS = {"User-Agent": "hibs-bet/1.0 (Scottish xG enrichment)"}

# league_code → (fbref comp id, URL slug)
FBREF_SCOTTISH_LEAGUE: Dict[str, Tuple[str, str]] = {
    "SCOTLAND": ("40", "Scottish-Premiership"),
    "SCOTLAND_CHAMP": ("64", "Scottish-Championship"),
    "SCOTLAND_L1": ("226", "Scottish-League-One"),
    "SCOTLAND_L2": ("227", "Scottish-League-Two"),
}

# Additional comps with schedule-level xG on FBref (no Understat or thin API xG).
FBREF_SCHEDULE_EXTRA: Dict[str, Tuple[str, str]] = {
    "SERIE_A": ("11", "Serie-A"),
    "CHAMPIONSHIP": ("10", "EFL-Championship"),
    "LEAGUE_ONE": ("15", "EFL-League-One"),
    "LEAGUE_TWO": ("16", "EFL-League-Two"),
    "EREDIVISIE": ("23", "Eredivisie"),
    "PRIMEIRA": ("32", "Primeira-Liga"),
    "BELGIUM_FIRST": ("37", "Belgian-Pro-League"),
    "DENMARK_SL": ("50", "Superliga"),
    "GREECE_SL": ("27", "Super-League-Greece"),
    "AUSTRIA_BL": ("56", "Austrian-Bundesliga"),
}

FBREF_SCHEDULE_LEAGUES: Dict[str, Tuple[str, str]] = {**FBREF_SCOTTISH_LEAGUE, **FBREF_SCHEDULE_EXTRA}

SCOTTISH_LEAGUE_CODES = frozenset(FBREF_SCOTTISH_LEAGUE.keys())
SCHEDULE_XG_LEAGUE_CODES = frozenset(FBREF_SCHEDULE_LEAGUES.keys())


def is_scottish_league(league_code: str) -> bool:
    return (league_code or "").strip().upper() in SCOTTISH_LEAGUE_CODES


def has_fbref_schedule_xg(league_code: str) -> bool:
    return (league_code or "").strip().upper() in SCHEDULE_XG_LEAGUE_CODES


def _schedule_xg_enabled() -> bool:
    return _env_on("HIBS_ENABLE_FBREF_SCHEDULE_XG", "1") or _env_on("HIBS_ENABLE_SCOTTISH_FBREF_XG", "1")


def _env_on(name: str, default: str = "1") -> bool:
    return (os.getenv(name, default) or default).strip().lower() not in ("0", "false", "no", "off")


def _season_label(now_year: int, month: int) -> str:
    if month >= 7:
        return f"{now_year}-{now_year + 1}"
    return f"{now_year - 1}-{now_year}"


def _norm_name(name: str) -> str:
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
    for drop in (" fc", " afc", " united", " city"):
        if s.endswith(drop):
            s = s[: -len(drop)].strip()
    return s


def _team_names_match(a: str, b: str) -> bool:
    na, nb = _norm_name(a), _norm_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    pa = [p for p in na.split() if len(p) > 3]
    pb = [p for p in nb.split() if len(p) > 3]
    return bool(pa and pb and pa[0] == pb[0])


def _parse_xg(text: str) -> Optional[float]:
    if not text:
        return None
    t = str(text).strip().replace(",", ".")
    if t in ("", "—", "-", "–"):
        return None
    try:
        v = float(t)
    except ValueError:
        return None
    if v <= 0.04 or v > 6.0:
        return None
    return v


def _cell_text(td: Any) -> str:
    if td is None:
        return ""
    return td.get_text(" ", strip=True)


def _extract_team_from_cell(td: Any) -> str:
    if td is None:
        return ""
    a = td.find("a")
    if a and a.get_text(strip=True):
        return a.get_text(strip=True)
    return _cell_text(td)


def _parse_schedule_rows(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id=re.compile(r"^sched_"))
    if not table:
        for t in soup.find_all("table"):
            tid = t.get("id") or ""
            if "sched" in tid:
                table = t
                break
    if not table or not table.find("tbody"):
        return []
    rows_out: List[Dict[str, Any]] = []
    for tr in table.find("tbody").find_all("tr"):
        if "spacer" in tr.get("class", []) or "thead" in tr.get("class", []):
            continue
        cells: Dict[str, Any] = {}
        for td in tr.find_all(["th", "td"]):
            stat = td.get("data-stat")
            if stat:
                cells[stat] = td
        home_td = cells.get("home_team") or cells.get("squad")
        away_td = cells.get("away_team")
        if not home_td or not away_td:
            continue
        home = _extract_team_from_cell(home_td)
        away = _extract_team_from_cell(away_td)
        xh = _parse_xg(_cell_text(cells.get("home_xg") or cells.get("xg1") or cells.get("xg")))
        xa = _parse_xg(_cell_text(cells.get("away_xg") or cells.get("xg2")))
        if xh is None or xa is None:
            score_td = cells.get("score")
            if score_td:
                xg_spans = score_td.find_all("span", class_=re.compile(r"xg", re.I))
                if len(xg_spans) >= 2:
                    xh = xh or _parse_xg(xg_spans[0].get_text())
                    xa = xa or _parse_xg(xg_spans[1].get_text())
        if xh is None or xa is None:
            continue
        rows_out.append({"home": home, "away": away, "xg_home": xh, "xg_away": xa})
    return rows_out


def fetch_schedule_rows(
    league_code: str,
    season_label: Optional[str] = None,
    *,
    cache: Optional[Cache] = None,
) -> List[Dict[str, Any]]:
    meta = FBREF_SCHEDULE_LEAGUES.get((league_code or "").strip().upper())
    if not meta:
        return []
    comp_id, slug = meta
    now = datetime.now()
    sl = season_label or _season_label(now.year, now.month)
    c = cache or Cache()
    key = f"fbref_scot_sched_{league_code}_{sl}"
    hit = c.get(key, ttl_hours=12.0)
    if isinstance(hit, list):
        return hit
    url = f"https://fbref.com/en/comps/{comp_id}/{sl}/schedule/{slug}-Scores-and-Fixtures"
    r = requests.get(url, headers=_HEADERS, timeout=30)
    r.raise_for_status()
    rows = _parse_schedule_rows(r.text)
    c.set(key, rows, ttl_hours=12.0)
    return rows


def find_fixture_xg(
    league_code: str,
    home_name: str,
    away_name: str,
    *,
    rows: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Tuple[float, float]]:
    data = rows if rows is not None else fetch_schedule_rows(league_code)
    for row in data:
        if _team_names_match(row.get("home", ""), home_name) and _team_names_match(
            row.get("away", ""), away_name
        ):
            return float(row["xg_home"]), float(row["xg_away"])
    return None


def avg_team_xg(
    league_code: str,
    team_name: str,
    *,
    rows: Optional[List[Dict[str, Any]]] = None,
    last_n: int = 10,
    min_samples: int = 2,
) -> Optional[float]:
    data = rows if rows is not None else fetch_schedule_rows(league_code)
    vals: List[float] = []
    for row in data:
        h, a = row.get("home", ""), row.get("away", "")
        if _team_names_match(h, team_name):
            vals.append(float(row["xg_home"]))
        elif _team_names_match(a, team_name):
            vals.append(float(row["xg_away"]))
        if len(vals) >= last_n:
            break
    if len(vals) < min_samples:
        return None
    return sum(vals[:last_n]) / min(len(vals), last_n)


def resolve_fbref_schedule_xg(
    league_code: str,
    home_name: str,
    away_name: str,
) -> Optional[Tuple[float, float, str, Dict[str, Any]]]:
    """Return (xg_home, xg_away, source_tag, meta) when FBref schedule xG is available."""
    if not _schedule_xg_enabled():
        return None
    code = (league_code or "").strip().upper()
    if code not in SCHEDULE_XG_LEAGUE_CODES:
        return None
    try:
        rows = fetch_schedule_rows(league_code)
    except Exception:
        return None
    if not rows:
        return None
    scot = is_scottish_league(code)
    tag_row = "scottish_fbref_xg" if scot else "fbref_schedule_xg"
    tag_avg = "scottish_fbref_avg_xg" if scot else "fbref_schedule_avg_xg"
    meta: Dict[str, Any] = {"league": league_code, "rows": len(rows)}
    pair = find_fixture_xg(league_code, home_name, away_name, rows=rows)
    if pair:
        meta["match"] = "schedule_row"
        return pair[0], pair[1], tag_row, meta
    h_avg = avg_team_xg(league_code, home_name, rows=rows)
    a_avg = avg_team_xg(league_code, away_name, rows=rows)
    if h_avg is not None and a_avg is not None:
        meta["match"] = "team_avg_last10"
        return h_avg, a_avg, tag_avg, meta
    return None


def resolve_scottish_fbref_xg(
    league_code: str,
    home_name: str,
    away_name: str,
) -> Optional[Tuple[float, float, str, Dict[str, Any]]]:
    """Backward-compatible alias — Scottish leagues only."""
    if not is_scottish_league(league_code):
        return None
    return resolve_fbref_schedule_xg(league_code, home_name, away_name)
