"""Data aggregator that enriches fixtures with multi-API data."""

import os
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from dotenv import load_dotenv

from hibs_predictor.api_clients import (
    ApiSportsFootballClient,
    FootballDataOrgClient,
    SportsMonkClient,
    OddsApiClient,
    StatsApiClient,
)
from hibs_predictor.betting_engine import TeamStrengthCalculator
from hibs_predictor.config import LEAGUES
from hibs_predictor.cache import Cache
from hibs_predictor.data_quality import compute_fixture_data_quality
from hibs_predictor.scrapers.supplemental import collect_supplemental
from hibs_predictor.fixture_utils import coerce_team_id, fixture_team_id, fixture_team_name
from hibs_predictor.scrapers import wikipedia_standings as wiki_standings
from hibs_predictor.scrapers import soccerstats_standings as soccerstats_standings


def _project_root() -> str:
    """Repository root (parent of `src/`), regardless of process cwd."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _load_dotenv_from_project() -> None:
    """Load `.env` from the repo root so fixture APIs work when cwd is not the project folder."""
    root = _project_root()
    load_dotenv(os.path.join(root, ".env"))
    load_dotenv(os.path.join(root, ".env.local"))


def _looks_like_placeholder(value: str) -> bool:
    low = value.strip().lower()
    if not low:
        return True
    if "your_" in low and "here" in low:
        return True
    if low in ("xxx", "test", "none", "changeme", "null", "n/a", "na"):
        return True
    return False


def _env_first_usable(*names: str) -> str:
    for name in names:
        raw = os.getenv(name)
        if raw is None:
            continue
        val = raw.strip().strip('"').strip("'").lstrip("\ufeff")
        if not val or val.startswith("#"):
            continue
        if _looks_like_placeholder(val):
            continue
        return val
    return ""


def _env_flag_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def _season_candidates(now: Optional[datetime] = None) -> List[int]:
    """Current domestic season id plus previous season for completed/thin windows."""
    d = now or datetime.now()
    primary = d.year if d.month >= 7 else d.year - 1
    return [primary, primary - 1]


def _norm_team_name(name: Any) -> str:
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    for suffix in (" fc", " afc", " cf", " sc"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    return text


def _football_data_position_from_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "position": entry.get("position"),
        "played": entry.get("playedGames", 0),
        "won": entry.get("won", 0),
        "drawn": entry.get("draw", 0),
        "lost": entry.get("lost", 0),
        "goals_for": entry.get("goalsFor", 0),
        "goals_against": entry.get("goalsAgainst", 0),
        "goal_diff": entry.get("goalDifference", 0),
        "points": entry.get("points", 0),
        "form": entry.get("form", ""),
        "source": "football_data_org",
    }


def _effective_skip_odds_api(clients: Dict[str, Any]) -> bool:
    """Use The Odds API when the client is configured unless HIBS_SKIP_ODDS_API opts out."""
    if "odds_api" not in clients:
        return True
    return _env_flag_truthy("HIBS_SKIP_ODDS_API")


def _effective_skip_rapid_stats_xg(clients: Dict[str, Any]) -> bool:
    """Default skips RapidAPI stats xG; HIBS_MAX_DATA=1 + stats_api client enables it without editing HIBS_SKIP_RAPID_STATS_XG."""
    raw = os.getenv("HIBS_SKIP_RAPID_STATS_XG", "1").strip().lower()
    if raw not in ("1", "true", "yes"):
        return False
    if _env_flag_truthy("HIBS_MAX_DATA") and "stats_api" in clients:
        return False
    return True


def _extract_goals_totals_from_api_stats(team_stats: Dict[str, Any]) -> Tuple[int, int]:
    """Normalize API-Football teams/statistics goals shape to (goals_for, goals_against)."""
    goals = team_stats.get("goals") or {}
    out_for, out_against = 0, 0
    for side_key, target in (("for", "for"), ("against", "against")):
        side = goals.get(side_key) or {}
        total = side.get("total")
        if isinstance(total, dict):
            v = total.get("total")
            if v is None:
                v = (total.get("home") or 0) + (total.get("away") or 0)
            try:
                val = int(v or 0)
            except (TypeError, ValueError):
                val = 0
        else:
            try:
                val = int(total or 0)
            except (TypeError, ValueError):
                val = 0
        if side_key == "for":
            out_for = val
        else:
            out_against = val
    return out_for, out_against


def _recent_match_rates(matches: List[Dict[str, Any]], team_id: int) -> Dict[str, float]:
    """BTTS / over rates and per-game goals from the team's last finished matches."""
    if not team_id or not matches:
        return {
            "btts_rate": 0.0,
            "over15_rate": 0.0,
            "over25_rate": 0.0,
            "avg_gf": 0.0,
            "avg_ga": 0.0,
            "n": 0.0,
        }
    btts = o15 = o25 = 0
    tgf = tga = 0.0
    n = 0
    for match in matches[:10]:
        teams = match.get("teams", {})
        goals = match.get("goals", {}) or {}
        hid = coerce_team_id((teams.get("home") or {}).get("id"))
        aid = coerce_team_id((teams.get("away") or {}).get("id"))
        tid = coerce_team_id(team_id)
        home_g = goals.get("home")
        away_g = goals.get("away")
        if home_g is None or away_g is None:
            continue
        try:
            hg = int(home_g)
            ag = int(away_g)
        except (TypeError, ValueError):
            continue
        if tid is not None and hid == tid:
            gf, ga = hg, ag
        elif tid is not None and aid == tid:
            gf, ga = ag, hg
        else:
            continue
        n += 1
        tgf += gf
        tga += ga
        if gf > 0 and ag > 0:
            btts += 1
        if gf + ga > 1:
            o15 += 1
        if gf + ga > 2:
            o25 += 1
    if n == 0:
        return {
            "btts_rate": 0.0,
            "over15_rate": 0.0,
            "over25_rate": 0.0,
            "avg_gf": 0.0,
            "avg_ga": 0.0,
            "n": 0.0,
        }
    return {
        "btts_rate": btts / n,
        "over15_rate": o15 / n,
        "over25_rate": o25 / n,
        "avg_gf": tgf / n,
        "avg_ga": tga / n,
        "n": float(n),
    }


