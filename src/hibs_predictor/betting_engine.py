"""Advanced betting engine with multi-API integration for sophisticated analysis."""

import math
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler


class TeamStrengthCalculator:
    """Calculates team strength metrics from multiple data sources."""

    @staticmethod
    def calculate_attack_strength(stats: Dict[str, Any]) -> float:
        """Calculate team attack strength (0-1)."""
        try:
            goals_for = stats.get("goals_for", 0)
            shots_on_target = stats.get("shots_on_target", 1)
            expected_goals = stats.get("expected_goals", goals_for * 0.8)
            
            conversion_rate = goals_for / max(shots_on_target, 1)
            attack_power = min(1.0, (goals_for / 50.0) * 0.7 + (expected_goals / 50.0) * 0.3)
            return max(0.0, min(1.0, attack_power))
        except Exception:
            return 0.5

    @staticmethod
    def calculate_defence_strength(stats: Dict[str, Any]) -> float:
        """Calculate team defence strength (0-1)."""
        try:
            goals_against = stats.get("goals_against", 50)
            shots_on_target_against = stats.get("shots_on_target_against", 1)
            expected_goals_against = stats.get("expected_goals_against", goals_against * 0.8)
            
            defence_power = max(0.0, 1.0 - (goals_against / 50.0))
            xg_defence = max(0.0, 1.0 - (expected_goals_against / 50.0))
            strength = defence_power * 0.6 + xg_defence * 0.4
            return max(0.0, min(1.0, strength))
        except Exception:
            return 0.5

    @staticmethod
    def calculate_form_strength(recent_results: List[Dict[str, Any]]) -> float:
        """Calculate team form strength from last 10 games (0-1)."""
        if not recent_results:
            return 0.5

        points = 0
        xg_diff = 0
        
        for match in recent_results[:10]:
            goals = match.get("goals", {})
            home = goals.get("home", 0)
            away = goals.get("away", 0)
            
            if home > away:
                points += 3
            elif home == away:
                points += 1
            
            xg = match.get("statistics", [])
            if xg:
                team_xg = xg[0].get("expected_goals", 0) if len(xg) > 0 else 0
                opp_xg = xg[1].get("expected_goals", 0) if len(xg) > 1 else 0
                xg_diff += (team_xg - opp_xg)
        
        form_score = points / 30.0
        xg_bonus = max(-0.1, min(0.1, xg_diff / 20.0))
        return max(0.0, min(1.0, form_score + xg_bonus))

    @staticmethod
    def calculate_home_away_factor(team_id: int, matches: List[Dict[str, Any]], is_home: bool) -> float:
        """Calculate home/away performance factor."""
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
            home = goals.get("home", 0)
            away = goals.get("away", 0)
            
            if (is_home and home > away) or (not is_home and away > home):
                points += 3
            elif home == away:
                points += 1
        
        win_rate = points / (len(relevant) * 3.0)
        return max(0.5, min(1.5, 1.0 + (win_rate - 0.33)))


class OddsAnalyzer:
    """Analyzes odds from multiple bookmakers and calculates implied probabilities."""

    @staticmethod
    def decimal_to_probability(decimal_odds: float) -> float:
        """Convert decimal odds to implied probability."""
        if decimal_odds <= 0:
            return 0.0
        return 1.0 / decimal_odds

    @staticmethod
    def probability_to_decimal(probability: float) -> float:
        """Convert probability to decimal odds."""
        if probability <= 0:
            return 1000.0
        return 1.0 / probability

    @staticmethod
    def calculate_best_odds(bookmaker_odds: List[float]) -> float:
        """Get best (lowest) odds from multiple bookmakers."""
        valid_odds = [o for o in bookmaker_odds if o > 1.0]
        return max(valid_odds) if valid_odds else 2.0

    @staticmethod
    def identify_value_bets(
        model_probabilities: Dict[str, float],
        bookmaker_odds: Dict[str, float],
        margin: float = 0.05
    ) -> Dict[str, Any]:
        """Identify value bets where model probability > bookmaker implied probability + margin."""
        value_bets = {}
        
        for outcome, model_prob in model_probabilities.items():
            if outcome not in bookmaker_odds:
                continue
            
            odds = bookmaker_odds[outcome]
            implied_prob = OddsAnalyzer.decimal_to_probability(odds)
            value = model_prob - implied_prob
            
            if value > margin:
                roi = (value / implied_prob) * 100
                value_bets[outcome] = {
                    "model_probability": model_prob,
                    "implied_probability": implied_prob,
                    "value": value,
                    "roi_percent": roi,
                    "odds": odds,
                    "bet_size": OddsAnalyzer.kelly_criterion(model_prob, odds),
                }
        
        return value_bets

    @staticmethod
    def kelly_criterion(win_probability: float, decimal_odds: float, fraction: float = 0.25) -> float:
        """Calculate Kelly Criterion bet size as fraction of bankroll."""
        if decimal_odds <= 1:
            return 0.0
        
        loss_probability = 1 - win_probability
        ratio = (decimal_odds - 1) / (decimal_odds - 1)
        kelly = (win_probability * ratio - loss_probability) / ratio
        
        return max(0.0, min(0.1, kelly * fraction))


