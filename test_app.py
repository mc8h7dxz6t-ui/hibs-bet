#!/usr/bin/env python3
"""
Quick test runner to verify hibs-bet app components.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_imports():
    """Test all module imports."""
    print("Testing imports...")
    try:
        from hibs_predictor.config import LEAGUES, HIBS_LEAGUE_FOCUS
        from hibs_predictor.api_clients import (
            BaseApiClient,
            ApiSportsFootballClient,
            FootballDataOrgClient,
            SportsMonkClient,
            OddsApiClient,
            StatsApiClient
        )
        from hibs_predictor.cache import Cache
        from hibs_predictor.rate_limiter import RateLimiter
        from hibs_predictor.data_aggregator import DataAggregator
        from hibs_predictor.betting_engine import BettingEngine, TeamStrengthCalculator, OddsAnalyzer
        from hibs_predictor.web import app
        from hibs_predictor.prediction_log import init_db, report_summary_dict
        from hibs_predictor.data_source_policy import policy_summary_dict
        from hibs_predictor.data_source_reliability import run_all_probes
        print("  ✓ All imports successful")
        return True
    except Exception as e:
        print(f"  ✗ Import failed: {e}")
        return False

def test_config():
    """Test configuration."""
    print("\nTesting configuration...")
    try:
        from hibs_predictor.config import LEAGUES, HIBS_LEAGUE_FOCUS
        assert len(LEAGUES) > 0, "No leagues configured"
        assert len(HIBS_LEAGUE_FOCUS) > 0, "No Hibs league focus"
        print(f"  ✓ Config valid: {len(LEAGUES)} leagues, {len(HIBS_LEAGUE_FOCUS)} focus leagues")
        return True
    except Exception as e:
        print(f"  ✗ Config test failed: {e}")
        return False

def test_cache():
    """Test cache system."""
    print("\nTesting cache system...")
    try:
        import tempfile
        import time
        from hibs_predictor.cache import Cache

        cache = Cache()
        cache.set("test_key", {"value": 123})
        retrieved = cache.get("test_key")
        assert retrieved == {"value": 123}, "Cache retrieval mismatch"

        with tempfile.TemporaryDirectory() as tmp:
            c2 = Cache(cache_dir=tmp)
            c2.set("expire_me", 1, ttl_hours=1e-9)
            time.sleep(0.02)
            pruned = c2.prune_stale(legacy_unknown_ttl_hours=1e-9)
            assert pruned >= 1, "prune should remove expired entry"
            assert c2.get("expire_me", ttl_hours=1) is None

            c2.set("fixtures_EPL_v14", {"x": 1})
            c2.set("all_fixtures_5d_v14", {"y": 2})
            c2.set("enriched_fixture_99", {"z": 3})
            assert c2.clear_pattern("fixtures_", prefix=True) == 1
            assert c2.clear_pattern("all_fixtures_", prefix=True) == 1
            assert c2.get("enriched_fixture_99", ttl_hours=24) is not None
            c2.set("keep_a", 1)
            c2.set("keep_b", 2)
            assert c2.clear_all() == 3

        print("  ✓ Cache working correctly")
        return True
    except Exception as e:
        print(f"  ✗ Cache test failed: {e}")
        return False

def test_rate_limiter():
    """Test rate limiter."""
    print("\nTesting rate limiter...")
    try:
        from hibs_predictor.rate_limiter import RateLimiter
        limiter = RateLimiter()
        assert limiter.check_rate_limit("api_sports"), "Rate limit check failed"
        limiter.record_request("api_sports")
        stats = limiter.get_stats("api_sports")
        assert stats["count"] >= 0, "Rate limit stats invalid"
        print("  ✓ Rate limiter working correctly")
        return True
    except Exception as e:
        print(f"  ✗ Rate limiter test failed: {e}")
        return False

def test_flask_routes():
    """Test Flask route definitions."""
    print("\nTesting Flask routes...")
    try:
        from hibs_predictor.web import app

        routes = {rule.rule for rule in app.url_map.iter_rules()}
        required = {
            "/",
            "/api/fixtures",
            "/api/health",
            "/api/value-bets",
            "/api/assistant/snapshot",
            "/api/assistant/recommendations",
            "/api/assistant/chat",
            "/api/audit/summary",
            "/api/cache/clear",
            "/api/insights",
            "/acca",
            "/insights",
            "/status",
        }
        missing = sorted(required - routes)
        if missing:
            print(f"  ✗ Missing routes: {missing}")
            return False
        print(f"  ✓ Flask app loaded with {len(routes)} routes")
        print(f"    Routes: {', '.join(sorted(routes))}")
        return True
    except Exception as e:
        print(f"  ✗ Flask test failed: {e}")
        return False


def test_api_health_prediction_quality():
    """Augmented /api/health includes narrative for UI and betting transparency."""
    print("\nTesting /api/health payload...")
    try:
        from hibs_predictor.web import app

        client = app.test_client()
        res = client.get("/api/health")
        assert res.status_code == 200, res.status_code
        data = res.get_json()
        assert data is not None
        assert "prediction_quality" in data
        pq = data["prediction_quality"]
        assert "headline" in pq and "overall" in pq
        assert "scrapers_policy" in data
        assert "features" in data and isinstance(data["features"], list)
        assert "cache_disk" in data and isinstance(data["cache_disk"], dict)
        assert "files" in data["cache_disk"] and "cache_dir" in data["cache_disk"]
        assert any((f.get("id") == "disk_cache") for f in (data.get("features") or []))
        for row in data.get("apis") or []:
            assert "prediction_effect" in row
        for row in data.get("scrapers") or []:
            assert "prediction_effect" in row
        print("  ✓ /api/health has prediction_quality, scrapers_policy, prediction_effect rows")
        return True
    except Exception as e:
        print(f"  ✗ Health payload test failed: {e}")
        return False


def test_api_cache_clear():
    """POST /api/cache/clear removes fixture cache files and resets health cache."""
    print("\nTesting /api/cache/clear...")
    try:
        import tempfile
        from hibs_predictor.cache import Cache
        from hibs_predictor.web import app, clear_application_caches, _health_cache

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["HIBS_CACHE_DIR"] = tmp
            c = Cache()
            c.set("fixtures_test_league", [1])
            c.set("other_key", [2])
            _health_cache["t"] = 999.0
            _health_cache["payload"] = {"stub": True}
            n = clear_application_caches(all_disk=False)
            assert n >= 1
            assert c.get("fixtures_test_league", ttl_hours=24) is None
            assert c.get("other_key", ttl_hours=24) is not None
            assert _health_cache["payload"] is None

            client = app.test_client()
            res = client.post("/api/cache/clear?all=1")
            assert res.status_code == 200, res.status_code
            body = res.get_json()
            assert body.get("cleared", 0) >= 1
            assert body.get("all_disk") is True
            assert c.get("other_key", ttl_hours=24) is None

        if "HIBS_CACHE_DIR" in os.environ:
            del os.environ["HIBS_CACHE_DIR"]
        print("  ✓ /api/cache/clear clears fixture + optional full disk cache")
        return True
    except Exception as e:
        if "HIBS_CACHE_DIR" in os.environ:
            del os.environ["HIBS_CACHE_DIR"]
        print(f"  ✗ Cache clear API test failed: {e}")
        return False


def test_data_policy():
    """Rolling data window metadata."""
    print("\nTesting data_source_policy...")
    try:
        from hibs_predictor.data_source_policy import policy_summary_dict

        d = policy_summary_dict()
        assert "window_start_utc" in d and "window_end_utc" in d
        print(f"  ✓ Policy window keys present (lookback_days={d.get('lookback_days')})")
        return True
    except Exception as e:
        print(f"  ✗ Policy test failed: {e}")
        return False


def test_main_cli_help():
    """CLI module exposes expected subcommands."""
    print("\nTesting main CLI --help...")
    try:
        import subprocess

        root = os.path.dirname(os.path.abspath(__file__))
        env = {**os.environ, "PYTHONPATH": os.path.join(root, "src")}
        r = subprocess.run(
            [sys.executable, "-m", "hibs_predictor.main", "--help"],
            cwd=root,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        assert r.returncode == 0, r.stderr
        out = (r.stdout or "") + (r.stderr or "")
        for needle in (
            "pred-log-sync",
            "pred-log-report",
            "pred-log-prune",
            "data-sources-probe",
        ):
            assert needle in out, f"missing {needle} in help"
        print("  ✓ main --help lists extended subcommands")
        return True
    except Exception as e:
        print(f"  ✗ CLI help test failed: {e}")
        return False


def test_value_edge_fields():
    """Value bet rows expose edge, ROI, and Kelly; O/U 1.5 and 3.5 in merged model."""
    print("\nTesting value edge fields...")
    try:
        from hibs_predictor.betting_engine import OddsAnalyzer

        vb = OddsAnalyzer.identify_value_bets(
            {"home": 0.55, "over15": 0.72, "over35": 0.40},
            {"home": 2.2, "over15": 1.55, "over35": 3.0},
            margin=0.04,
        )
        assert "home" in vb
        for key in vb:
            assert "edge_pct" in vb[key]
            assert "roi_percent" in vb[key]
            assert "kelly" in vb[key]
        print("  ✓ Value edge fields OK")
        return True
    except Exception as e:
        print(f"  ✗ Value edge fields test failed: {e}")
        return False


def test_bottom_top_underdog_not_home_value():
    """Bottom-vs-top longshot should not be surfaced as home value."""
    print("\nTesting bottom/top underdog value guardrail...")
    try:
        from hibs_predictor.betting_engine import BettingEngine, OddsAnalyzer

        raw_value = OddsAnalyzer.identify_value_bets(
            {"home": 0.18, "draw": 0.20, "away": 0.62},
            {"home": 8.5, "draw": 5.5, "away": 1.33},
            margin=0.04,
        )
        assert "home" in raw_value, "sanity check: raw edge alone would flag the longshot"

        fixture = {
            "home": {"id": 1, "name": "Burnley"},
            "away": {"id": 2, "name": "Arsenal"},
            "league": "EPL",
            "odds_available": True,
            "odds_home": 8.5,
            "odds_draw": 5.5,
            "odds_away": 1.33,
            "home_stats": {"played": 15, "goals_for": 12, "goals_against": 32, "expected_goals": 11, "expected_goals_against": 31},
            "away_stats": {"played": 15, "goals_for": 34, "goals_against": 10, "expected_goals": 33, "expected_goals_against": 12},
            "home_form": 0.12,
            "away_form": 0.84,
            "home_home_factor": 0.82,
            "away_away_factor": 1.28,
            "xg_home": 0.95,
            "xg_away": 1.95,
            "xg_source": "stats_api_xg",
            "home_recent_n": 8,
            "away_recent_n": 8,
            "home_position": {"position": 20},
            "away_position": {"position": 1},
            "data_quality": {"score_pct": 92, "full_scope": True},
        }
        prediction = BettingEngine({}).predict_with_confidence(fixture)

        assert prediction["probabilities"]["home"] < 0.24, prediction["probabilities"]
        assert "home" not in (prediction.get("value_bets") or {})
        assert prediction.get("best_bet") != "home"
        assert "home" in (prediction.get("value_bets_rejected") or {})
        menu = prediction.get("pick_menu") or []
        home_rows = [m for m in menu if m.get("key") == "home_win"]
        assert home_rows and home_rows[0].get("is_value") is False
        print("  ✓ Bottom/top underdog home value suppressed")
        return True
    except Exception as e:
        print(f"  ✗ Bottom/top guardrail test failed: {e}")
        return False


def test_pick_menu():
    """Per-fixture pick menu for summary dropdowns."""
    print("\nTesting pick menu...")
    try:
        from hibs_predictor.match_insight import build_pick_menu, build_structured_insight

        fixture = {
            "home": "Hibs",
            "away": "Hearts",
            "league": "SCOTLAND",
            "home_recent_n": 8,
            "away_recent_n": 8,
            "data_quality": {"score_pct": 82},
        }
        prediction = {
            "probabilities": {"home": 0.45, "draw": 0.28, "away": 0.27},
            "probabilities_pct": {"home": 45.0, "draw": 28.0, "away": 27.0},
            "bookmaker_odds": {"home": 2.1, "draw": 3.4, "away": 3.2},
            "btts_probability": 0.55,
            "btts_probability_pct": 55.0,
            "over25_probability_pct": 52.0,
            "expected_goals_home": 1.4,
            "expected_goals_away": 1.1,
        }
        prediction["structured_insight"] = build_structured_insight(fixture, prediction)
        prediction["value_bets"] = {
            "home": {
                "edge_pct": 5.0,
                "roi_percent": 12.0,
            }
        }
        menu = build_pick_menu(fixture, prediction)
        assert len(menu) >= 3
        assert any(m.get("recommended") for m in menu)
        labels = [m["label"] for m in menu]
        assert any("Home Win" in x for x in labels)
        home_row = next(m for m in menu if m["key"] == "home_win")
        assert home_row.get("is_value") is True
        assert home_row.get("edge_pct") == 5.0
        print("  ✓ Pick menu OK")
        return True
    except Exception as e:
        print(f"  ✗ Pick menu test failed: {e}")
        return False


def test_structured_insight():
    """Structured match card: pick, rationale, odds-only for thin data."""
    print("\nTesting structured match insight...")
    try:
        from hibs_predictor.match_insight import build_structured_insight, should_use_odds_only

        fixture = {
            "home": "Hibs",
            "away": "Hearts",
            "league": "SCOTLAND",
            "home_recent_n": 8,
            "away_recent_n": 8,
            "home_btts_rate": 0.6,
            "away_btts_rate": 0.5,
            "data_quality": {"score_pct": 82},
        }
        prediction = {
            "home": "Hibs",
            "away": "Hearts",
            "probabilities": {"home": 0.45, "draw": 0.28, "away": 0.27},
            "probabilities_pct": {"home": 45.0, "draw": 28.0, "away": 27.0},
            "expected_goals_home": 1.4,
            "expected_goals_away": 1.1,
            "btts_probability": 0.55,
            "over25_probability_pct": 52.0,
            "data_quality": {"score_pct": 82},
        }
        card = build_structured_insight(fixture, prediction)
        assert card["match"] == "Hibs vs Hearts"
        assert card["pick"]
        assert len(card.get("rationale") or []) >= 1
        assert card["mode"] == "prediction"

        thin = dict(fixture)
        thin["league"] = "DENMARK_SL"
        thin["data_quality"] = {"score_pct": 50}
        assert should_use_odds_only(thin, prediction)
        odds_card = build_structured_insight(
            thin,
            {**prediction, "bookmaker_odds": {"home": 2.1, "draw": 3.4, "away": 3.2}},
        )
        assert odds_card["mode"] == "odds_only"
        print("  ✓ Structured insight OK")
        return True
    except Exception as e:
        print(f"  ✗ Structured insight test failed: {e}")
        return False


def test_assistant_chat():
    """NL assistant routes questions to structured blocks."""
    print("\nTesting assistant chat...")
    try:
        from hibs_predictor.assistant_chat import handle_chat

        pkt = {
            "id": 1,
            "home": "Hibs",
            "away": "Hearts",
            "kickoff_time": "15:00",
            "data_quality_pct": 88.0,
            "home_recent_n": 5,
            "away_recent_n": 5,
            "structured_insight": {"mode": "prediction", "match": "Hibs vs Hearts", "pick": "Over 2.5"},
            "pick_menu": [
                {"key": "over_25", "label": "Over 2.5", "model_pct": 61.0, "odds": 1.85},
                {"key": "btts_yes", "label": "BTTS Yes", "model_pct": 62.0, "odds": 1.72},
            ],
            "probability_scores": {"over25_pct": 61, "btts_pct": 62},
            "home_position": {"position": 4, "points": 48, "played": 31, "goal_diff": 10},
            "away_position": {"position": 7, "points": 42, "played": 31, "goal_diff": 2},
            "home_form_summary": {"played": 5, "wins": 3, "draws": 1, "losses": 1, "gf": 8, "ga": 5, "btts": 3, "over25": 3},
            "away_form_summary": {"played": 5, "wins": 2, "draws": 1, "losses": 2, "gf": 6, "ga": 6, "btts": 4, "over25": 2},
        }
        r = handle_chat("stats for Hibs v Hearts", [pkt])
        assert r["intent"] == "stats"
        assert any(b.get("type") == "stats" for b in r["blocks"])
        table = handle_chat("why does the table matter?", [pkt], fixture_id=1)
        assert table["intent"] == "table"
        assert any("Table context" in " ".join(b.get("lines", [])) for b in table["blocks"])
        generic_table = handle_chat("why does the league table matter?", [pkt])
        assert any("Table context matters" in " ".join(b.get("lines", [])) for b in generic_table["blocks"])
        dive = handle_chat("deep dive this game", [pkt], fixture_id=1)
        assert dive["intent"] == "deep_dive"
        dive_lines = " ".join(line for b in dive["blocks"] for line in b.get("lines", []))
        assert "Team news" in dive_lines and "last 5" in dive_lines
        h = handle_chat("help", [pkt])
        assert h["intent"] == "help"
        print("  ✓ Assistant chat OK")
        return True
    except Exception as e:
        print(f"  ✗ Assistant chat test failed: {e}")
        return False


def test_assistant_recommendations():
    """Acca / singles builder respects data-quality gate on synthetic packets."""
    print("\nTesting assistant recommendations...")
    try:
        from hibs_predictor.assistant_recommendations import (
            build_assistant_recommendations,
            is_analyzable,
        )

        good = {
            "id": 1,
            "home": "Hibs",
            "away": "Hearts",
            "kickoff_time": "15:00",
            "data_quality_pct": 88.0,
            "home_recent_n": 5,
            "away_recent_n": 5,
            "structured_insight": {
                "mode": "prediction",
                "match": "Hibs vs Hearts",
                "pick": "Over 2.5",
                "pick_key": "over_25",
            },
            "pick_menu": [
                {"key": "btts_yes", "label": "BTTS Yes", "model_pct": 62.0, "odds": 1.72, "is_value": True, "edge_pct": 4.2},
                {"key": "over_25", "label": "Over 2.5", "model_pct": 61.0, "odds": 1.85, "recommended": True},
                {"key": "over_15", "label": "Over 1.5", "model_pct": 78.0, "odds": 1.28},
                {"key": "home_win", "label": "Home Win", "model_pct": 48.0, "odds": 2.1},
            ],
            "value_bets_display": [
                {"outcome": "btts_yes", "market_label": "BTTS Yes", "odds": 1.72, "edge_pct": 4.2, "roi_percent": 5.1}
            ],
            "has_value_bet": True,
        }
        thin = {
            "id": 2,
            "home": "A",
            "away": "B",
            "data_quality_pct": 40.0,
            "structured_insight": {"mode": "odds_only"},
        }
        assert is_analyzable(good)
        assert not is_analyzable(thin)
        rec = build_assistant_recommendations([good, thin])
        assert rec["deep_dive_summary"]["fixtures_scanned"] == 2
        assert rec["deep_dive_summary"]["fixtures_eligible"] == 1
        assert len(rec["best_singles"]) >= 1
        btts = [a for a in rec["acca_suggestions"] if a["type"] == "btts"]
        assert btts == [], "one leg cannot form 3-leg acca"
        print("  ✓ Assistant recommendations OK")
        return True
    except Exception as e:
        print(f"  ✗ Assistant recommendations test failed: {e}")
        return False


def test_insights_and_bet_builders():
    """Insights page payload and same-game builders use available markets only."""
    print("\nTesting insights and bet builders...")
    try:
        from hibs_predictor.assistant_recommendations import build_bet_builder_suggestions
        from hibs_predictor.insights import build_insights

        pkt = {
            "id": 10,
            "home": "Hibs",
            "away": "Hearts",
            "league": "SCOTLAND",
            "league_name": "Scottish Premiership",
            "kickoff_time": "15:00",
            "data_quality_pct": 90.0,
            "data_quality": {"score_pct": 90, "blocks": []},
            "home_recent_n": 5,
            "away_recent_n": 5,
            "structured_insight": {"mode": "prediction", "match": "Hibs vs Hearts", "pick": "BTTS Yes"},
            "pick_menu": [
                {"key": "btts_yes", "label": "BTTS Yes", "model_pct": 64.0, "odds": 1.8},
                {"key": "over_25", "label": "Over 2.5", "model_pct": 61.0, "odds": 1.95},
                {"key": "over_15", "label": "Over 1.5", "model_pct": 74.0, "odds": 1.35},
                {"key": "home_or_draw", "label": "Home or Draw", "model_pct": 68.0, "odds": 1.42},
            ],
            "probability_scores": {"xg_home": 1.6, "xg_away": 1.2},
            "home_position": {"position": 4},
            "away_position": {"position": 7},
            "home_form_summary": {"played": 5, "wins": 3, "draws": 1, "losses": 1},
            "away_form_summary": {"played": 5, "wins": 2, "draws": 1, "losses": 2},
        }
        builders = build_bet_builder_suggestions([pkt])
        titles = [b["title"] for b in builders]
        assert "BTTS + Over 2.5" in titles
        assert "Home or Draw + Over 1.5" in titles

        fixture = {
            "id": 10,
            "home": "Hibs",
            "away": "Hearts",
            "league": "SCOTLAND",
            "league_name": "Scottish Premiership",
            "kickoff_time": "15:00",
            "home_last10": [{"result": "W", "gf": 2, "ga": 1} for _ in range(5)],
            "away_last10": [{"result": "L", "gf": 1, "ga": 2} for _ in range(5)],
            "home_position": {"position": 4},
            "away_position": {"position": 7},
            "data_quality": {"score_pct": 90, "blocks": []},
            "xg_source": "api_fixture_xg",
            "has_value_bet": True,
            "prediction": {
                "structured_insight": {"mode": "prediction", "match": "Hibs vs Hearts", "pick": "BTTS Yes"},
                "pick_menu": pkt["pick_menu"],
                "probability_scores": pkt["probability_scores"],
                "value_bets_display": [{"market_label": "BTTS Yes", "odds": 1.8, "edge_pct": 4.0, "roi_percent": 5.0}],
            },
        }
        ins = build_insights([fixture])
        assert ins["top_probabilities"]
        assert ins["value_opportunities"]
        assert ins["bet_builders"]
        assert ins["coverage"]["no_player_props"] is True
        print("  ✓ Insights and bet builders OK")
        return True
    except Exception as e:
        print(f"  ✗ Insights/bet-builder test failed: {e}")
        return False


def test_dashboard_days_grouping():
    """Main dashboard: fixtures grouped by UK local day, then league (SPL first)."""
    print("\nTesting dashboard day/league grouping...")
    try:
        from hibs_predictor.display_tz import attach_kickoff_display
        from hibs_predictor.web import _dashboard_days_groups, _finalize_fixture_bundle, DASHBOARD_LEAGUE_ORDER

        raw = [
            attach_kickoff_display(
                {
                    "id": 1,
                    "home": "Hibs",
                    "away": "Celts",
                    "date": "2026-05-15T11:30:00+00:00",
                    "league": "SCOTLAND",
                    "prediction": {"pick_menu": [{"key": "home_win", "label": "Home Win"}]},
                }
            ),
            attach_kickoff_display(
                {
                    "id": 2,
                    "home": "Arsenal",
                    "away": "Chelsea",
                    "date": "2026-05-15T19:00:00+00:00",
                    "league": "EPL",
                    "prediction": {"pick_menu": [{"key": "draw", "label": "Draw"}]},
                }
            ),
            attach_kickoff_display(
                {
                    "id": 3,
                    "home": "Rangers",
                    "away": "Aberdeen",
                    "date": "2026-05-16T14:00:00+00:00",
                    "league": "SCOTLAND",
                    "prediction": {},
                }
            ),
        ]
        days = _dashboard_days_groups(raw)
        assert len(days) == 2
        assert days[0]["date_iso"] == "2026-05-15"
        assert [lg["code"] for lg in days[0]["leagues"]] == ["SCOTLAND", "EPL"]
        assert days[0]["leagues"][0]["code"] == DASHBOARD_LEAGUE_ORDER[0] or days[0]["leagues"][0]["code"] == "SCOTLAND"
        assert sum(len(lg["fixtures"]) for lg in days[0]["leagues"]) == 2

        bundle = _finalize_fixture_bundle(list(raw))
        assert bundle["total"] == 3
        assert len(bundle["dashboard_days"]) == 2
        assert bundle["sidebar_upcoming"]
        assert bundle["all"][0]["kickoff_time"] == "12:30"
        assert bundle["all"][0]["prediction"].get("pick_menu")
        print("  ✓ Dashboard day/league grouping OK")
        return True
    except Exception as e:
        print(f"  ✗ Dashboard grouping test failed: {e}")
        return False


def test_scottish_fbref_xg():
    """Scottish FBref schedule xG resolves without live HTTP."""
    print("\nTesting Scottish FBref xG...")
    try:
        from unittest.mock import patch

        from hibs_predictor.scraped_xg import apply_scraped_xg_to_enriched

        sample_rows = [
            {"home": "Hibernian", "away": "Celtic", "xg_home": 1.4, "xg_away": 1.9},
            {"home": "Hearts", "away": "Hibernian", "xg_home": 1.1, "xg_away": 1.6},
            {"home": "Rangers", "away": "Hearts", "xg_home": 2.0, "xg_away": 0.7},
            {"home": "Motherwell", "away": "Livingston", "xg_home": 1.2, "xg_away": 0.9},
            {"home": "Aberdeen", "away": "St Johnstone", "xg_home": 1.3, "xg_away": 1.0},
            {"home": "Motherwell", "away": "Kilmarnock", "xg_home": 1.05, "xg_away": 1.15},
            {"home": "St Mirren", "away": "Aberdeen", "xg_home": 0.95, "xg_away": 1.35},
        ]
        fixture = {
            "teams": {"home": {"id": 10, "name": "Hibernian"}, "away": {"id": 20, "name": "Celtic"}},
            "home": {"name": "Hibernian"},
            "away": {"name": "Celtic"},
        }
        enriched = {
            "xg_home": 1.0,
            "xg_away": 1.0,
            "xg_source": "goals_proxy",
            "home_recent": [],
            "away_recent": [],
            "supplemental": {},
        }
        with patch(
            "hibs_predictor.scrapers.fbref_scottish_xg.fetch_schedule_rows",
            return_value=sample_rows,
        ):
            out = apply_scraped_xg_to_enriched(fixture, "SCOTLAND", enriched)
            assert out["xg_source"] == "scottish_fbref_xg", out.get("xg_source")
            assert out["xg_home"] == 1.4
            assert out["xg_away"] == 1.9

        enriched2 = {
            "xg_home": 1.0,
            "xg_away": 1.0,
            "xg_source": "goals_proxy",
            "home_recent": [],
            "away_recent": [],
            "supplemental": {},
        }
        with patch(
            "hibs_predictor.scrapers.fbref_scottish_xg.fetch_schedule_rows",
            return_value=sample_rows,
        ):
            out2 = apply_scraped_xg_to_enriched(
                {
                    "teams": {"home": {"id": 11, "name": "Motherwell"}, "away": {"id": 12, "name": "Aberdeen"}},
                    "home": {"name": "Motherwell"},
                    "away": {"name": "Aberdeen"},
                },
                "SCOTLAND",
                enriched2,
            )
            assert out2["xg_source"] == "scottish_fbref_avg_xg", out2.get("xg_source")
            assert out2["xg_home"] > 0.5
            assert out2["xg_away"] > 0.5
        print("  ✓ Scottish FBref xG fixture + team avg")
        return True
    except Exception as e:
        print(f"  ✗ Scottish FBref xG test failed: {e}")
        return False


def test_scraped_xg_resolution():
    """Scraped xG from recent API matches upgrades goals_proxy."""
    print("\nTesting scraped xG...")
    try:
        from hibs_predictor.scraped_xg import apply_scraped_xg_to_enriched

        fixture = {
            "teams": {"home": {"id": 1, "name": "Home FC"}, "away": {"id": 2, "name": "Away FC"}},
            "home": {"name": "Home FC"},
            "away": {"name": "Away FC"},
        }
        enriched = {
            "xg_home": 1.1,
            "xg_away": 1.0,
            "xg_source": "goals_proxy",
            "home_recent": [
                {
                    "teams": {"home": {"id": 1}, "away": {"id": 99}},
                    "statistics": [
                        {"team": {"id": 1}, "expected_goals": {"total": "1.8"}},
                        {"team": {"id": 99}, "expected_goals": {"total": "0.9"}},
                    ],
                },
                {
                    "teams": {"home": {"id": 88}, "away": {"id": 1}},
                    "statistics": [
                        {"team": {"id": 88}, "expected_goals": {"total": "1.0"}},
                        {"team": {"id": 1}, "expected_goals": {"total": "2.1"}},
                    ],
                },
            ],
            "away_recent": [
                {
                    "teams": {"home": {"id": 2}, "away": {"id": 77}},
                    "statistics": [
                        {"team": {"id": 2}, "expected_goals": {"total": "1.5"}},
                        {"team": {"id": 77}, "expected_goals": {"total": "1.0"}},
                    ],
                },
                {
                    "teams": {"home": {"id": 66}, "away": {"id": 2}},
                    "statistics": [
                        {"team": {"id": 66}, "expected_goals": {"total": "0.8"}},
                        {"team": {"id": 2}, "expected_goals": {"total": "1.6"}},
                    ],
                },
            ],
            "supplemental": {},
        }
        out = apply_scraped_xg_to_enriched(fixture, "SCOTLAND", enriched)
        assert out["xg_source"] == "scraped_recent_xg", out.get("xg_source")
        assert out["xg_home"] > 1.4
        assert out["xg_away"] > 1.3
        print("  ✓ Scraped recent-match xG applied")
        return True
    except Exception as e:
        print(f"  ✗ Scraped xG test failed: {e}")
        return False


def test_kickoff_display_tz():
    """Kick-off shown in Europe/London (BST: UTC+1)."""
    print("\nTesting kick-off timezone display...")
    try:
        from hibs_predictor.display_tz import attach_kickoff_display, day_heading_for_local_date
        from datetime import date

        f = attach_kickoff_display({"date": "2026-05-15T11:30:00+00:00", "home": "Hibs", "away": "Celts"})
        assert f["kickoff_time"] == "12:30", f"expected 12:30 BST, got {f['kickoff_time']}"
        assert f["kickoff_day_local"] == "2026-05-15"
        h = day_heading_for_local_date("2026-05-15", 3, date(2026, 5, 15))
        assert "Today" in h and "3 fixtures" in h
        print("  ✓ Kick-off local time (UK) correct")
        return True
    except Exception as e:
        print(f"  ✗ Kick-off TZ test failed: {e}")
        return False


def test_templates():
    """Test template loading."""
    print("\nTesting templates...")
    try:
        from jinja2 import Environment, FileSystemLoader
        template_dir = os.path.join(os.path.dirname(__file__), 'templates')
        env = Environment(loader=FileSystemLoader(template_dir))
        templates = ["base.html", "dashboard.html", "acca_builder.html", "api_status.html", "insights.html"]
        for template in templates:
            env.get_template(template)
            print(f"  ✓ Template loaded: {template}")
        return True
    except Exception as e:
        print(f"  ✗ Template test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("=" * 60)
    print("hibs-bet application test suite")
    print("=" * 60)
    
    tests = [
        test_imports,
        test_config,
        test_cache,
        test_rate_limiter,
        test_data_policy,
        test_main_cli_help,
        test_flask_routes,
        test_api_health_prediction_quality,
        test_api_cache_clear,
        test_structured_insight,
        test_value_edge_fields,
        test_bottom_top_underdog_not_home_value,
        test_pick_menu,
        test_dashboard_days_grouping,
        test_kickoff_display_tz,
        test_scottish_fbref_xg,
        test_scraped_xg_resolution,
        test_assistant_recommendations,
        test_insights_and_bet_builders,
        test_assistant_chat,
        test_templates,
    ]
    
    results = [test() for test in tests]
    
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    
    if all(results):
        print("✓ All tests passed! Application ready to run.")
        print("\nStart the dashboard: launch/Run-hibs-bet.command or: PYTHONPATH=src python3 src/hibs_predictor/web.py")
        return 0
    else:
        print("✗ Some tests failed. Check output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
