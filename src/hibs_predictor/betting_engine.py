"""Refined betting engine with Poisson model, fixed Kelly Criterion, and clear value bet output."""

import math
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

import numpy as np
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
    def parse_last_10_results(matches: List[Dict[str, Any]], team_id: int) -> List[Dict[str, Any]]:
        """Parse last 10 matches into readable result rows for the UI."""
        results = []
        for match in matches[:10]:
            teams = match.get("teams", {})
            goals = match.get("goals", {})
            home_id = teams.get("home", {}).get("id")
            home_name = teams.get("home", {}).get("name", "?")
            away_name = teams.get("away", {}).get("name", "?")
            home_goals = float(goals.get("home", 0) or 0)
            away_goals = float(goals.get("away", 0) or 0)
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
            odds = bookmaker_odds[outcome]
            if odds <= 1.0:
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
        odds_home = float(fixture.get("odds_home", 2.0) or 2.0)
        odds_draw = float(fixture.get("odds_draw", 3.2) or 3.2)
        odds_away = float(fixture.get("odds_away", 3.0) or 3.0)
        xg_home = float(fixture.get("xg_home", 1.5) or 1.5)
        xg_away = float(fixture.get("xg_away", 1.2) or 1.2)
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
        xg_home = metadata["xg_home"]
        xg_away = metadata["xg_away"]
        poisson_probs = self._poisson_match_probs(xg_home, xg_away)
        ensemble_probs = {k: ml_probs[k] * 0.4 + poisson_probs[k] * 0.6 for k in ["home", "draw", "away"]}
        total = sum(ensemble_probs.values())
        if total > 0:
            ensemble_probs = {k: v / total for k, v in ensemble_probs.items()}
        bookmaker_odds = {
            "home": float(fixture.get("odds_home", 2.0) or 2.0),
            "draw": float(fixture.get("odds_draw", 3.2) or 3.2),
            "away": float(fixture.get("odds_away", 3.0) or 3.0),
        }
        value_bets = OddsAnalyzer.identify_value_bets(ensemble_probs, bookmaker_odds, margin=0.04)
        confidence = max(ensemble_probs.values())
        predicted_outcome = max(ensemble_probs, key=ensemble_probs.get)
        btts_prob = min(0.92, max(0.08,
            (1 - self._poisson_prob(xg_home, 0)) * (1 - self._poisson_prob(xg_away, 0))
        ))
        over25_prob = min(0.95, max(0.05,
            1 - sum(
                self._poisson_prob(xg_home, h) * self._poisson_prob(xg_away, a)
                for h in range(3) for a in range(3) if h + a <= 2
            )
        ))
        best_bet = max(value_bets, key=lambda x: value_bets[x].get("roi_percent", 0)) if value_bets else None
        best_roi = value_bets[best_bet].get("roi_percent", 0.0) if best_bet else 0.0
        return {
            "fixture": f"{metadata['home']} vs {metadata['away']}",
            "home": metadata["home"], "away": metadata["away"],
            "probabilities": {k: round(v, 4) for k, v in ensemble_probs.items()},
            "probabilities_pct": {k: round(v * 100, 1) for k, v in ensemble_probs.items()},
            "predicted_outcome": predicted_outcome,
            "confidence": round(confidence, 4),
            "confidence_pct": round(confidence * 100, 1),
            "bookmaker_odds": bookmaker_odds,
            "value_bets": value_bets,
            "best_bet": best_bet,
            "best_bet_roi": round(best_roi, 1),
            "expected_goals_home": round(xg_home, 2),
            "expected_goals_away": round(xg_away, 2),
            "btts_probability_pct": round(btts_prob * 100, 1),
            "over25_probability_pct": round(over25_prob * 100, 1),
            "team_strength_home": round(metadata["home_strength"] * 100, 1),
            "team_strength_away": round(metadata["away_strength"] * 100, 1),
            "form_home": round(metadata["home_form"] * 100, 1),
            "form_away": round(metadata["away_form"] * 100, 1),
            "poisson_probs": {k: round(v * 100, 1) for k, v in poisson_probs.items()},
        }

    def train(self, X_train: List[List[float]], y_train: List[int]) -> Tuple[float, float]:
        X_scaled = self.scaler.fit_transform(X_train)
        self.rf_model.fit(X_scaled, y_train)
        self.gb_model.fit(X_scaled, y_train)
        self.is_trained = True
        return self.rf_model.score(X_scaled, y_train), self.gb_model.score(X_scaled, y_train)
