from typing import Dict, List, Tuple


def build_feature_matrix(fixtures: List[Dict]) -> Tuple[List[List[float]], List[int]]:
    X = []
    y = []
    league_map = {
        "EPL": 1,
        "Premier League": 1,
        "Scottish Premiership": 0.8,
        "Championship": 0.9,
        "La Liga": 1.0,
        "Bundesliga": 1.0,
        "Serie A": 1.0,
        "Ligue 1": 0.95,
    }

    for fixture in fixtures:
        home_strength = fixture.get("home_strength", 0.5)
        away_strength = fixture.get("away_strength", 0.5)
        odds_home = fixture.get("odds_home", 2.0)
        odds_draw = fixture.get("odds_draw", 3.2)
        odds_away = fixture.get("odds_away", 3.0)
        league = fixture.get("league", "Unknown")
        league_factor = league_map.get(league, 0.85)

        features = [
            home_strength,
            away_strength,
            odds_home,
            odds_draw,
            odds_away,
            home_strength - away_strength,
            home_strength + away_strength,
            league_factor,
        ]

        X.append(features)

        result = fixture.get("result")
        if result == "H":
            y.append(0)
        elif result == "D":
            y.append(1)
        elif result == "A":
            y.append(2)
        else:
            y.append(1)

    return X, y


def normalize_strength(team_stats: Dict[str, float]) -> float:
    pace = team_stats.get("pace", 0.5)
    form = team_stats.get("form", 0.5)
    defence = team_stats.get("defence", 0.5)
    attack = team_stats.get("attack", 0.5)
    return max(0.0, min(1.0, (pace + form + defence + attack) / 4.0))
