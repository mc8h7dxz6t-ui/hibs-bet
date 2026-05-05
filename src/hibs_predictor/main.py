import argparse
import os
from typing import Any, Dict, List

from dotenv import load_dotenv

from hibs_predictor.api_clients import ApiSportsFootballClient, FootballDataOrgClient, SportsMonkClient
from hibs_predictor.features import build_feature_matrix, normalize_strength
from hibs_predictor.model import train_model, save_model, load_model, predict_probabilities


def load_keys() -> Dict[str, str]:
    load_dotenv()
    return {
        "football_data_org": os.getenv("FOOTBALL_DATA_ORG_KEY", ""),
        "sportsmonk": os.getenv("SPORTSMONK_KEY", ""),
        "api_sports": os.getenv("API_SPORTS_FOOTBALL_KEY", ""),
    }


def sample_fixtures() -> List[Dict[str, Any]]:
    return [
        {
            "home_strength": 0.72,
            "away_strength": 0.55,
            "odds_home": 2.10,
            "odds_draw": 3.40,
            "odds_away": 3.20,
            "league": "Scottish Premiership",
            "result": "H",
        },
        {
            "home_strength": 0.45,
            "away_strength": 0.68,
            "odds_home": 3.10,
            "odds_draw": 3.30,
            "odds_away": 2.15,
            "league": "EPL",
            "result": "A",
        },
        {
            "home_strength": 0.60,
            "away_strength": 0.60,
            "odds_home": 2.70,
            "odds_draw": 3.10,
            "odds_away": 2.70,
            "league": "Premier League",
            "result": "D",
        },
    ]


def fetch_remote_fixtures() -> List[Dict[str, Any]]:
    keys = load_keys()
    fixtures: List[Dict[str, Any]] = []

    if keys["football_data_org"]:
        client = FootballDataOrgClient(keys["football_data_org"])
        try:
            raw = client.fetch_fixtures("SPL", 2025)
            for match in raw:
                fixtures.append(
                    {
                        "home_strength": 0.6,
                        "away_strength": 0.5,
                        "odds_home": 2.20,
                        "odds_draw": 3.20,
                        "odds_away": 3.40,
                        "league": "Scottish Premiership",
                        "result": match.get("score", {}).get("winner", "D")[:1],
                    }
                )
        except Exception:
            pass

    if not fixtures and keys["api_sports"]:
        client = ApiSportsFootballClient(keys["api_sports"])
        try:
            raw = client.fetch_odds(0)
            for item in raw:
                fixture = item.get("fixture", {})
                markets = item.get("bookmakers", [])
                last_market = markets[0] if markets else {}
                odds = last_market.get("bets", [])
                fixtures.append(
                    {
                        "home_strength": 0.58,
                        "away_strength": 0.62,
                        "odds_home": 2.55,
                        "odds_draw": 3.15,
                        "odds_away": 2.65,
                        "league": "EPL",
                        "result": "D",
                    }
                )
        except Exception:
            pass

    return fixtures


def run_train() -> None:
    fixtures = fetch_remote_fixtures()
    if not fixtures:
        print("No remote fixture data available; using sample Edinburgh/Hibs-style data.")
        fixtures = sample_fixtures()

    X, y = build_feature_matrix(fixtures)
    pipeline, score = train_model(X, y)
    save_model(pipeline)
    print(f"Trained model saved to model.joblib with test accuracy: {score:.3f}")


def run_predict(args: argparse.Namespace) -> None:
    pipeline = load_model()
    fixture = [
        [
            normalize_strength({"pace": args.home_strength, "form": 0.75, "defence": 0.7, "attack": 0.75}),
            normalize_strength({"pace": args.away_strength, "form": 0.68, "defence": 0.65, "attack": 0.7}),
            args.odds_home,
            args.odds_draw,
            args.odds_away,
            0.8,
            args.home_strength - args.away_strength,
            args.home_strength + args.away_strength,
        ]
    ]
    probs = predict_probabilities(pipeline, fixture)[0]
    print(f"Prediction for {args.home} vs {args.away} in {args.league}:")
    print(f"  Home win chance: {probs[0]:.2f}")
    print(f"  Draw chance: {probs[1]:.2f}")
    print(f"  Away win chance: {probs[2]:.2f}")


def run_setup() -> None:
    """Interactive setup for API keys."""
    import sys
    print("\n🟤💛 HibsBetting — First-Time Setup\n")
    print("Get free API keys from:")
    print("  • API-Sports: https://www.api-football.com")
    print("  • Football-Data.org: https://www.football-data.org")
    print("  • SportsMonk: https://www.sportmonks.com\n")

    env_path = ".env"
    env_content = ""

    api_sports_key = input("Enter your API-Sports-Football key (or press Enter to skip): ").strip()
    if api_sports_key:
        env_content += f"API_SPORTS_FOOTBALL_KEY={api_sports_key}\n"

    food_key = input("Enter your Football-Data.org key (or press Enter to skip): ").strip()
    if food_key:
        env_content += f"FOOTBALL_DATA_ORG_KEY={food_key}\n"

    sportsmonk_key = input("Enter your SportsMonk key (or press Enter to skip): ").strip()
    if sportsmonk_key:
        env_content += f"SPORTSMONK_KEY={sportsmonk_key}\n"

    if env_content:
        with open(env_path, "w") as f:
            f.write(env_content)
        print(f"\n✓ Keys saved to {env_path}")
    else:
        print("\n✗ No keys entered. Setup incomplete.")
        sys.exit(1)


def run_web() -> None:
    """Launch the Flask web dashboard."""
    try:
        from hibs_predictor.web import app
        print("\n🟤💛 HibsBetting Web Dashboard")
        print("Opening http://127.0.0.1:5000\n")
        app.run(debug=False, port=5000, host="127.0.0.1")
    except ImportError:
        print("Flask not installed. Run: pip install -r requirements.txt")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hibs-themed bet predictor for UK and European football")
    subparsers = parser.add_subparsers(dest="command")

    train_parser = subparsers.add_parser("train", help="Train the bet predictor")
    train_parser.add_argument("--use-sample", action="store_true", help="Force sample data for training")

    predict_parser = subparsers.add_parser("predict", help="Predict a fixture result")
    predict_parser.add_argument("--home", required=True)
    predict_parser.add_argument("--away", required=True)
    predict_parser.add_argument("--league", default="Scottish Premiership")
    predict_parser.add_argument("--odds-home", type=float, required=True)
    predict_parser.add_argument("--odds-draw", type=float, required=True)
    predict_parser.add_argument("--odds-away", type=float, required=True)
    predict_parser.add_argument("--home-strength", type=float, default=0.65)
    predict_parser.add_argument("--away-strength", type=float, default=0.60)

    setup_parser = subparsers.add_parser("setup", help="Interactive API key setup")
    web_parser = subparsers.add_parser("web", help="Launch Flask web dashboard")

    return parser


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()

    if args.command == "train":
        run_train()
    elif args.command == "predict":
        run_predict(args)
    elif args.command == "setup":
        run_setup()
    elif args.command == "web":
        run_web()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
