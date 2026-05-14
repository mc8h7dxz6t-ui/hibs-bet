"""Refined betting engine with Poisson model, fixed Kelly Criterion, and clear value bet output."""

import math
import os
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

import numpy as np

from hibs_predictor.calibrated_lambdas import calibrated_match_lambdas
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler


class TeamStrengthCalculator:

    @staticmethod
    def calculate_attack_strength(stats: Dict[str, Any]) -> float:
        try:
            goals_for = float(stats.get("goals_for", 0) or 0)
            expected_goals = float(stats.get("expected_goals", goals_for * 0.8) or (goals_for * 0.8))
            attack_power = min(1.0, (goals_for / 50.0) * 0.7 + (expected_goals / 50.0) * 0.3)
            return max(0.0, min(1.0, attack_power))
        except Exception:
            return 0.5

    @staticmethod
    def calculate_defence_strength(stats: Dict[str, Any]) -> float:
        try:
            goals_against = float(stats.get("goals_against", 50) or 50)
            expected_goals_against = float(stats.get("expected_goals_against", goals_against * 0.8) or (goals_against * 0.8))
            defence_power = max(0.0, 1.0 - (goals_against / 50.0))
            xg_defence = max(0.0, 1.0 - (expected_goals_against / 50.0))
            return max(0.0, min(1.0, defence_power * 0.6 + xg_defence * 0.4))
        except Exception:
            return 0.5

    @staticmethod
    def calculate_form_strength(recent_results: List[Dict[str, Any]]) -> float:
        if not recent_results:
            return 0.5
        points = 0
        xg_diff = 0.0
        for match in recent_results[:10]:
            goals = match.get("goals", {})
            home = float(goals.get("home", 0) or 0)
            away = float(goals.get("away", 0) or 0)
            if home > away:
                points += 3
            elif home == away:
                points += 1
            xg = match.get("statistics", [])
            if xg and len(xg) >= 2:
                xg_diff += float(xg[0].get("expected_goals", 0) or 0) - float(xg[1].get("expected_goals", 0) or 0)
        form_score = points / 30.0
        xg_bonus = max(-0.1, min(0.1, xg_diff / 20.0))
        return max(0.0, min(1.0, form_score + xg_bonus))

    @staticmethod
    def calculate_home_away_factor(team_id: int, matches: List[Dict[str, Any]], is_home: bool) -> float:
        relevant = [
            m for m in matches
            if (is_home and m.get("teams", {}).get("home", {}).get("id") == team_id)
            or (not is_home and m.get("teams", {}).get("away", {}).get("id") == team_id)
        ]
        if not relevant:
            return 1.0
        points = 0
        for match in relevant[:10]:
            goals = match.get("goals", {})
            home = float(goals.get("home", 0) or 0)
            away = float(goals.get("away", 0) or 0)
            if (is_home and home > away) or (not is_home and away > home):
                points += 3
            elif home == away:
                points += 1
        win_rate = points / (len(relevant[:10]) * 3.0)
        return max(0.5, min(1.5, 1.0 + (win_rate - 0.33)))

    @staticmethod
    def parse_last_10_results(matches: List[Dict[str, Any]], team_id: Optional[int]) -> List[Dict[str, Any]]:
        """Parse last 10 matches into readable result rows for the UI."""
        if not team_id:
            return []
        results = []
        for match in matches[:10]:
            status_short = (match.get("fixture", {}) or {}).get("status", {}) or {}
            if status_short.get("short") and status_short.get("short") != "FT":
                continue
            teams = match.get("teams", {})
            goals = match.get("goals", {}) or {}
            home_id = teams.get("home", {}).get("id")
            home_name = teams.get("home", {}).get("name", "?")
            away_name = teams.get("away", {}).get("name", "?")
            gh, ga = goals.get("home"), goals.get("away")
            if gh is None or ga is None:
                continue
            home_goals = float(gh)
            away_goals = float(ga)
            is_home = home_id == team_id
            gf, ga = (home_goals, away_goals) if is_home else (away_goals, home_goals)
            opponent = away_name if is_home else home_name
            result = "W" if gf > ga else ("L" if gf < ga else "D")
            fixture_date = match.get("fixture", {}).get("date", "") or ""
            results.append({
                "result": result,
                "score": f"{int(gf)}-{int(ga)}",
                "opponent": opponent,
                "home_away": "H" if is_home else "A",
                "date": fixture_date[:10],
            })
        return results


