"""League tables from Wikipedia (MediaWiki HTML) — no API keys; cache aggressively.

Wikipedia content is CC BY-SA; attribute when redistributing text. We only parse
numeric standings for internal previews. Respect crawl rate (cached hours).
"""

import re
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": "hibs-bet/1.0 (standings preview; contact via site owner)",
    "Accept-Language": "en",
}

# league_code → Wikipedia article title suffix (after season prefix "YYYY–YY_")
WP_SUFFIX: Dict[str, str] = {
    "EPL": "Premier_League",
    "SCOTLAND": "Scottish_Premiership",
    "SCOTLAND_CHAMP": "Scottish_Championship",
    "SCOTLAND_L1": "Scottish_League_One",
    "SCOTLAND_L2": "Scottish_League_Two",
    "LA_LIGA": "La_Liga",
    "SERIE_A": "Serie_A",
    "BUNDESLIGA": "Bundesliga",
    "LIGUE_1": "Ligue_1",
    "CHAMPIONSHIP": "EFL_Championship",
    "LEAGUE_ONE": "EFL_League_One",
    "LEAGUE_TWO": "EFL_League_Two",
    "EREDIVISIE": "Eredivisie",
    "PRIMEIRA": "Primeira_Liga",
    "BELGIUM_FIRST": "Belgian_Pro_League",
    "DENMARK_SL": "Danish_Superliga",
    "GREECE_SL": "Super_League_Greece",
    "AUSTRIA_BL": "Austrian_Football_Bundesliga",
    "UCL": "UEFA_Champions_League",
    "EUROPA_LEAGUE": "UEFA_Europa_League",
    "UECL": "UEFA_Europa_Conference_League",
    "WORLD_CUP": "FIFA_World_Cup",
    "EUROS": "UEFA_European_Championship",
    "NATIONS_LEAGUE": "UEFA_Nations_League",
}


def _season_wiki_title_part(now: Optional[datetime] = None) -> str:
    d = now or datetime.now()
    start = d.year if d.month >= 7 else d.year - 1
    end_short = str(start + 1)[2:]
    return f"{start}–{end_short}"


def _article_title(league_code: str, now: Optional[datetime] = None) -> Optional[str]:
    suf = WP_SUFFIX.get(league_code)
    if not suf:
        return None
    return f"{_season_wiki_title_part(now)}_{suf}"


def _norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[\._]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for rm in (" fc", " afc", " cf", " sc", " fk", " bk"):
        if s.endswith(rm):
            s = s[: -len(rm)].strip()
    return s


def _pick_standings_table(soup: BeautifulSoup) -> Optional[Any]:
    best = None
    best_n = 0
    for table in soup.select("table.wikitable"):
        rows = table.find_all("tr")
        if len(rows) < 6:
            continue
        header_cells = rows[0].find_all(["th", "td"])
        labels = [c.get_text(" ", strip=True).lower() for c in header_cells]
        joined = " ".join(labels)
        if "team" not in joined and "club" not in joined:
            continue
        if "pld" not in joined and "p" not in joined and "played" not in joined:
            continue
        if "pts" not in joined and "points" not in joined:
            continue
        if len(rows) > best_n:
            best = table
            best_n = len(rows)
    return best


def _parse_int(cell: str) -> int:
    cell = re.sub(r"[^\d\-]", "", cell or "")
    if not cell or cell == "-":
        return 0
    try:
        return int(cell)
    except ValueError:
        return 0


