"""Data aggregator that enriches fixtures with multi-API data."""

import os
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
from hibs_predictor.scrapers.supplemental import collect_supplemental


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
        hid = teams.get("home", {}).get("id")
        home_g = goals.get("home")
        away_g = goals.get("away")
        if home_g is None or away_g is None:
            continue
        try:
            hg = int(home_g)
            ag = int(away_g)
        except (TypeError, ValueError):
            continue
        if hid == team_id:
            gf, ga = hg, ag
        elif teams.get("away", {}).get("id") == team_id:
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


def _parse_api_sports_side_markets(odds_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """BTTS and Over/Under 2.5 from API-Football odds (best decimal per selection)."""
    btts_yes: List[float] = []
    btts_no: List[float] = []
    over25: List[float] = []
    under25: List[float] = []
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
                        if "over 2.5" in val or val in ("o2.5", "over 2.5"):
                            over25.append(p)
                        elif "under 2.5" in val or val in ("u2.5", "under 2.5"):
                            under25.append(p)
    out: Dict[str, Any] = {}
    if btts_yes:
        out["btts_yes"] = max(btts_yes)
    if btts_no:
        out["btts_no"] = max(btts_no)
    if over25:
        out["over_2_5"] = max(over25)
    if under25:
        out["under_2_5"] = max(under25)
    return out


class DataAggregator:
    """Aggregates data from multiple APIs to enrich fixture data."""

    def __init__(self) -> None:
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

        if os.getenv("API_SPORTS_FOOTBALL_KEY"):
            clients["api_sports"] = ApiSportsFootballClient(os.getenv("API_SPORTS_FOOTBALL_KEY", ""))

        if os.getenv("FOOTBALL_DATA_ORG_KEY"):
            clients["football_data_org"] = FootballDataOrgClient(os.getenv("FOOTBALL_DATA_ORG_KEY", ""))

        if os.getenv("SPORTSMONK_KEY"):
            clients["sportsmonk"] = SportsMonkClient(os.getenv("SPORTSMONK_KEY", ""))

        if os.getenv("ODDS_API_KEY"):
            clients["odds_api"] = OddsApiClient(os.getenv("ODDS_API_KEY", ""))

        if os.getenv("STATS_API_KEY"):
            clients["stats_api"] = StatsApiClient(os.getenv("STATS_API_KEY", ""))

        return clients

    def enrich_fixture(self, fixture: Dict[str, Any], league_code: str = "EPL") -> Dict[str, Any]:
        """Enrich a fixture with comprehensive data from multiple sources."""
        fixture_id = fixture.get("fixture", {}).get("id") or fixture.get("id", "")
        cache_key = f"enriched_fixture_{fixture_id}_{league_code}"
        cached = self.cache.get(cache_key, ttl_hours=2)
        if cached:
            return cached

        enriched = dict(fixture)
        league = LEAGUES.get(league_code, {})
        league_api_id = league.get("api_sports_id")
        now = datetime.now()
        season = now.year if now.month >= 7 else now.year - 1

        home_id = fixture.get("teams", {}).get("home", {}).get("id")
        away_id = fixture.get("teams", {}).get("away", {}).get("id")

        enriched["home_recent"] = self._fetch_team_recent_matches(home_id)
        enriched["away_recent"] = self._fetch_team_recent_matches(away_id)

        home_rates = _recent_match_rates(enriched["home_recent"], home_id or 0)
        away_rates = _recent_match_rates(enriched["away_recent"], away_id or 0)
        enriched["home_btts_rate"] = home_rates["btts_rate"]
        enriched["away_btts_rate"] = away_rates["btts_rate"]
        enriched["home_recent_n"] = int(home_rates["n"])
        enriched["away_recent_n"] = int(away_rates["n"])
        enriched["home_over25_rate"] = home_rates["over25_rate"]
        enriched["away_over25_rate"] = away_rates["over25_rate"]
        enriched["home_over15_rate"] = home_rates["over15_rate"]
        enriched["away_over15_rate"] = away_rates["over15_rate"]

        enriched["home_stats"] = self._fetch_team_stats(home_id, league_code, league_api_id, season, home_rates)
        enriched["away_stats"] = self._fetch_team_stats(away_id, league_code, league_api_id, season, away_rates)

        enriched["home_form"] = TeamStrengthCalculator.calculate_form_strength(enriched["home_recent"])
        enriched["away_form"] = TeamStrengthCalculator.calculate_form_strength(enriched["away_recent"])

        enriched["home_home_factor"] = TeamStrengthCalculator.calculate_home_away_factor(
            home_id, enriched["home_recent"], is_home=True
        )
        enriched["away_away_factor"] = TeamStrengthCalculator.calculate_home_away_factor(
            away_id, enriched["away_recent"], is_home=False
        )

        if league_api_id:
            enriched["home_position"] = self._fetch_team_position(home_id, league_api_id, season)
            enriched["away_position"] = self._fetch_team_position(away_id, league_api_id, season)
        else:
            enriched["home_position"] = {}
            enriched["away_position"] = {}

        enriched["xg_home"], enriched["xg_away"] = self._fetch_expected_goals(
            fixture_id, home_rates, away_rates, league.get("strength_factor", 1.0)
        )
        bundle = self._fetch_odds_bundle(fixture, league_code)
        enriched["odds_home"] = bundle["odds_home"]
        enriched["odds_draw"] = bundle["odds_draw"]
        enriched["odds_away"] = bundle["odds_away"]
        enriched["odds_available"] = bundle["odds_available"]
        enriched["all_bookmaker_odds"] = bundle["all_bookmaker_odds"]
        enriched["odds_secondary"] = bundle["odds_secondary"]
        enriched["odds_cross_max_implied_diff_pct"] = bundle["odds_cross_max_implied_diff_pct"]
        enriched["odds_primary_source"] = bundle["odds_primary_source"]
        enriched["market_odds"] = bundle["market_odds"]
        enriched["league_factor"] = league.get("strength_factor", 1.0)
        try:
            fid_int = int(fixture_id) if fixture_id else 0
        except (TypeError, ValueError):
            fid_int = 0
        if fid_int and "api_sports" in self.clients:
            try:
                enriched["fixture_injuries"] = self.clients["api_sports"].fetch_injuries(fid_int)
            except Exception:
                enriched["fixture_injuries"] = []
        else:
            enriched["fixture_injuries"] = []
        enriched["supplemental"] = collect_supplemental(fixture, league_code, enriched)

        self.cache.set(cache_key, enriched, ttl_hours=2)
        return enriched

    def _fetch_team_stats(
        self,
        team_id: Optional[int],
        league_code: str,
        league_api_id: Optional[int] = None,
        season: int = None,
        recent_rates: Optional[Dict[str, float]] = None,
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

    def _fetch_team_recent_matches(self, team_id: Optional[int], limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch team's last matches from API-Sports."""
        if not team_id:
            return []

        cache_key = f"team_recent_{team_id}"
        cached = self.cache.get(cache_key, ttl_hours=4)
        if cached:
            return cached

        matches: List[Dict[str, Any]] = []
        if "api_sports" in self.clients:
            try:
                matches = self.clients["api_sports"].fetch_team_last_matches(team_id, limit=limit)
            except Exception:
                pass

        self.cache.set(cache_key, matches, ttl_hours=4)
        return matches

    def _fetch_expected_goals(
        self,
        fixture_id: Optional[int],
        home_rates: Dict[str, float],
        away_rates: Dict[str, float],
        league_strength: float,
    ) -> Tuple[float, float]:
        """Expected goals from APIs; fall back to attack vs defence estimates from recent real results."""
        if not fixture_id:
            return self._lambda_from_rates(home_rates, away_rates, league_strength)

        cache_key = f"xg_data_{fixture_id}"
        cached = self.cache.get(cache_key, ttl_hours=6)
        if cached:
            return cached

        xg_home: Optional[float] = None
        xg_away: Optional[float] = None

        if "stats_api" in self.clients:
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
                        else:
                            xg_away = val
            except Exception:
                pass

        if xg_home is not None and xg_away is not None and xg_home > 0 and xg_away > 0:
            result = (xg_home, xg_away)
            self.cache.set(cache_key, result, ttl_hours=6)
            return result

        est_h, est_a = self._lambda_from_rates(home_rates, away_rates, league_strength)
        use_h = xg_home if xg_home and xg_home > 0 else est_h
        use_a = xg_away if xg_away and xg_away > 0 else est_a
        out = (use_h, use_a)
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
        home_name = (fixture.get("home", {}).get("name", "") or "").lower()
        away_name = (fixture.get("away", {}).get("name", "") or "").lower()

        cache_key = f"odds_bundle_{fixture_id}_{league_code}"
        cached = self.cache.get(cache_key, ttl_hours=1)
        if isinstance(cached, dict):
            return cached

        oa_home = oa_draw = oa_away = None
        as_home = as_draw = as_away = None
        all_bookmakers: List = []
        api_odds_raw: List[Dict[str, Any]] = []

        if "odds_api" in self.clients:
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

        avail = bool(ph and pd and pa and ph > 1 and pd > 1 and pa > 1)
        bundle = {
            "odds_home": ph,
            "odds_draw": pd,
            "odds_away": pa,
            "odds_available": avail,
            "all_bookmaker_odds": all_bookmakers,
            "odds_secondary": {"home": sh, "draw": sd, "away": sa},
            "odds_cross_max_implied_diff_pct": cross,
            "odds_primary_source": primary_src,
            "market_odds": market_odds,
        }
        self.cache.set(cache_key, bundle, ttl_hours=1)
        return bundle

    def get_all_clients(self) -> Dict[str, Any]:
        """Return all initialized API clients."""
        return self.clients