class OddsAnalyzer:

    @staticmethod
    def decimal_to_probability(decimal_odds: float) -> float:
        if decimal_odds <= 1.0:
            return 0.0
        return 1.0 / decimal_odds

    @staticmethod
    def kelly_criterion(win_probability: float, decimal_odds: float, fraction: float = 0.25) -> Dict[str, Any]:
        """
        Fractional Kelly Criterion as human-readable betting guidance.
        Returns suggested_percent of bankroll, a confidence label, and plain English explanation.
        """
        if decimal_odds <= 1.0 or win_probability <= 0:
            return {
                "raw_fraction": 0.0,
                "suggested_percent": 0.0,
                "confidence_label": "Skip",
                "example_stake": "\u00a30.00",
                "explanation": "No edge detected \u2014 skip this bet.",
            }
        b = decimal_odds - 1.0
        q = 1.0 - win_probability
        kelly = max(0.0, (win_probability * b - q) / b)
        capped = min(0.10, kelly * fraction)
        suggested_percent = round(capped * 100, 1)
        example_stake = round(100 * capped, 2)
        if suggested_percent >= 5.0:
            label, explanation = "Strong", f"Strong edge. Stake ~{suggested_percent}% of bankroll (e.g. \u00a3{example_stake:.2f} per \u00a3100)."
        elif suggested_percent >= 2.5:
            label, explanation = "Moderate", f"Moderate edge. Stake ~{suggested_percent}% of bankroll (e.g. \u00a3{example_stake:.2f} per \u00a3100)."
        elif suggested_percent > 0:
            label, explanation = "Cautious", f"Small edge. Stake ~{suggested_percent}% of bankroll (e.g. \u00a3{example_stake:.2f} per \u00a3100)."
        else:
            label, explanation = "Skip", "No positive edge \u2014 skip this bet."
        return {
            "raw_fraction": round(kelly, 4),
            "suggested_percent": suggested_percent,
            "confidence_label": label,
            "example_stake": f"\u00a3{example_stake:.2f}",
            "explanation": explanation,
        }

    @staticmethod
    def identify_value_bets(
        model_probabilities: Dict[str, float],
        bookmaker_odds: Dict[str, float],
        margin: float = 0.04,
    ) -> Dict[str, Any]:
        value_bets = {}
        for outcome, model_prob in model_probabilities.items():
            if outcome not in bookmaker_odds:
                continue
            odds = bookmaker_odds.get(outcome)
            if odds is None or odds <= 1.0:
                continue
            implied_prob = OddsAnalyzer.decimal_to_probability(odds)
            edge = model_prob - implied_prob
            if edge > margin:
                roi = (edge / implied_prob) * 100
                value_bets[outcome] = {
                    "model_probability": round(model_prob, 4),
                    "model_probability_pct": round(model_prob * 100, 1),
                    "implied_probability": round(implied_prob, 4),
                    "implied_probability_pct": round(implied_prob * 100, 1),
                    "edge": round(edge, 4),
                    "edge_pct": round(edge * 100, 1),
                    "roi_percent": round(roi, 1),
                    "odds": odds,
                    "kelly": OddsAnalyzer.kelly_criterion(model_prob, odds),
                }
        return value_bets