def _implied_prob(odds: float) -> float:
    if odds is None or odds <= 1.0:
        return 0.0
    return 1.0 / float(odds)


def _fdo_match_to_recent_format(match: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize Football-Data.org finished match → API-Sports-like shape for rate calculators."""
    ht = match.get("homeTeam") or {}
    at = match.get("awayTeam") or {}
    if not isinstance(ht, dict) or not isinstance(at, dict):
        return None
    hid, aid = ht.get("id"), at.get("id")
    ft = (match.get("score") or {}).get("fullTime") or {}
    home_g, away_g = ft.get("home"), ft.get("away")
    if home_g is None or away_g is None:
        return None
    try:
        return {
            "teams": {"home": {"id": int(hid)}, "away": {"id": int(aid)}},
            "goals": {"home": int(home_g), "away": int(away_g)},
            "_source": "football_data_org",
        }
    except (TypeError, ValueError):
        return None


def _stats_from_fdo_matches(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    from hibs_predictor.api_clients import FootballDataOrgClient

    if not matches:
        return {}
    parsed = FootballDataOrgClient.parse_form_from_matches(matches)
    n = min(10, len(matches))
    if n == 0:
        return {}
    gf = float(parsed.get("goals_for") or 0)
    ga = float(parsed.get("goals_against") or 0)
    return {
        "goals_for": gf,
        "goals_against": ga,
        "played": n,
        "wins": parsed.get("wins", 0),
        "draws": parsed.get("draws", 0),
        "losses": parsed.get("losses", 0),
        "source": "football_data_org",
    }


def _empty_rates() -> Dict[str, float]:
    return {
        "btts_rate": 0.0,
        "over15_rate": 0.0,
        "over25_rate": 0.0,
        "avg_gf": 0.0,
        "avg_ga": 0.0,
        "n": 0.0,
    }


def _empty_odds_bundle() -> Dict[str, Any]:
    return {
        "odds_home": None,
        "odds_draw": None,
        "odds_away": None,
        "odds_available": False,
        "all_bookmaker_odds": [],
        "odds_secondary": {"home": None, "draw": None, "away": None},
        "odds_cross_max_implied_diff_pct": 0.0,
        "odds_cross_book_max_implied_diff_pct": 0.0,
        "odds_primary_source": "partial",
        "market_odds": {},
        "best_odds_1x2": {"home": None, "draw": None, "away": None},
        "best_odds_source": {"home": None, "draw": None, "away": None},
        "sharp_anchor_implied": {},
    }


def _max_implied_delta_pct(
    a: Optional[float],
    b: Optional[float],
    c: Optional[float],
    x: Optional[float],
    y: Optional[float],
    z: Optional[float],
) -> float:
    if not all(v and v > 1.0 for v in (a, b, c, x, y, z)):
        return 0.0
    d = 0.0
    for p, q in ((a, x), (b, y), (c, z)):
        d = max(d, abs(_implied_prob(p) - _implied_prob(q)) * 100.0)
    return round(d, 2)


def compute_best_line_from_bookmakers(
    all_bookmakers: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Best decimal price per 1X2 outcome across bookmaker rows, plus cross-book disagreement.

    Returns keys: best_odds_1x2, best_odds_source, odds_cross_book_max_implied_diff_pct,
    sharp_anchor_implied (median de-vig 1X2 or Pinnacle when listed).
    """
    sides = ("home", "draw", "away")
    best: Dict[str, Optional[float]] = {s: None for s in sides}
    source: Dict[str, Optional[str]] = {s: None for s in sides}
    by_side_prices: Dict[str, List[float]] = {s: [] for s in sides}
    pinnacle: Dict[str, Optional[float]] = {s: None for s in sides}

    for row in all_bookmakers or []:
        if not isinstance(row, dict):
            continue
        bm_name = str(row.get("bookmaker") or row.get("name") or "").strip()
        is_pinnacle = "pinnacle" in bm_name.lower()
        for side in sides:
            raw = row.get(side)
            try:
                price = float(raw) if raw is not None else 0.0
            except (TypeError, ValueError):
                continue
            if price <= 1.0:
                continue
            by_side_prices[side].append(price)
            if is_pinnacle:
                cur = pinnacle.get(side)
                pinnacle[side] = price if cur is None else max(cur, price)
            cur_best = best[side]
            if cur_best is None or price > cur_best:
                best[side] = price
                source[side] = bm_name or row.get("source") or "unknown"

    cross = 0.0
    for side in sides:
        prices = by_side_prices[side]
        if len(prices) < 2:
            continue
        impls = [_implied_prob(p) for p in prices if p > 1.0]
        if len(impls) >= 2:
            cross = max(cross, (max(impls) - min(impls)) * 100.0)

    sharp: Dict[str, float] = {}
    if all(pinnacle.get(s) and pinnacle[s] > 1.0 for s in sides):
        raw_impl = {s: _implied_prob(float(pinnacle[s])) for s in sides}  # type: ignore[arg-type]
        s = sum(raw_impl.values())
        if s > 0:
            sharp = {k: raw_impl[k] / s for k in raw_impl}
    else:
        med_odds: Dict[str, float] = {}
        for side in sides:
            prices = sorted(by_side_prices[side])
            if not prices:
                continue
            mid = prices[len(prices) // 2]
            med_odds[side] = mid
        if len(med_odds) == 3:
            raw_impl = {k: _implied_prob(v) for k, v in med_odds.items()}
            s = sum(raw_impl.values())
            if s > 0:
                sharp = {k: raw_impl[k] / s for k in raw_impl}

    return {
        "best_odds_1x2": best,
        "best_odds_source": source,
        "odds_cross_book_max_implied_diff_pct": round(cross, 2),
        "sharp_anchor_implied": sharp,
    }


def _parse_api_sports_side_markets(odds_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """BTTS and Over/Under lines from API-Football odds (best decimal per selection)."""
    btts_yes: List[float] = []
    btts_no: List[float] = []
    over15: List[float] = []
    under15: List[float] = []
    over25: List[float] = []
    under25: List[float] = []
    over35: List[float] = []
    under35: List[float] = []
    for entry in odds_data or []:
        for bm in entry.get("bookmakers", []) or []:
            for bet in bm.get("bets", []) or []:
                name = (bet.get("name") or "").strip()
                vals = bet.get("values", []) or []
                if name == "Both Teams To Score":
                    for v in vals:
                        val = (v.get("value") or "").strip().lower()
                        try:
                            p = float(v.get("odd", 0) or 0)
                        except (TypeError, ValueError):
                            continue
                        if p <= 1.0:
                            continue
                        if val == "yes":
                            btts_yes.append(p)
                        elif val == "no":
                            btts_no.append(p)
                elif name in ("Goals Over/Under", "Over/Under", "Total Goals"):
                    for v in vals:
                        val = (v.get("value") or "").strip().lower()
                        try:
                            p = float(v.get("odd", 0) or 0)
                        except (TypeError, ValueError):
                            continue
                        if p <= 1.0:
                            continue
                        if "over 1.5" in val or val in ("o1.5", "over 1.5"):
                            over15.append(p)
                        elif "under 1.5" in val or val in ("u1.5", "under 1.5"):
                            under15.append(p)
                        if "over 2.5" in val or val in ("o2.5", "over 2.5"):
                            over25.append(p)
                        elif "under 2.5" in val or val in ("u2.5", "under 2.5"):
                            under25.append(p)
                        if "over 3.5" in val or val in ("o3.5", "over 3.5"):
                            over35.append(p)
                        elif "under 3.5" in val or val in ("u3.5", "under 3.5"):
                            under35.append(p)
    out: Dict[str, Any] = {}
    if btts_yes:
        out["btts_yes"] = max(btts_yes)
    if btts_no:
        out["btts_no"] = max(btts_no)
    if over15:
        out["over_1_5"] = max(over15)
    if under15:
        out["under_1_5"] = max(under15)
    if over25:
        out["over_2_5"] = max(over25)
    if under25:
        out["under_2_5"] = max(under25)
    if over35:
        out["over_3_5"] = max(over35)
    if under35:
        out["under_3_5"] = max(under35)
    return out


class DataAggregator:
    """Aggregates data from multiple APIs to enrich fixture data."""

    def __init__(self) -> None:
        _load_dotenv_from_project()
        load_dotenv()
        self.cache = Cache()
        self.clients = self._initialize_clients()
        if os.getenv("HIBS_CACHE_PRUNE", "1").lower() not in ("0", "false", "no"):
            try:
                n = self.cache.prune_stale()
                if n:
                    print(f"[Cache] Pruned {n} stale on-disk entries")
            except OSError as exc:
                print(f"[Cache] Prune skipped: {exc}")

    def _initialize_clients(self) -> Dict[str, Any]:
        clients: Dict[str, Any] = {}

        api_sports_key = _env_first_usable(
            "API_SPORTS_FOOTBALL_KEY",
            "API_SPORTS_KEY",
            "APISPORTS_KEY",
        )
        if (
            api_sports_key
            and os.getenv("HIBS_DISABLE_API_SPORTS", "").strip().lower() not in ("1", "true", "yes", "on")
        ):
            clients["api_sports"] = ApiSportsFootballClient(api_sports_key)

        fdo_key = _env_first_usable("FOOTBALL_DATA_ORG_KEY", "FOOTBALL_DATA_KEY")
        if fdo_key:
            clients["football_data_org"] = FootballDataOrgClient(fdo_key)

        sm_key = _env_first_usable("SPORTSMONK_KEY")
        if sm_key:
            clients["sportsmonk"] = SportsMonkClient(sm_key)

        odds_key = _env_first_usable("ODDS_API_KEY")
        if odds_key:
            clients["odds_api"] = OddsApiClient(odds_key)

        stats_key = _env_first_usable("STATS_API_KEY")
        if stats_key:
            clients["stats_api"] = StatsApiClient(stats_key)

        return clients

    def _fetch_api_sports_position_with_fallback(
        self, team_id: Optional[int], league_api_id: Optional[int], season: int
    ) -> Dict[str, Any]:
        if not team_id or not league_api_id or "api_sports" not in self.clients:
            return {}
        for sy in [season, season - 1]:
            row = self._fetch_team_position(team_id, league_api_id, sy)
            if row:
                row.setdefault("source", "api_sports")
                if sy != season:
                    row.setdefault("season_status", "last_completed")
                return row
        return {}

    def _fetch_football_data_position_with_fallback(
        self,
        team_id: Optional[int],
        team_name: str,
        competition_code: Optional[str],
        season: int,
    ) -> Dict[str, Any]:
        if not competition_code or "football_data_org" not in self.clients:
            return {}
        client = self.clients["football_data_org"]
        for sy in [season, season - 1]:
            if team_id:
                row = client.fetch_team_position(int(team_id), str(competition_code), int(sy))
                if row:
                    if sy != season:
                        row.setdefault("season_status", "last_completed")
                    return row
            try:
                groups = client.fetch_standings(str(competition_code), int(sy))
            except Exception:
                groups = []
            wanted = _norm_team_name(team_name)
            if not wanted:
                continue
            for group in groups or []:
                if str(group.get("type") or "").upper() not in ("TOTAL", ""):
                    continue
                for entry in group.get("table") or []:
                    candidate = _norm_team_name((entry.get("team") or {}).get("name"))
                    if candidate and (candidate == wanted or candidate in wanted or wanted in candidate):
                        row = _football_data_position_from_entry(entry)
                        if sy != season:
                            row.setdefault("season_status", "last_completed")
                        return row
        return {}

    def enrich_fixture(self, fixture: Dict[str, Any], league_code: str = "EPL") -> Dict[str, Any]:
        """Enrich a fixture with comprehensive data from multiple sources."""
        league = LEAGUES.get(league_code, {})
        league_api_id = league.get("api_sports_id")
        fdo_comp = league.get("football_data_org_id")
        now = datetime.now()
        season = _season_candidates(now)[0]

        home_id = fixture_team_id(fixture, "home")
        away_id = fixture_team_id(fixture, "away")

        fx = fixture.get("fixture")
        raw_fid = fx.get("id") if isinstance(fx, dict) else None
        if raw_fid is None:
            raw_fid = fixture.get("id")
        fixture_id_str = str(raw_fid).strip() if raw_fid not in (None, "", 0, "0") else ""
        hk = fixture_team_name(fixture, "home") or "?"
        ak = fixture_team_name(fixture, "away") or "?"
        dt = str(fixture.get("date", ""))
        if fixture_id_str:
            cache_key = f"enriched_fixture_{fixture_id_str}_{league_code}_dq6"
        else:
            cache_key = f"enriched_fixture_teams_{league_code}_{hk}|{ak}|{dt}_dq6"

        try:
            fixture_id_for_xg = int(raw_fid) if raw_fid not in (None, "", "0", 0) else None
        except (TypeError, ValueError):
            fixture_id_for_xg = None

        cached = self.cache.get(cache_key, ttl_hours=2)
        if cached and not self._enriched_needs_recent_refetch(cached, home_id, away_id):
            return cached

        enriched = dict(cached) if cached else dict(fixture)

        try:
            enriched["home_recent"] = self._fetch_team_recent_matches(home_id, fdo_comp=fdo_comp)
        except Exception as exc:
            print(f"[enrich home_recent] {league_code} fid={fixture_id_str}: {exc!r}")
            enriched["home_recent"] = []
        try:
            enriched["away_recent"] = self._fetch_team_recent_matches(away_id, fdo_comp=fdo_comp)
        except Exception as exc:
            print(f"[enrich away_recent] {league_code} fid={fixture_id_str}: {exc!r}")
            enriched["away_recent"] = []

        try:
            home_rates = _recent_match_rates(enriched["home_recent"], home_id or 0)
            away_rates = _recent_match_rates(enriched["away_recent"], away_id or 0)
        except Exception as exc:
            print(f"[enrich match_rates] {league_code} fid={fixture_id_str}: {exc!r}")
            home_rates = _empty_rates()
            away_rates = _empty_rates()
        enriched["home_btts_rate"] = home_rates["btts_rate"]
        enriched["away_btts_rate"] = away_rates["btts_rate"]
        enriched["home_recent_n"] = int(home_rates["n"])
        enriched["away_recent_n"] = int(away_rates["n"])
        enriched["home_over25_rate"] = home_rates["over25_rate"]
        enriched["away_over25_rate"] = away_rates["over25_rate"]
        enriched["home_over15_rate"] = home_rates["over15_rate"]
        enriched["away_over15_rate"] = away_rates["over15_rate"]

        try:
            enriched["home_stats"] = self._fetch_team_stats(
                home_id, league_code, league_api_id, season, home_rates, fdo_comp=fdo_comp
            )
        except Exception as exc:
            print(f"[enrich home_stats] {league_code} fid={fixture_id_str}: {exc!r}")
            enriched["home_stats"] = {}
        try:
            enriched["away_stats"] = self._fetch_team_stats(
                away_id, league_code, league_api_id, season, away_rates, fdo_comp=fdo_comp
            )
        except Exception as exc:
            print(f"[enrich away_stats] {league_code} fid={fixture_id_str}: {exc!r}")
            enriched["away_stats"] = {}

        try:
            enriched["home_form"] = TeamStrengthCalculator.calculate_form_strength(
                enriched["home_recent"], home_id
            )
        except Exception as exc:
            print(f"[enrich home_form] {league_code} fid={fixture_id_str}: {exc!r}")
            enriched["home_form"] = 0.5
        try:
            enriched["away_form"] = TeamStrengthCalculator.calculate_form_strength(
                enriched["away_recent"], away_id
            )
        except Exception as exc:
            print(f"[enrich away_form] {league_code} fid={fixture_id_str}: {exc!r}")
            enriched["away_form"] = 0.5

        try:
            enriched["home_home_factor"] = TeamStrengthCalculator.calculate_home_away_factor(
                home_id, enriched["home_recent"], is_home=True
            )
        except Exception as exc:
            print(f"[enrich home_home_factor] {league_code} fid={fixture_id_str}: {exc!r}")
            enriched["home_home_factor"] = 1.0
        try:
            enriched["away_away_factor"] = TeamStrengthCalculator.calculate_home_away_factor(
                away_id, enriched["away_recent"], is_home=False
            )
        except Exception as exc:
            print(f"[enrich away_away_factor] {league_code} fid={fixture_id_str}: {exc!r}")
            enriched["away_away_factor"] = 1.0

        home_nm = fixture_team_name(fixture, "home")
        away_nm = fixture_team_name(fixture, "away")
        prefer_wiki = os.getenv("HIBS_PREFER_SCRAPED_STANDINGS", "1").lower() in ("1", "true", "yes")
        wiki_rows: List[Dict[str, Any]] = []
        if prefer_wiki and league_code in wiki_standings.WP_SUFFIX:
            try:
                wiki_rows = self._cached_wikipedia_league_table(league_code)
            except Exception as exc:
                print(f"[enrich wiki_standings] {league_code}: {exc!r}")
                wiki_rows = []

        hp: Dict[str, Any] = {}
        ap: Dict[str, Any] = {}
        if wiki_rows:
            try:
                wr = wiki_standings.find_team_row(wiki_rows, home_nm)
                arw = wiki_standings.find_team_row(wiki_rows, away_nm)
                if wr:
                    hp = wiki_standings.row_to_position_shape(wr)
                if arw:
                    ap = wiki_standings.row_to_position_shape(arw)
            except Exception as exc:
                print(f"[enrich wiki_positions] {league_code} fid={fixture_id_str}: {exc!r}")

        if league_api_id and "api_sports" in self.clients:
            skip_api_tbl = os.getenv("HIBS_SKIP_API_STANDINGS", "0").lower() in ("1", "true", "yes")
            if not skip_api_tbl:
                try:
                    if not hp.get("position"):
                        hp = self._fetch_api_sports_position_with_fallback(home_id, league_api_id, season) or hp
                except Exception as exc:
                    print(f"[enrich home_position] {league_code} fid={fixture_id_str}: {exc!r}")
                try:
                    if not ap.get("position"):
                        ap = self._fetch_api_sports_position_with_fallback(away_id, league_api_id, season) or ap
                except Exception as exc:
                    print(f"[enrich away_position] {league_code} fid={fixture_id_str}: {exc!r}")

        if fdo_comp and "football_data_org" in self.clients:
            try:
                if not hp.get("position"):
                    hp = self._fetch_football_data_position_with_fallback(home_id, home_nm, fdo_comp, season) or hp
            except Exception as exc:
                print(f"[enrich fdo_home_position] {league_code} fid={fixture_id_str}: {exc!r}")
            try:
                if not ap.get("position"):
                    ap = self._fetch_football_data_position_with_fallback(away_id, away_nm, fdo_comp, season) or ap
            except Exception as exc:
                print(f"[enrich fdo_away_position] {league_code} fid={fixture_id_str}: {exc!r}")

        if prefer_wiki and league_code in soccerstats_standings.LEAGUE_PARAM:
            try:
                if not hp.get("position") or not ap.get("position"):
                    ss_rows = self._cached_soccerstats_league_table(league_code)
                    if ss_rows:
                        if not hp.get("position"):
                            sr = soccerstats_standings.find_team_row(ss_rows, home_nm)
                            if sr:
                                hp = soccerstats_standings.row_to_position_shape(sr)
                        if not ap.get("position"):
                            sr_a = soccerstats_standings.find_team_row(ss_rows, away_nm)
                            if sr_a:
                                ap = soccerstats_standings.row_to_position_shape(sr_a)
            except Exception as exc:
                if os.getenv("HIBS_DEBUG", "0").lower() in ("1", "true", "yes"):
                    print(f"[enrich soccerstats_positions] {league_code} fid={fixture_id_str}: {exc!r}")

        enriched["home_position"] = hp
        enriched["away_position"] = ap

        try:
            enriched["xg_home"], enriched["xg_away"], enriched["xg_source"] = self._fetch_expected_goals(
                fixture_id_for_xg, home_rates, away_rates, league.get("strength_factor", 1.0)
            )
        except Exception as exc:
            print(f"[enrich xg] {league_code} fid={fixture_id_str}: {exc!r}")
            lam_h, lam_a = self._lambda_from_rates(home_rates, away_rates, league.get("strength_factor", 1.0))
            enriched["xg_home"], enriched["xg_away"], enriched["xg_source"] = float(lam_h), float(lam_a), "goals_proxy"

        try:
            bundle = self._fetch_odds_bundle(fixture, league_code)
        except Exception as exc:
            print(f"[enrich odds_bundle] {league_code} fid={fixture_id_str}: {exc!r}")
            bundle = _empty_odds_bundle()
        enriched["odds_home"] = bundle["odds_home"]
        enriched["odds_draw"] = bundle["odds_draw"]
        enriched["odds_away"] = bundle["odds_away"]
        enriched["odds_available"] = bundle["odds_available"]
        enriched["all_bookmaker_odds"] = bundle["all_bookmaker_odds"]
        enriched["odds_secondary"] = bundle["odds_secondary"]
        enriched["odds_cross_max_implied_diff_pct"] = bundle["odds_cross_max_implied_diff_pct"]
        enriched["odds_cross_book_max_implied_diff_pct"] = bundle.get("odds_cross_book_max_implied_diff_pct", 0.0)
        enriched["odds_primary_source"] = bundle["odds_primary_source"]
        enriched["market_odds"] = bundle["market_odds"]
        enriched["best_odds_1x2"] = bundle.get("best_odds_1x2") or {}
        enriched["best_odds_source"] = bundle.get("best_odds_source") or {}
        enriched["sharp_anchor_implied"] = bundle.get("sharp_anchor_implied") or {}
        enriched["league_factor"] = league.get("strength_factor", 1.0)
        try:
            fid_int = int(raw_fid) if raw_fid not in (None, "", "0", 0) else 0
        except (TypeError, ValueError):
            fid_int = 0
        if fid_int and "api_sports" in self.clients and os.getenv("HIBS_SKIP_API_INJURIES", "0").lower() not in (
            "1",
            "true",
            "yes",
        ):
            try:
                enriched["fixture_injuries"] = self.clients["api_sports"].fetch_injuries(fid_int)
            except Exception:
                enriched["fixture_injuries"] = []
        else:
            enriched["fixture_injuries"] = []
        try:
            enriched["supplemental"] = collect_supplemental(fixture, league_code, enriched)
        except Exception as exc:
            print(f"[enrich supplemental] {league_code} fid={fixture_id_str}: {exc!r}")
            enriched["supplemental"] = {}
        try:
            from hibs_predictor.scraped_xg import apply_scraped_xg_to_enriched

            enriched = apply_scraped_xg_to_enriched(fixture, league_code, enriched)
        except Exception as exc:
            print(f"[enrich scraped_xg] {league_code} fid={fixture_id_str}: {exc!r}")
        try:
            enriched["data_quality"] = compute_fixture_data_quality(enriched)
        except Exception as exc:
            print(f"[enrich data_quality] {league_code} fid={fixture_id_str}: {exc!r}")
            enriched["data_quality"] = {"score_pct": 0.0, "blocks": [], "full_scope": False, "strong_scope": False}

        cache_ttl = 2.0
        if self._enriched_needs_recent_refetch(enriched, home_id, away_id):
            cache_ttl = 0.25
        self.cache.set(cache_key, enriched, ttl_hours=cache_ttl)
        return enriched

    @staticmethod
    def _enriched_needs_recent_refetch(
        enriched: Dict[str, Any],
        home_id: Optional[int],
        away_id: Optional[int],
    ) -> bool:
        """True when a team id exists but no finished recent matches were loaded (retry, don't freeze empty)."""
        if home_id and not (enriched.get("home_recent") or []):
            return True
        if away_id and not (enriched.get("away_recent") or []):
            return True
        return False

    def _fetch_team_stats(
        self,
        team_id: Optional[int],
        league_code: str,
        league_api_id: Optional[int] = None,
        season: int = None,
        recent_rates: Optional[Dict[str, float]] = None,
        fdo_comp: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch team statistics from API-Football; augment with recent-match aggregates when sparse."""
        recent_rates = recent_rates or {}
        if not team_id:
            return {}

        season = season or (datetime.now().year if datetime.now().month >= 7 else datetime.now().year - 1)
        cache_key = f"team_stats_{team_id}_{league_code}_{season}"
        cached = self.cache.get(cache_key, ttl_hours=12)
        if cached:
            return cached

        stats: Dict[str, Any] = {}

        if "api_sports" in self.clients:
            for s in [season, season - 1]:
                try:
                    team_stats = self.clients["api_sports"].fetch_team_statistics(team_id, s, league_api_id)
                    if not team_stats:
                        continue
                    goals_for, goals_against = _extract_goals_totals_from_api_stats(team_stats)
                    shots = team_stats.get("shots", {}) or {}
                    on_blk = shots.get("on", {}) or {}
                    sot_raw = on_blk.get("total")
                    if isinstance(sot_raw, dict):
                        sot_val = int(sot_raw.get("total") or 0)
                    else:
                        try:
                            sot_val = int(sot_raw or 0)
                        except (TypeError, ValueError):
                            sot_val = 0
                    fixtures_blk = team_stats.get("fixtures", {}) or {}
                    played = fixtures_blk.get("played", {}) or {}
                    played_total = played.get("total")
                    try:
                        played_n = int(played_total or 0)
                    except (TypeError, ValueError):
                        played_n = 0
                    stats = {
                        "goals_for": goals_for,
                        "goals_against": goals_against,
                        "shots_on_target": sot_val,
                        "played": played_n,
                        "wins": (fixtures_blk.get("wins", {}) or {}).get("total", 0),
                        "draws": (fixtures_blk.get("draws", {}) or {}).get("total", 0),
                        "losses": (fixtures_blk.get("loses", {}) or {}).get("total", 0),
                    }
                    if goals_for or goals_against or played_n:
                        break
                except Exception:
                    continue

        if (not stats or (stats.get("goals_for", 0) == 0 and stats.get("goals_against", 0) == 0)) and fdo_comp and "football_data_org" in self.clients:
            try:
                fdo_matches = self.clients["football_data_org"].fetch_team_matches(int(team_id), 10)
                fdo_stats = _stats_from_fdo_matches(fdo_matches)
                if fdo_stats.get("played"):
                    stats = fdo_stats
            except Exception:
                pass

        if (not stats or (stats.get("goals_for", 0) == 0 and stats.get("goals_against", 0) == 0)) and recent_rates.get("n", 0) >= 3:
            gf = recent_rates["avg_gf"] * 10.0
            ga = recent_rates["avg_ga"] * 10.0
            stats = {
                "goals_for": max(0.0, gf),
                "goals_against": max(0.0, ga),
                "shots_on_target": stats.get("shots_on_target", 0) if stats else 0,
                "played": int(recent_rates.get("n", 0)),
                "expected_goals": max(0.1, gf * 0.92),
                "expected_goals_against": max(0.1, ga * 0.92),
            }

        if stats and stats.get("played", 0) and stats.get("goals_for", 0) is not None:
            gp = max(1, int(stats.get("played", 1)))
            stats.setdefault("expected_goals", float(stats.get("goals_for", 0)) * 0.92)
            stats.setdefault("expected_goals_against", float(stats.get("goals_against", 0)) * 0.92)

        self.cache.set(cache_key, stats, ttl_hours=12)
        return stats

    def _fetch_team_position(self, team_id: Optional[int], league_api_id: int, season: int) -> Dict[str, Any]:
        """Fetch team's current league position."""
        if not team_id or not league_api_id:
            return {}
        try:
            if "api_sports" in self.clients:
                return self.clients["api_sports"].fetch_team_position(team_id, league_api_id, season)
        except Exception:
            pass
        return {}

    def _cached_soccerstats_league_table(self, league_code: str) -> List[Dict[str, Any]]:
        cache_key = f"soccerstats_table_{league_code}"
        cached = self.cache.get(cache_key, ttl_hours=12)
        if cached:
            return cached
        rows = soccerstats_standings.fetch_league_table(league_code, cache=self.cache)
        self.cache.set(cache_key, rows, ttl_hours=12)
        return rows

    def _cached_wikipedia_league_table(self, league_code: str) -> List[Dict[str, Any]]:
        """One Wikipedia standings parse per league per ~12h (disk cache)."""
        sk = wiki_standings._season_wiki_title_part()
        cache_key = f"wiki_stand_{league_code}_{sk}"
        cached = self.cache.get(cache_key, ttl_hours=12)
        if cached is not None:
            return cached if isinstance(cached, list) else []
        rows = wiki_standings.fetch_league_table(league_code)
        self.cache.set(cache_key, rows, ttl_hours=12)
        return rows

    def _fetch_team_recent_matches(
        self,
        team_id: Optional[int],
        limit: int = 10,
        fdo_comp: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Last finished matches: API-Sports when ids match; else Football-Data.org for FDO fixture ids."""
        if not team_id:
            return []

        provider = "fdo" if fdo_comp else "api"
        cache_key = f"team_recent_{provider}_{team_id}"
        cached = self.cache.get(cache_key, ttl_hours=4)
        if cached:
            return cached

        matches: List[Dict[str, Any]] = []
        if "api_sports" in self.clients:
            try:
                matches = self.clients["api_sports"].fetch_team_last_matches(team_id, limit=limit)
            except Exception:
                pass

        if not matches and fdo_comp and "football_data_org" in self.clients:
            try:
                raw = self.clients["football_data_org"].fetch_team_matches(int(team_id), limit)
                for m in raw or []:
                    norm = _fdo_match_to_recent_format(m)
                    if norm:
                        matches.append(norm)
            except Exception:
                pass

        if matches:
            self.cache.set(cache_key, matches, ttl_hours=4)
        return matches

    def _fetch_expected_goals(
        self,
        fixture_id: Optional[int],
        home_rates: Dict[str, float],
        away_rates: Dict[str, float],
        league_strength: float,
    ) -> Tuple[float, float, str]:
        """Expected goals from APIs; fall back to attack vs defence estimates from recent real results.

        Returns (xg_home, xg_away, source_tag) where source_tag is one of:
        api_fixture_xg, stats_api_xg, mixed_api_goals_proxy, goals_proxy.
        """
        if not fixture_id:
            h, a = self._lambda_from_rates(home_rates, away_rates, league_strength)
            return (h, a, "goals_proxy")

        cache_key = f"xg_data_v2_{fixture_id}"
        cached = self.cache.get(cache_key, ttl_hours=6)
        if isinstance(cached, (list, tuple)) and len(cached) >= 3:
            return float(cached[0]), float(cached[1]), str(cached[2])

        xg_home: Optional[float] = None
        xg_away: Optional[float] = None
        from_stats_api = False
        filled_via_api_fixture = False

        if "stats_api" in self.clients and not _effective_skip_rapid_stats_xg(self.clients):
            try:
                xg_data = self.clients["stats_api"].fetch_xg_data(fixture_id)
                resp = xg_data.get("response") if isinstance(xg_data, dict) else None
                if resp:
                    for stat in resp:
                        tname = (stat.get("team", {}) or {}).get("name", "")
                        stats_list = stat.get("statistics") or []
                        val_raw = stats_list[0].get("value") if stats_list else None
                        try:
                            val = float(val_raw)
                        except (TypeError, ValueError):
                            continue
                        if tname == "Home":
                            xg_home = val
                        else:
                            xg_away = val
                    if xg_home and xg_away:
                        from_stats_api = True
            except Exception:
                pass

        if "api_sports" in self.clients:
            try:
                fixture_data = self.clients["api_sports"].fetch_fixture(int(fixture_id))
                stats_list = fixture_data.get("statistics") or []
                if len(stats_list) >= 2:
                    for block in stats_list:
                        team = block.get("team", {}) or {}
                        tid = team.get("id")
                        xg_block = block.get("expected_goals") or {}
                        raw = xg_block.get("value") or xg_block.get("total")
                        if raw is None:
                            continue
                        try:
                            val = float(raw)
                        except (TypeError, ValueError):
                            continue
                        hid = fixture_data.get("teams", {}).get("home", {}).get("id")
                        if tid == hid:
                            xg_home = val
                            filled_via_api_fixture = True
                        else:
                            xg_away = val
                            filled_via_api_fixture = True
            except Exception:
                pass

        if xg_home is not None and xg_away is not None and xg_home > 0 and xg_away > 0:
            if filled_via_api_fixture:
                tag = "api_fixture_xg"
            elif from_stats_api:
                tag = "stats_api_xg"
            else:
                tag = "mixed_api_goals_proxy"
            result = (float(xg_home), float(xg_away), tag)
            self.cache.set(cache_key, result, ttl_hours=6)
            return result

        est_h, est_a = self._lambda_from_rates(home_rates, away_rates, league_strength)
        use_h = xg_home if xg_home and xg_home > 0 else est_h
        use_a = xg_away if xg_away and xg_away > 0 else est_a
        had_any = (xg_home is not None and xg_home > 0) or (xg_away is not None and xg_away > 0)
        tag = "mixed_api_goals_proxy" if had_any else "goals_proxy"
        out = (float(use_h), float(use_a), tag)
        self.cache.set(cache_key, out, ttl_hours=6)
        return out

    @staticmethod
    def _lambda_from_rates(home_rates: Dict[str, float], away_rates: Dict[str, float], league_strength: float) -> Tuple[float, float]:
        """Derive Poisson lambdas from recent goals (real matches) when API xG is unavailable."""
        base = 1.15 * max(0.55, min(1.45, float(league_strength or 1.0)))
        hgf = home_rates.get("avg_gf") or 0.0
        hga = home_rates.get("avg_ga") or 0.0
        agf = away_rates.get("avg_gf") or 0.0
        aga = away_rates.get("avg_ga") or 0.0
        if home_rates.get("n", 0) < 2 and away_rates.get("n", 0) < 2:
            return base * 1.1, base * 0.95
        lam_h = max(0.35, min(3.8, (hgf + aga) / 2.0 * (0.85 + 0.15 * float(league_strength or 1.0))))
        lam_a = max(0.35, min(3.8, (agf + hga) / 2.0 * (0.85 + 0.15 * float(league_strength or 1.0))))
        return lam_h, lam_a

    def _fetch_odds_bundle(self, fixture: Dict[str, Any], league_code: str) -> Dict[str, Any]:
        """Primary + secondary 1X2 sources, cross-implied delta, and side markets from API-Football."""
        fixture_id = fixture.get("fixture", {}).get("id")
        home_name = (fixture_team_name(fixture, "home") or "").lower()
        away_name = (fixture_team_name(fixture, "away") or "").lower()

        cache_key = f"odds_bundle_{fixture_id}_{league_code}"
        cached = self.cache.get(cache_key, ttl_hours=1)
        if isinstance(cached, dict):
            return cached

        oa_home = oa_draw = oa_away = None
        as_home = as_draw = as_away = None
        all_bookmakers: List = []
        api_odds_raw: List[Dict[str, Any]] = []

        if "odds_api" in self.clients and not _effective_skip_odds_api(self.clients):
            try:
                events = self.clients["odds_api"].fetch_odds_for_league(league_code)
                for event in events or []:
                    eh = (event.get("home_team") or "").lower()
                    ea = (event.get("away_team") or "").lower()
                    if len(home_name) >= 3 and len(away_name) >= 3:
                        if not (
                            (home_name[:4] in eh or eh[:4] in home_name)
                            and (away_name[:4] in ea or ea[:4] in away_name)
                        ):
                            continue
                    home_odds_list, draw_odds_list, away_odds_list = [], [], []
                    for bm in event.get("bookmakers", []) or []:
                        bm_name = bm.get("name", "")
                        bm_odds: Dict[str, Any] = {"bookmaker": bm_name, "source": "the_odds_api"}
                        for market in bm.get("markets", []):
                            if market.get("key") != "h2h":
                                continue
                            for o in market.get("outcomes", []):
                                oname = (o.get("name") or "").lower()
                                try:
                                    price = float(o.get("price", 0) or 0)
                                except (TypeError, ValueError):
                                    continue
                                if price <= 1.0:
                                    continue
                                if "draw" in oname:
                                    bm_odds["draw"] = price
                                    draw_odds_list.append(price)
                                elif home_name[:4] in oname or oname[:4] in home_name:
                                    bm_odds["home"] = price
                                    home_odds_list.append(price)
                                else:
                                    bm_odds["away"] = price
                                    away_odds_list.append(price)
                        if len(bm_odds) > 1:
                            all_bookmakers.append(bm_odds)
                    if home_odds_list:
                        oa_home = max(home_odds_list)
                    if draw_odds_list:
                        oa_draw = max(draw_odds_list)
                    if away_odds_list:
                        oa_away = max(away_odds_list)
                    if oa_home and oa_draw and oa_away:
                        break
            except Exception:
                pass

        if "api_sports" in self.clients and fixture_id:
            try:
                api_odds_raw = self.clients["api_sports"].fetch_odds(int(fixture_id))
                if api_odds_raw:
                    for entry in api_odds_raw:
                        for bm in entry.get("bookmakers", []) or []:
                            bets = bm.get("bets", []) or []
                            for bet in bets:
                                if bet.get("name") != "Match Winner":
                                    continue
                                values = bet.get("values", []) or []
                                bm_entry = {"bookmaker": bm.get("name", ""), "source": "api_sports"}
                                for v in values:
                                    val = (v.get("value") or "").lower()
                                    try:
                                        price = float(v.get("odd", 0) or 0)
                                    except (TypeError, ValueError):
                                        continue
                                    if price <= 1.0:
                                        continue
                                    if val == "home":
                                        bm_entry["home"] = price
                                        as_home = price if as_home is None else max(as_home, price)
                                    elif val == "draw":
                                        bm_entry["draw"] = price
                                        as_draw = price if as_draw is None else max(as_draw, price)
                                    elif val == "away":
                                        bm_entry["away"] = price
                                        as_away = price if as_away is None else max(as_away, price)
                                if len(bm_entry) > 1:
                                    all_bookmakers.append(bm_entry)
            except Exception:
                pass

        side = _parse_api_sports_side_markets(api_odds_raw)
        market_odds: Dict[str, Any] = {}
        if side.get("btts_yes") or side.get("btts_no"):
            market_odds["btts"] = {k: v for k, v in (("yes", side.get("btts_yes")), ("no", side.get("btts_no"))) if v}
        if side.get("over_2_5") or side.get("under_2_5"):
            market_odds["totals_2_5"] = {
                k: v for k, v in (("over", side.get("over_2_5")), ("under", side.get("under_2_5"))) if v
            }
        if side.get("over_1_5") or side.get("under_1_5"):
            market_odds["totals_1_5"] = {
                k: v for k, v in (("over", side.get("over_1_5")), ("under", side.get("under_1_5"))) if v
            }
        if side.get("over_3_5") or side.get("under_3_5"):
            market_odds["totals_3_5"] = {
                k: v for k, v in (("over", side.get("over_3_5")), ("under", side.get("under_3_5"))) if v
            }

        as_ok = bool(as_home and as_draw and as_away and as_home > 1 and as_draw > 1 and as_away > 1)
        oa_ok = bool(oa_home and oa_draw and oa_away and oa_home > 1 and oa_draw > 1 and oa_away > 1)
        cross = 0.0
        if as_ok and oa_ok:
            cross = _max_implied_delta_pct(as_home, as_draw, as_away, oa_home, oa_draw, oa_away)
            ph, pd, pa = max(as_home, oa_home), max(as_draw, oa_draw), max(as_away, oa_away)
            sh, sd, sa = oa_home, oa_draw, oa_away
            primary_src = "merged_best"
        elif as_ok:
            ph, pd, pa = as_home, as_draw, as_away
            sh, sd, sa = oa_home, oa_draw, oa_away
            primary_src = "api_sports"
        elif oa_ok:
            ph, pd, pa = oa_home, oa_draw, oa_away
            sh, sd, sa = as_home, as_draw, as_away
            primary_src = "the_odds_api"
        else:
            ph = as_home if as_home else oa_home
            pd = as_draw if as_draw else oa_draw
            pa = as_away if as_away else oa_away
            sh = oa_home if ph == as_home and oa_home else (as_home if ph == oa_home and as_home else None)
            sd = oa_draw if pd == as_draw and oa_draw else (as_draw if pd == oa_draw and as_draw else None)
            sa = oa_away if pa == as_away and oa_away else (as_away if pa == oa_away and as_away else None)
            primary_src = "partial"

        line_shop = compute_best_line_from_bookmakers(all_bookmakers)
        best_1x2 = line_shop.get("best_odds_1x2") or {}
        bh = best_1x2.get("home")
        bd = best_1x2.get("draw")
        ba = best_1x2.get("away")
        best_ok = bool(bh and bd and ba and bh > 1 and bd > 1 and ba > 1)
        if best_ok:
            ph, pd, pa = bh, bd, ba
            primary_src = "line_shop_best"
        cross_book = float(line_shop.get("odds_cross_book_max_implied_diff_pct") or 0.0)
        cross = max(float(cross), cross_book)

        avail = bool(ph and pd and pa and ph > 1 and pd > 1 and pa > 1)
        bundle = {
            "odds_home": ph,
            "odds_draw": pd,
            "odds_away": pa,
            "odds_available": avail,
            "all_bookmaker_odds": all_bookmakers,
            "odds_secondary": {"home": sh, "draw": sd, "away": sa},
            "odds_cross_max_implied_diff_pct": cross,
            "odds_cross_book_max_implied_diff_pct": cross_book,
            "odds_primary_source": primary_src,
            "market_odds": market_odds,
            "best_odds_1x2": line_shop.get("best_odds_1x2"),
            "best_odds_source": line_shop.get("best_odds_source"),
            "sharp_anchor_implied": line_shop.get("sharp_anchor_implied") or {},
        }
        self.cache.set(cache_key, bundle, ttl_hours=1)
        return bundle

    def get_all_clients(self) -> Dict[str, Any]:
        """Return all initialized API clients."""
        return self.clients
