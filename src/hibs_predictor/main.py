import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from hibs_predictor.api_clients import ApiSportsFootballClient
from hibs_predictor.config import LEAGUES
from hibs_predictor.features import build_feature_matrix, normalize_strength
from hibs_predictor.model import train_model, save_model, load_model, predict_probabilities


def _project_root() -> str:
    """Repository root (parent of `src/`), same as DataAggregator."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _load_env_from_project() -> None:
    root = _project_root()
    load_dotenv(os.path.join(root, ".env"))
    load_dotenv(os.path.join(root, ".env.local"))


def load_keys() -> Dict[str, str]:
    _load_env_from_project()
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


def _outcome_from_goals(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "H"
    if home_goals < away_goals:
        return "A"
    return "D"


def _match_winner_odds_from_api_sports(odds_data: List[Dict[str, Any]]) -> Optional[Tuple[float, float, float]]:
    for entry in odds_data or []:
        for bm in entry.get("bookmakers", []) or []:
            for bet in bm.get("bets", []) or []:
                if bet.get("name") != "Match Winner":
                    continue
                oh = od = oa = None
                for v in bet.get("values", []) or []:
                    val = (v.get("value") or "").lower()
                    try:
                        price = float(v.get("odd", 0) or 0)
                    except (TypeError, ValueError):
                        continue
                    if price <= 1.0:
                        continue
                    if val == "home":
                        oh = price
                    elif val == "draw":
                        od = price
                    elif val == "away":
                        oa = price
                if oh and od and oa:
                    return oh, od, oa
    return None


def fetch_remote_fixtures() -> List[Dict[str, Any]]:
    """Finished fixtures with real closing Match Winner odds from API-Football (no fabricated rows)."""
    keys = load_keys()
    if not keys["api_sports"]:
        return []

    client = ApiSportsFootballClient(keys["api_sports"])
    now = datetime.now(timezone.utc)
    date_to = now.strftime("%Y-%m-%d")
    date_from = (now - timedelta(days=45)).strftime("%Y-%m-%d")
    season = now.year if now.month >= 7 else now.year - 1

    rows: List[Dict[str, Any]] = []
    # Finished fixtures + Match Winner odds for sklearn training (wider league mix).
    train_codes = (
        "EPL",
        "SCOTLAND",
        "CHAMPIONSHIP",
        "LEAGUE_ONE",
        "LA_LIGA",
        "SERIE_A",
        "BUNDESLIGA",
        "LIGUE_1",
        "EREDIVISIE",
        "UCL",
    )
    for code in train_codes:
        league = LEAGUES.get(code)
        if not league or not league.get("api_sports_id"):
            continue
        league_id = int(league["api_sports_id"])
        try:
            raw = client.fetch_fixtures_by_league(
                league_id, season, status="FT", date_from=date_from, date_to=date_to
            )
        except Exception:
            continue
        for fx in (raw or [])[:80]:
            goals = fx.get("goals") or {}
            try:
                hg = int(goals.get("home"))
                ag = int(goals.get("away"))
            except (TypeError, ValueError):
                continue
            fid = (fx.get("fixture") or {}).get("id")
            if not fid:
                continue
            try:
                odds_raw = client.fetch_odds(int(fid))
            except Exception:
                continue
            triple = _match_winner_odds_from_api_sports(odds_raw)
            if not triple:
                continue
            oh, od, oa = triple
            inv = (1.0 / oh) + (1.0 / od) + (1.0 / oa)
            home_strength = max(0.05, min(0.95, (1.0 / oh) / inv))
            away_strength = max(0.05, min(0.95, (1.0 / oa) / inv))
            rows.append(
                {
                    "home_strength": home_strength,
                    "away_strength": away_strength,
                    "odds_home": oh,
                    "odds_draw": od,
                    "odds_away": oa,
                    "league": league.get("name", code),
                    "result": _outcome_from_goals(hg, ag),
                }
            )

    return rows


def run_train(use_sample: bool = False) -> None:
    _load_env_from_project()
    if use_sample:
        fixtures = sample_fixtures()
    else:
        fixtures = fetch_remote_fixtures()
        if not fixtures:
            print(
                "No training data: need API_SPORTS_FOOTBALL_KEY with quota for fixtures + odds, "
                "or run: python3 -m hibs_predictor.main train --use-sample"
            )
            sys.exit(1)

    X, y = build_feature_matrix(fixtures)
    pipeline, score = train_model(X, y)
    model_path = os.path.join(_project_root(), "model.joblib")
    save_model(pipeline, model_path)
    print(f"Trained model saved to {model_path} with test accuracy: {score:.3f}")


def run_predict(args: argparse.Namespace) -> None:
    import numpy as np

    _load_env_from_project()
    model_path = os.path.join(_project_root(), "model.joblib")
    pipeline = load_model(model_path)
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
    arr = np.asarray(probs, dtype=float).ravel()
    if arr.size != 3:
        print(f"Prediction for {args.home} vs {args.away} in {args.league}:")
        print(f"  Model output has {arr.size} class(es): {arr}. Expected 3 (home/draw/away).")
        print("  Train with: python3 -m hibs_predictor.main train (API fixtures + odds) for full 1X2.")
        return
    ph, pd, pa = float(arr[0]), float(arr[1]), float(arr[2])
    print(f"Prediction for {args.home} vs {args.away} in {args.league}:")
    print(f"  Home win chance: {ph:.2f}")
    print(f"  Draw chance: {pd:.2f}")
    print(f"  Away win chance: {pa:.2f}")


def run_setup() -> None:
    """Interactive setup for API keys."""
    import sys
    print("\n🟤💛 hibs-bet — First-Time Setup\n")
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
        print("\n🟤💛 hibs-bet Web Dashboard")
        print("Opening http://127.0.0.1:5000\n")
        app.run(debug=False, port=5000, host="127.0.0.1")
    except ImportError:
        print("Flask not installed. Run: pip install -r requirements.txt")


def run_pred_log_sync(args: argparse.Namespace) -> None:
    """Backfill finished scores into rows logged by prediction_log (API-Football)."""
    load_dotenv()
    from hibs_predictor.prediction_log import _db_path, _enabled, sync_finished_results

    if not _enabled() and not os.path.isfile(_db_path()):
        print(
            "No prediction audit database found. Enable HIBS_PREDICTION_LOG_ENABLED=1, "
            "then use the web dashboard or predictions so snapshots are created."
        )
        sys.exit(1)
    from hibs_predictor.data_aggregator import DataAggregator

    agg = DataAggregator()
    if "api_sports" not in agg.clients:
        print("API_SPORTS_FOOTBALL_KEY is required to sync finished results.")
        sys.exit(1)
    n = sync_finished_results(
        agg.clients["api_sports"].fetch_fixture,
        max_fixtures=int(args.max_fixtures),
        min_after_kickoff_hours=float(args.min_after_kickoff_hours),
    )
    print(f"Updated snapshot row(s): {n}")


def run_pred_log_report(args: argparse.Namespace) -> None:
    """Print JSON summary of scored prediction snapshots (Brier, log loss, buckets)."""
    import json

    load_dotenv()
    from hibs_predictor.prediction_log import export_scored_csv, report_summary_dict

    rep = report_summary_dict()
    if getattr(args, "csv", None):
        rep["csv_rows_written"] = export_scored_csv(args.csv)
        rep["csv_path"] = args.csv
    print(json.dumps(rep, indent=2))


def run_pred_log_prune(args: argparse.Namespace) -> None:
    """Delete old prediction_snapshots rows by captured_at (retention)."""
    load_dotenv()
    from hibs_predictor.prediction_log import _db_path, _enabled, prune_old_rows

    if not _enabled() and not os.path.isfile(_db_path()):
        print("No prediction audit database to prune.")
        sys.exit(1)
    n = prune_old_rows(args.days)
    print(f"Deleted {n} snapshot row(s).")


def run_data_sources_probe() -> None:
    """Print JSON reliability probe for APIs + scrapers + StatsBomb open data (needs network)."""
    import json

    from hibs_predictor.data_source_reliability import run_all_probes

    payload = run_all_probes()
    print(json.dumps(payload, indent=2))


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="hibs-bet — UK and European football predictor")
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

    pred_sync = subparsers.add_parser(
        "pred-log-sync",
        help="Backfill FT results into prediction audit DB (needs API_SPORTS_FOOTBALL_KEY)",
    )
    pred_sync.add_argument("--max", dest="max_fixtures", type=int, default=400, help="Max distinct fixtures to poll")
    pred_sync.add_argument(
        "--min-after-kickoff-hours",
        type=float,
        default=2.5,
        help="Skip API calls for fixtures whose kickoff is sooner than this many hours ago",
    )

    pred_report = subparsers.add_parser("pred-log-report", help="Print JSON metrics for scored prediction snapshots")
    pred_report.add_argument(
        "--csv",
        metavar="PATH",
        help="Also write scored rows to CSV at this path",
    )

    pred_prune = subparsers.add_parser("pred-log-prune", help="Delete old rows from prediction audit DB")
    pred_prune.add_argument(
        "--days",
        type=int,
        default=None,
        help="Delete snapshots older than this many days (default: HIBS_PREDICTION_LOG_RETAIN_DAYS)",
    )

    subparsers.add_parser(
        "data-sources-probe",
        help="JSON probe: policy window + reliability of StatsBomb/Understat/FBref/Sofascore/API-Football",
    )

    return parser


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()

    if args.command == "train":
        run_train(use_sample=bool(getattr(args, "use_sample", False)))
    elif args.command == "predict":
        run_predict(args)
    elif args.command == "setup":
        run_setup()
    elif args.command == "web":
        run_web()
    elif args.command == "pred-log-sync":
        run_pred_log_sync(args)
    elif args.command == "pred-log-report":
        run_pred_log_report(args)
    elif args.command == "pred-log-prune":
        run_pred_log_prune(args)
    elif args.command == "data-sources-probe":
        run_data_sources_probe()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