class BettingEngine:

    @staticmethod
    def _blend_1x2_toward_implied(
        probs: Dict[str, float],
        book: Dict[str, float],
        strength: float,
    ) -> Dict[str, float]:
        """Pull 1X2 model mass slightly toward de-vig implied odds (fewer spurious value flags)."""
        if strength <= 0 or not book:
            return probs
        impl: Dict[str, float] = {}
        for k in ("home", "draw", "away"):
            o = book.get(k)
            if o is None or float(o) <= 1.0:
                return probs
            impl[k] = OddsAnalyzer.decimal_to_probability(float(o))
        s = sum(impl.values())
        if s <= 0:
            return probs
        impl = {k: impl[k] / s for k in impl}
        out: Dict[str, float] = {}
        for k in ("home", "draw", "away"):
            e = float(probs.get(k, 1.0 / 3.0))
            out[k] = e * (1.0 - strength) + impl[k] * strength
        t = sum(out.values())
        if t <= 0:
            return probs
        return {k: max(1e-6, v / t) for k, v in out.items()}

    def __init__(self, clients: Dict[str, Any]) -> None:
        self.clients = clients
        self.scaler = StandardScaler()
        self.rf_model = RandomForestClassifier(n_estimators=200, max_depth=12, random_state=42)
        self.gb_model = GradientBoostingClassifier(n_estimators=150, max_depth=5, random_state=42)
        self.is_trained = False

    def _poisson_prob(self, lam: float, k: int) -> float:
        try:
            return (math.exp(-lam) * (lam ** k)) / math.factorial(k)
        except Exception:
            return 0.0

    def _poisson_match_probs(self, xg_home: float, xg_away: float) -> Dict[str, float]:
        max_goals = 8
        home_win = draw = away_win = 0.0
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                p = self._poisson_prob(max(0.1, xg_home), h) * self._poisson_prob(max(0.1, xg_away), a)
                if h > a:
                    home_win += p
                elif h == a:
                    draw += p
                else:
                    away_win += p
        total = home_win + draw + away_win
        if total > 0:
            return {"home": home_win / total, "draw": draw / total, "away": away_win / total}
        return {"home": 0.33, "draw": 0.34, "away": 0.33}

    @staticmethod
    def _fair_decimal_from_prob(p: float) -> float:
        """Decimal odds with no vig from a win probability (for feature fill-in only)."""
        p = max(0.03, min(0.97, float(p)))
        return max(1.02, min(80.0, 1.0 / p))

    @staticmethod
    def _read_1x2_mode() -> str:
        """ensemble: ML+Poisson(raw). calibrated_poisson: HA+Elo-proxy Poisson only. blend_all: weighted mix of three 1X2 heads."""
        m = (os.getenv("HIBS_1X2_MODE") or "ensemble").strip().lower()
        if m in ("calibrated_poisson", "blend_all", "ensemble"):
            return m
        return "ensemble"

    @staticmethod
    def _read_blend_weights() -> Tuple[float, float, float]:
        def _f(name: str, default: float) -> float:
            try:
                return float(os.getenv(name, str(default)))
            except ValueError:
                return default

        w_ml = _f("HIBS_BLEND_W_ML", 1.0 / 3.0)
        w_raw = _f("HIBS_BLEND_W_POISSON_RAW", 1.0 / 3.0)
        w_cal = _f("HIBS_BLEND_W_POISSON_CAL", 1.0 / 3.0)
        s = w_ml + w_raw + w_cal
        if s <= 0:
            return (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0)
        return (w_ml / s, w_raw / s, w_cal / s)

    @staticmethod
    def _merge_three_1x2(
        p_ml: Dict[str, float],
        p_raw: Dict[str, float],
        p_cal: Dict[str, float],
        w_ml: float,
        w_raw: float,
        w_cal: float,
    ) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for k in ("home", "draw", "away"):
            out[k] = (
                float(p_ml.get(k, 0.0)) * w_ml
                + float(p_raw.get(k, 0.0)) * w_raw
                + float(p_cal.get(k, 0.0)) * w_cal
            )
        t = sum(out.values())
        if t <= 0:
            return {"home": 1.0 / 3.0, "draw": 1.0 / 3.0, "away": 1.0 / 3.0}
        return {k: max(1e-9, v / t) for k, v in out.items()}

    def _poisson_btts_probability(self, lam_h: float, lam_a: float) -> float:
        """Independent Poisson: both teams score at least once."""
        lam_h = max(0.08, float(lam_h))
        lam_a = max(0.08, float(lam_a))
        p_home_scores = 1.0 - self._poisson_prob(lam_h, 0)
        p_away_scores = 1.0 - self._poisson_prob(lam_a, 0)
        return max(0.02, min(0.98, p_home_scores * p_away_scores))

    def _poisson_over_goals_probability(self, lam_h: float, lam_a: float, line: float) -> float:
        """P(total goals > line) for half-goal lines (e.g. 2.5 → sum P(T<=2) subtracted from 1)."""
        lam_h = max(0.08, float(lam_h))
        lam_a = max(0.08, float(lam_a))
        max_total = int(math.floor(float(line)))
        p_at_most = 0.0
        cap = 12
        for h in range(cap + 1):
            for a in range(cap + 1):
                if h + a <= max_total:
                    p_at_most += self._poisson_prob(lam_h, h) * self._poisson_prob(lam_a, a)
        p_at_most = min(1.0, p_at_most)
        over = 1.0 - p_at_most
        return max(0.02, min(0.98, over))

    def _poisson_joint_home_win_and_btts(self, lam_h: float, lam_a: float) -> float:
        lam_h = max(0.08, float(lam_h))
        lam_a = max(0.08, float(lam_a))
        s = 0.0
        cap = 10
        for h in range(1, cap + 1):
            for a in range(1, cap + 1):
                if h > a:
                    s += self._poisson_prob(lam_h, h) * self._poisson_prob(lam_a, a)
        return max(0.001, min(0.95, s))

    def _poisson_joint_draw_and_btts(self, lam_h: float, lam_a: float) -> float:
        lam_h = max(0.08, float(lam_h))
        lam_a = max(0.08, float(lam_a))
        s = 0.0
        cap = 10
        for g in range(1, cap + 1):
            s += self._poisson_prob(lam_h, g) * self._poisson_prob(lam_a, g)
        return max(0.001, min(0.95, s))

    def _poisson_joint_away_win_and_btts(self, lam_h: float, lam_a: float) -> float:
        lam_h = max(0.08, float(lam_h))
        lam_a = max(0.08, float(lam_a))
        s = 0.0
        cap = 10
        for h in range(1, cap + 1):
            for a in range(1, cap + 1):
                if a > h:
                    s += self._poisson_prob(lam_h, h) * self._poisson_prob(lam_a, a)
        return max(0.001, min(0.95, s))

    def build_advanced_features(self, fixture: Dict[str, Any]) -> Tuple[List[float], Dict[str, Any]]:
        home = fixture.get("home", {})
        away = fixture.get("away", {})
        home_id = home.get("id", 0) if isinstance(home, dict) else 0
        away_id = away.get("id", 0) if isinstance(away, dict) else 0
        home_name = home.get("name", str(home)) if isinstance(home, dict) else str(home)
        away_name = away.get("name", str(away)) if isinstance(away, dict) else str(away)
        home_stats = fixture.get("home_stats", {})
        away_stats = fixture.get("away_stats", {})
        home_attack = TeamStrengthCalculator.calculate_attack_strength(home_stats)
        home_defence = TeamStrengthCalculator.calculate_defence_strength(home_stats)
        away_attack = TeamStrengthCalculator.calculate_attack_strength(away_stats)
        away_defence = TeamStrengthCalculator.calculate_defence_strength(away_stats)
        home_form = float(fixture.get("home_form", 0.5) or 0.5)
        away_form = float(fixture.get("away_form", 0.5) or 0.5)
        home_home_factor = float(fixture.get("home_home_factor", 1.0) or 1.0)
        away_away_factor = float(fixture.get("away_away_factor", 1.0) or 1.0)
        home_strength = max(0.0, min(1.0, home_attack * 0.4 + home_defence * 0.2 + home_form * 0.3 + (home_home_factor - 1.0) * 0.1))
        away_strength = max(0.0, min(1.0, away_attack * 0.4 + away_defence * 0.2 + away_form * 0.3 + (away_away_factor - 1.0) * 0.1))
        league_factor = float(fixture.get("league_factor", 1.0) or 1.0)
        xg_home = float(fixture.get("xg_home", 1.2) or 1.2)
        xg_away = float(fixture.get("xg_away", 1.1) or 1.1)
        poisson_pre = self._poisson_match_probs(xg_home, xg_away)
        raw_oh = fixture.get("odds_home")
        raw_od = fixture.get("odds_draw")
        raw_oa = fixture.get("odds_away")
        try:
            odds_home = float(raw_oh) if raw_oh is not None and float(raw_oh) > 1.0 else self._fair_decimal_from_prob(poisson_pre["home"])
            odds_draw = float(raw_od) if raw_od is not None and float(raw_od) > 1.0 else self._fair_decimal_from_prob(poisson_pre["draw"])
            odds_away = float(raw_oa) if raw_oa is not None and float(raw_oa) > 1.0 else self._fair_decimal_from_prob(poisson_pre["away"])
        except (TypeError, ValueError):
            odds_home = self._fair_decimal_from_prob(poisson_pre["home"])
            odds_draw = self._fair_decimal_from_prob(poisson_pre["draw"])
            odds_away = self._fair_decimal_from_prob(poisson_pre["away"])
        features = [
            home_strength, away_strength, home_attack, home_defence, away_attack, away_defence,
            home_form, away_form, home_home_factor, away_away_factor,
            odds_home, odds_draw, odds_away,
            OddsAnalyzer.decimal_to_probability(odds_home),
            OddsAnalyzer.decimal_to_probability(odds_draw),
            OddsAnalyzer.decimal_to_probability(odds_away),
            xg_home, xg_away, xg_home - xg_away,
            home_strength - away_strength, home_strength + away_strength,
            league_factor, home_attack - away_defence, away_attack - home_defence,
        ]
        metadata = {
            "home": home_name, "away": away_name,
            "home_id": home_id, "away_id": away_id,
            "home_strength": home_strength, "away_strength": away_strength,
            "home_attack": home_attack, "home_defence": home_defence,
            "away_attack": away_attack, "away_defence": away_defence,
            "home_form": home_form, "away_form": away_form,
            "xg_home": xg_home, "xg_away": xg_away,
        }
        return features, metadata

    def predict_with_confidence(self, fixture: Dict[str, Any]) -> Dict[str, Any]:
        features, metadata = self.build_advanced_features(fixture)
        X = np.array([features])
        try:
            rf_probs = self.rf_model.predict_proba(X)[0]
            gb_probs = self.gb_model.predict_proba(X)[0]
            ml_probs = {
                "home": float(rf_probs[0] * 0.6 + gb_probs[0] * 0.4),
                "draw": float(rf_probs[1] * 0.6 + gb_probs[1] * 0.4),
                "away": float(rf_probs[2] * 0.6 + gb_probs[2] * 0.4),
            }
        except Exception:
            ml_probs = {"home": 0.33, "draw": 0.34, "away": 0.33}
        xg_home = float(metadata["xg_home"])
        xg_away = float(metadata["xg_away"])
        sup_xg_dbg: Optional[Dict[str, Any]] = None
        if os.getenv("HIBS_USE_SUPPLEMENTAL_XG_PRIOR", "0").lower() in ("1", "true", "yes"):
            us = (fixture.get("supplemental") or {}).get("understat_light") or {}
            u_h, u_a = us.get("xg_home"), us.get("xg_away")
            if u_h is not None and u_a is not None:
                try:
                    uh, ua = float(u_h), float(u_a)
                except (TypeError, ValueError):
                    uh = ua = 0.0
                if uh > 0.04 and ua > 0.04 and (uh + ua) < 6.0:
                    try:
                        w = float(os.getenv("HIBS_SUPPLEMENTAL_XG_BLEND", "0.1"))
                    except ValueError:
                        w = 0.1
                    w = max(0.0, min(0.3, w))
                    xg_home = xg_home * (1.0 - w) + uh * w
                    xg_away = xg_away * (1.0 - w) + ua * w
                    metadata["xg_home"] = xg_home
                    metadata["xg_away"] = xg_away
                    sup_xg_dbg = {"blend_weight": w, "understat_xg_home": uh, "understat_xg_away": ua}
        poisson_probs_raw = self._poisson_match_probs(xg_home, xg_away)
        mode = self._read_1x2_mode()
        league_code = str(fixture.get("league") or "")

        lam_cal_h: Optional[float] = None
        lam_cal_a: Optional[float] = None
        cal_dbg: Dict[str, Any] = {}
        poisson_probs_cal: Optional[Dict[str, float]] = None
        blend_w: Optional[Dict[str, float]] = None
        if mode in ("calibrated_poisson", "blend_all"):
            lam_cal_h, lam_cal_a, cal_dbg = calibrated_match_lambdas(
                xg_home,
                xg_away,
                league_code,
                fixture.get("home_position"),
                fixture.get("away_position"),
            )
            poisson_probs_cal = self._poisson_match_probs(lam_cal_h, lam_cal_a)

        if mode == "calibrated_poisson" and poisson_probs_cal is not None:
            ensemble_probs = dict(poisson_probs_cal)
        elif mode == "blend_all" and poisson_probs_cal is not None:
            w_ml, w_raw, w_cal = self._read_blend_weights()
            blend_w = {"ml": round(w_ml, 3), "poisson_raw": round(w_raw, 3), "poisson_calibrated": round(w_cal, 3)}
            ensemble_probs = self._merge_three_1x2(ml_probs, poisson_probs_raw, poisson_probs_cal, w_ml, w_raw, w_cal)
        else:
            poisson_w = 0.78 if not self.is_trained else 0.6
            ml_w = 1.0 - poisson_w
            ensemble_probs = {
                k: ml_probs[k] * ml_w + poisson_probs_raw[k] * poisson_w for k in ["home", "draw", "away"]
            }
            total = sum(ensemble_probs.values())
            if total > 0:
                ensemble_probs = {k: v / total for k, v in ensemble_probs.items()}
        oh_raw, od_raw, oa_raw = fixture.get("odds_home"), fixture.get("odds_draw"), fixture.get("odds_away")
        has_book = bool(
            fixture.get("odds_available")
            or (
                oh_raw is not None and od_raw is not None and oa_raw is not None
                and float(oh_raw) > 1.0 and float(od_raw) > 1.0 and float(oa_raw) > 1.0
            )
        )
        bookmaker_odds: Dict[str, float] = {}
        if has_book:
            try:
                bookmaker_odds = {
                    "home": float(oh_raw),
                    "draw": float(od_raw),
                    "away": float(oa_raw),
                }
            except (TypeError, ValueError):
                bookmaker_odds = {}
                has_book = False
        if has_book and bookmaker_odds:
            try:
                blend = float(os.getenv("HIBS_CALIB_MARKET_BLEND", "0.08"))
            except ValueError:
                blend = 0.08
            ensemble_probs = self._blend_1x2_toward_implied(ensemble_probs, bookmaker_odds, blend)

        use_cal_side = mode == "calibrated_poisson" or (
            mode == "blend_all"
            and (os.getenv("HIBS_SIDE_MARKETS_USE_CALIBRATED", "1").lower() in ("1", "true", "yes"))
        )
        lam_h_side = float(lam_cal_h) if (use_cal_side and lam_cal_h is not None) else float(xg_home)
        lam_a_side = float(lam_cal_a) if (use_cal_side and lam_cal_a is not None) else float(xg_away)

        poisson_btts = self._poisson_btts_probability(lam_h_side, lam_a_side)
        hb = float(fixture.get("home_btts_rate", 0.0) or 0.0)
        ab = float(fixture.get("away_btts_rate", 0.0) or 0.0)
        empirical_btts = (hb + ab) / 2.0 if (hb > 0 or ab > 0) else 0.0
        n_home = int(fixture.get("home_recent_n", 0) or 0)
        n_away = int(fixture.get("away_recent_n", 0) or 0)
        if n_home >= 4 and n_away >= 4:
            btts_prob = max(0.03, min(0.97, poisson_btts * 0.42 + empirical_btts * 0.58))
        elif n_home >= 2 or n_away >= 2:
            w = 0.65
            btts_prob = max(0.03, min(0.97, poisson_btts * w + empirical_btts * (1.0 - w)))
        else:
            btts_prob = poisson_btts
        over15_prob = self._poisson_over_goals_probability(lam_h_side, lam_a_side, 1.5)
        over25_prob = self._poisson_over_goals_probability(lam_h_side, lam_a_side, 2.5)
        over35_prob = self._poisson_over_goals_probability(lam_h_side, lam_a_side, 3.5)
        j_home_btts = self._poisson_joint_home_win_and_btts(lam_h_side, lam_a_side)
        j_draw_btts = self._poisson_joint_draw_and_btts(lam_h_side, lam_a_side)
        j_away_btts = self._poisson_joint_away_win_and_btts(lam_h_side, lam_a_side)
        merged_model = {
            **ensemble_probs,
            "btts_yes": btts_prob,
            "btts_no": max(0.02, min(0.98, 1.0 - btts_prob)),
            "over25": over25_prob,
            "under25": max(0.02, min(0.98, 1.0 - over25_prob)),
            "home_and_btts": j_home_btts,
            "draw_and_btts": j_draw_btts,
            "away_and_btts": j_away_btts,
        }
        merged_book: Dict[str, float] = {}
        if bookmaker_odds:
            for k, v in bookmaker_odds.items():
                if v is not None and float(v) > 1.0:
                    merged_book[str(k)] = float(v)
        mo = fixture.get("market_odds") or {}
        bt = mo.get("btts") or {}
        if bt.get("yes") and float(bt["yes"]) > 1.0:
            merged_book["btts_yes"] = float(bt["yes"])
        if bt.get("no") and float(bt["no"]) > 1.0:
            merged_book["btts_no"] = float(bt["no"])
        to = mo.get("totals_2_5") or {}
        if to.get("over") and float(to["over"]) > 1.0:
            merged_book["over25"] = float(to["over"])
        if to.get("under") and float(to["under"]) > 1.0:
            merged_book["under25"] = float(to["under"])
        to15 = mo.get("totals_1_5") or {}
        if to15.get("over") and float(to15["over"]) > 1.0:
            merged_book["over15"] = float(to15["over"])
        dq_bundle = fixture.get("data_quality") or {}
        dq_pct = float(dq_bundle.get("score_pct") or 0)
        try:
            dq_min_boost = float(os.getenv("HIBS_MIN_DATA_QUALITY_PCT", "0"))
        except ValueError:
            dq_min_boost = 0.0
        try:
            dq_val_req = float(os.getenv("HIBS_VALUE_REQUIRE_DATA_PCT", "0"))
        except ValueError:
            dq_val_req = 0.0
        try:
            base_margin = float(os.getenv("HIBS_VALUE_EDGE_MARGIN", "0.04"))
        except ValueError:
            base_margin = 0.04
        avg_n = (n_home + n_away) / 2.0
        conf_scale = min(1.0, max(0.4, avg_n / 8.0))
        margin = base_margin + (1.0 - conf_scale) * 0.02
        margin = max(0.03, min(0.09, margin))
        if dq_min_boost > 0 and dq_pct < dq_min_boost:
            margin *= 1.0 + min(0.35, (dq_min_boost - dq_pct) / 100.0)
        margin = min(0.14, margin)
        value_bets = OddsAnalyzer.identify_value_bets(merged_model, merged_book, margin=margin) if merged_book else {}
        gated_values = dq_val_req > 0 and dq_pct < dq_val_req
        if gated_values:
            value_bets = {}
        confidence = max(ensemble_probs.values())
        predicted_outcome = max(ensemble_probs, key=ensemble_probs.get)
        best_bet = max(value_bets, key=lambda x: value_bets[x].get("roi_percent", 0)) if value_bets else None
        best_roi = value_bets[best_bet].get("roi_percent", 0.0) if best_bet else 0.0
        market_labels = {
            "home": "1X2 Home",
            "draw": "1X2 Draw",
            "away": "1X2 Away",
            "btts_yes": "BTTS Yes",
            "btts_no": "BTTS No",
            "over25": "Over 2.5",
            "under25": "Under 2.5",
            "home_and_btts": "Home + BTTS",
            "draw_and_btts": "Draw + BTTS",
            "away_and_btts": "Away + BTTS",
        }
        for _k, row in value_bets.items():
            row["market_label"] = market_labels.get(_k, _k.replace("_", " ").title())
        for _ti, (_k, _row) in enumerate(sorted(value_bets.items(), key=lambda kv: -kv[1].get("roi_percent", 0.0))):
            _row["value_tier"] = 1 if _ti == 0 else (2 if _ti == 1 else 3)
        value_highlights = sorted(
            [
                {
                    "key": k,
                    "roi": v.get("roi_percent", 0.0),
                    "label": v.get("market_label", k),
                    "tier": int(v.get("value_tier", 3)),
                }
                for k, v in value_bets.items()
            ],
            key=lambda z: -z["roi"],
        )[:6]
        value_bets_display = []
        for k, v in sorted(value_bets.items(), key=lambda kv: -kv[1].get("roi_percent", 0.0)):
            row = dict(v)
            row["outcome"] = k
            value_bets_display.append(row)
        line_odds: Dict[str, Any] = {}
        for _lk in ("btts_yes", "btts_no", "over25", "under25", "over15"):
            _lv = merged_book.get(_lk)
            try:
                _fv = float(_lv)
                line_odds[_lk] = round(_fv, 2) if _fv > 1.0 else None
            except (TypeError, ValueError):
                line_odds[_lk] = None
        sup = fixture.get("supplemental") or {}
        hsk = sup.get("heavy_skipped") or {}
        dq = fixture.get("data_quality") or {}
        sup_errs = [k for k in sup if str(k).endswith("_error")]
        score_pct = float(dq.get("score_pct") or 0)
        if hsk.get("reason") == "api_strong_skip_heavy":
            pq_summary = "API coverage is strong for this fixture; heavy HTML scrapers were skipped — 1X2 unchanged by FBref/Understat."
        elif score_pct < 70:
            pq_summary = "Lower data coverage; treat multi-market and value hints cautiously."
        elif sup_errs:
            pq_summary = "Some supplemental sources failed; core prediction still uses APIs + Poisson/ML blend."
        else:
            pq_summary = "Typical input mix for this fixture."

        out: Dict[str, Any] = {
            "fixture": f"{metadata['home']} vs {metadata['away']}",
            "home": metadata["home"], "away": metadata["away"],
            "probabilities": {k: round(v, 4) for k, v in ensemble_probs.items()},
            "probabilities_pct": {k: round(v * 100, 1) for k, v in ensemble_probs.items()},
            "predicted_outcome": predicted_outcome,
            "confidence": round(confidence, 4),
            "confidence_pct": round(confidence * 100, 1),
            "bookmaker_odds": bookmaker_odds if bookmaker_odds else {"home": None, "draw": None, "away": None},
            "odds_source_bookmaker": has_book,
            "value_bets": value_bets,
            "value_bets_display": value_bets_display,
            "value_highlights": value_highlights,
            "line_odds": line_odds,
            "has_any_value": bool(value_bets),
            "best_bet": best_bet,
            "best_bet_roi": round(best_roi, 1),
            "data_quality": dq_bundle if dq_bundle else None,
            "xg_source": fixture.get("xg_source"),
            "value_bets_gated_by_data": gated_values,
            "value_edge_margin_used": round(margin, 4),
            "score_and_btts_pct": {
                "home_win_and_btts": round(j_home_btts * 100, 1),
                "draw_and_btts": round(j_draw_btts * 100, 1),
                "away_win_and_btts": round(j_away_btts * 100, 1),
            },
            "odds_cross_max_implied_diff_pct": float(fixture.get("odds_cross_max_implied_diff_pct") or 0.0),
            "expected_goals_home": round(xg_home, 2),
            "expected_goals_away": round(xg_away, 2),
            "btts_probability": round(btts_prob, 4),
            "btts_probability_pct": round(btts_prob * 100, 1),
            "over15_probability_pct": round(over15_prob * 100, 1),
            "over25_probability_pct": round(over25_prob * 100, 1),
            "over35_probability_pct": round(over35_prob * 100, 1),
            "team_strength_home": round(metadata["home_strength"] * 100, 1),
            "team_strength_away": round(metadata["away_strength"] * 100, 1),
            "form_home": round(metadata["home_form"] * 100, 1),
            "form_away": round(metadata["away_form"] * 100, 1),
            "poisson_probs": {k: round(v * 100, 1) for k, v in poisson_probs_raw.items()},
            "one_x2_mode": mode,
            "supplemental_xg_prior": sup_xg_dbg,
            "prediction_quality_hint": {
                "data_score_pct": dq.get("score_pct"),
                "full_scope": dq.get("full_scope"),
                "supplemental_errors": sup_errs[:10],
                "heavy_scrape": (
                    "skipped:" + str(hsk.get("reason"))
                    if hsk.get("reason")
                    else (
                        "used"
                        if sup.get("understat") or sup.get("fbref_home_squad")
                        else "not_run"
                    )
                ),
                "summary": pq_summary,
            },
            "lambda_side_home": round(lam_h_side, 3),
            "lambda_side_away": round(lam_a_side, 3),
            "lambda_calibration": cal_dbg,
            "blend_weights_1x2": blend_w,
            "poisson_probs_calibrated_pct": (
                {k: round(v * 100, 1) for k, v in poisson_probs_cal.items()} if poisson_probs_cal else None
            ),
        }
        try:
            from hibs_predictor.prediction_log import maybe_log_prediction_snapshot

            maybe_log_prediction_snapshot(fixture, out)
        except Exception:
            pass
        return out

    def train(self, X_train: List[List[float]], y_train: List[int]) -> Tuple[float, float]:
        X_scaled = self.scaler.fit_transform(X_train)
        self.rf_model.fit(X_scaled, y_train)
        self.gb_model.fit(X_scaled, y_train)
        self.is_trained = True
        return self.rf_model.score(X_scaled, y_train), self.gb_model.score(X_scaled, y_train)