def fetch_league_table(league_code: str, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    title = _article_title(league_code, now)
    if not title:
        return []
    path = title.replace(" ", "_")
    url = "https://en.wikipedia.org/wiki/" + quote(path, safe="/'_()-!~")
    try:
        r = requests.get(url, headers=_HEADERS, timeout=25)
        r.raise_for_status()
    except requests.RequestException:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    table = _pick_standings_table(soup)
    if not table:
        return []

    rows = table.find_all("tr")
    if not rows:
        return []
    header_row = rows[0]
    headers = [c.get_text(" ", strip=True).lower() for c in header_row.find_all(["th", "td"])]
    out: List[Dict[str, Any]] = []

    def col_idx(*names: str) -> Optional[int]:
        for i, h in enumerate(headers):
            h_clean = re.sub(r"\s+", " ", (h or "").strip().lower())
            for n in names:
                n = n.lower()
                if h_clean == n or h_clean.startswith(n + " ") or h_clean.endswith(" " + n):
                    return i
        return None

    i_pos = col_idx("pos", "position", "rank") or 0
    i_team = col_idx("team", "club")
    if i_team is None:
        for i, h in enumerate(headers):
            if h in ("team", "club"):
                i_team = i
                break
    if i_team is None:
        i_team = 1
    i_pld = col_idx("pld", "played", " p ")
    i_w = col_idx("won", "wins", "w")
    i_d = col_idx("drawn", "drawn", "draws", "d")
    i_l = col_idx("lost", "losses", "l")
    i_gf = col_idx("gf", "goals for", "f")
    i_ga = col_idx("ga", "goals against", "a")
    i_gd = col_idx("gd", "goal difference")
    i_pts = col_idx("pts", "points")

    for tr in rows[1:]:
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
        if len(cells) <= max(i_pos, i_team, i_pts or 0, i_pld or 0):
            continue
        team_raw = cells[i_team]
        team_clean = re.sub(r"\[.*?\]", "", team_raw).strip()
        if not team_clean or len(team_clean) > 60:
            continue
        pos = _parse_int(cells[i_pos]) if i_pos < len(cells) else len(out) + 1
        if pos == 0:
            for c in cells[:3]:
                if c.isdigit():
                    pos = int(c)
                    break
            if pos == 0:
                pos = len(out) + 1
        played = _parse_int(cells[i_pld]) if i_pld is not None and i_pld < len(cells) else 0
        w = _parse_int(cells[i_w]) if i_w is not None and i_w < len(cells) else 0
        d = _parse_int(cells[i_d]) if i_d is not None and i_d < len(cells) else 0
        l = _parse_int(cells[i_l]) if i_l is not None and i_l < len(cells) else 0
        gf = _parse_int(cells[i_gf]) if i_gf is not None and i_gf < len(cells) else 0
        ga = _parse_int(cells[i_ga]) if i_ga is not None and i_ga < len(cells) else 0
        gd = _parse_int(cells[i_gd]) if i_gd is not None and i_gd < len(cells) else gf - ga
        pts = _parse_int(cells[i_pts]) if i_pts is not None and i_pts < len(cells) else 0
        if not team_clean:
            continue
        out.append(
            {
                "rank": pos,
                "team": team_clean,
                "played": played,
                "won": w,
                "drawn": d,
                "lost": l,
                "goals_for": gf,
                "goals_against": ga,
                "goal_diff": gd,
                "points": pts,
            }
        )
    out.sort(key=lambda r: r["rank"])
    return out


def row_to_position_shape(row: Dict[str, Any]) -> Dict[str, Any]:
    """Match shape expected by templates / API-Football fetch_team_position."""
    return {
        "position": row.get("rank"),
        "played": row.get("played", 0),
        "won": row.get("won", 0),
        "drawn": row.get("drawn", 0),
        "lost": row.get("lost", 0),
        "goals_for": row.get("goals_for", 0),
        "goals_against": row.get("goals_against", 0),
        "goal_diff": row.get("goal_diff", 0),
        "points": row.get("points", 0),
        "form": "",
        "source": "wikipedia",
    }


def find_team_row(rows: List[Dict[str, Any]], team_name: str) -> Optional[Dict[str, Any]]:
    if not rows or not team_name:
        return None
    q = _norm_name(team_name)
    if not q:
        return None
    best: Optional[Tuple[int, Dict[str, Any]]] = None
    for row in rows:
        t = _norm_name(row.get("team", ""))
        if not t:
            continue
        score = 0
        if q == t:
            score = 100
        elif q in t or t in q:
            score = 80 - abs(len(t) - len(q))
        elif any(part in t for part in q.split() if len(part) > 3):
            score = 50
        if score > 0 and (best is None or score > best[0]):
            best = (score, row)
    return best[1] if best else None