class BettingEngine:
    """Comprehensive betting engine combining multiple models and data sources."""

    def __init__(self, clients: Dict[str, Any]) -> None:
        self.clients = clients
        self.scaler = StandardScaler()
        self.rf_model = RandomForestClassifier(n_estimators=200, max_depth=12, random_state=42)
        self.gb_model = GradientBoostingClassifier(n_estimators=150, max_depth=5, random_state=42)
        self.is_trained = False

    def build_advanced_features(self, fixture: Dict[str, Any]) -> Tuple[List[float], Dict[str, Any]]:
        """Build comprehensive feature set from multiple APIs."""
        home = fixture.get("home", {})
        away = fixture.get("away", {})
        
        home_id = home.get("id", 0)
        away_id = away.get("id", 0)
        
        features = []
        metadata = {
            "home": home.get("name", ""),
            "away": away.get("name", ""),
            "home_id": home_id,
            "away_id": away_id,
        }

        home_stats = fixture.get("home_stats", {})
        away_stats = fixture.get("away_stats", {})

        home_attack = TeamStrengthCalculator.calculate_attack_strength(home_stats)
        home_defence = TeamStrengthCalculator.calculate_defence_strength(home_stats)
        away_attack = TeamStrengthCalculator.calculate_attack_strength(away_stats)
        away_defence = TeamStrengthCalculator.calculate_defence_strength(away_stats)

        home_form = fixture.get("home_form", 0.5)
        away_form = fixture.get("away_form", 0.5)

        home_home_factor = fixture.get("home_home_factor", 1.0)
        away_away_factor = fixture.get("away_away_factor", 1.0)

        home_strength = (home_attack * 0.4 + home_defence * 0.2 + home_form * 0.3 + home_home_factor * 0.1)
        away_strength = (away_attack * 0.4 + away_defence * 0.2 + away_form * 0.3 + away_away_factor * 0.1)

        league_factor = fixture.get("league_factor", 1.0)
        
        odds_home = fixture.get("odds_home", 2.0)
        odds_draw = fixture.get("odds_draw", 3.2)
        odds_away = fixture.get("odds_away", 3.0)

        odds_home_prob = OddsAnalyzer.decimal_to_probability(odds_home)
        odds_draw_prob = OddsAnalyzer.decimal_to_probability(odds_draw)
        odds_away_prob = OddsAnalyzer.decimal_to_probability(odds_away)

        xg_home = fixture.get("xg_home", 1.5)
        xg_away = fixture.get("xg_away", 1.2)

        features = [
            home_strength,
            away_strength,
            home_attack,
            home_defence,
            away_attack,
            away_defence,
            home_form,
            away_form,
            home_home_factor,
            away_away_factor,
            odds_home,
            odds_draw,
            odds_away,
            odds_home_prob,
            odds_away_prob,
            xg_home,
            xg_away,
            xg_home - xg_away,
            home_strength - away_strength,
            home_strength + away_strength,
            league_factor,
            home_attack - away_defence,
            away_attack - home_defence,
        ]

        metadata.update({
            "home_strength": home_strength,
            "away_strength": away_strength,
            "home_attack": home_attack,
            "home_defence": home_defence,
            "away_attack": away_attack,
            "away_defence": away_defence,
            "home_form": home_form,
            "away_form": away_form,
            "xg_home": xg_home,
            "xg_away": xg_away,
        })

        return features, metadata

    def predict_with_confidence(self, fixture: Dict[str, Any]) -> Dict[str, Any]:
        """Generate predictions with confidence scores and odds analysis."""
        features, metadata = self.build_advanced_features(fixture)
        
        X = np.array([features])
        
        try:
            rf_probs = self.rf_model.predict_proba(X)[0]
            gb_probs = self.gb_model.predict_proba(X)[0]
        except Exception:
            rf_probs = [0.33, 0.33, 0.33]
            gb_probs = [0.33, 0.33, 0.33]

        ensemble_probs = {
            "home": (rf_probs[0] * 0.6 + gb_probs[0] * 0.4),
            "draw": (rf_probs[1] * 0.6 + gb_probs[1] * 0.4),
            "away": (rf_probs[2] * 0.6 + gb_probs[2] * 0.4),
        }

        bookmaker_odds = {
            "home": fixture.get("odds_home", 2.0),
            "draw": fixture.get("odds_draw", 3.2),
            "away": fixture.get("odds_away", 3.0),
        }

        value_bets = OddsAnalyzer.identify_value_bets(ensemble_probs, bookmaker_odds, margin=0.03)

        confidence = max(ensemble_probs.values())
        predicted_outcome = max(ensemble_probs, key=ensemble_probs.get)

        expected_goals_diff = metadata["xg_home"] - metadata["xg_away"]
        btts_probability = min(0.9, max(0.1, 1.0 - abs(expected_goals_diff) / 4.0))

        return {
            "fixture": f"{metadata['home']} vs {metadata['away']}",
            "home": metadata["home"],
            "away": metadata["away"],
            "probabilities": ensemble_probs,
            "predicted_outcome": predicted_outcome,
            "confidence": confidence,
            "bookmaker_odds": bookmaker_odds,
            "value_bets": value_bets,
            "best_bet": max(value_bets, key=lambda x: value_bets[x].get("roi_percent", 0)) if value_bets else None,
            "best_bet_roi": max((v.get("roi_percent", 0) for v in value_bets.values()), default=0) if value_bets else 0,
            "expected_goals_home": metadata["xg_home"],
            "expected_goals_away": metadata["xg_away"],
            "btts_probability": btts_probability,
            "team_strength_home": metadata["home_strength"],
            "team_strength_away": metadata["away_strength"],
            "form_home": metadata["home_form"],
            "form_away": metadata["away_form"],
        }

    def train(self, X_train: List[List[float]], y_train: List[int]) -> Tuple[float, float]:
        """Train ensemble models."""
        X_scaled = self.scaler.fit_transform(X_train)
        
        self.rf_model.fit(X_scaled, y_train)
        self.gb_model.fit(X_scaled, y_train)
        
        rf_score = self.rf_model.score(X_scaled, y_train)
        gb_score = self.gb_model.score(X_scaled, y_train)
        
        self.is_trained = True
        return rf_score, gb_score
