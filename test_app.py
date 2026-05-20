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
            "/api/fixtures/live",
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
            "/tables",
            "/guide",
            "/status",
            "/settings",
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


def _sample_table_fixture_bundle():
    from hibs_predictor.display_tz import attach_kickoff_display
    from hibs_predictor.web import _finalize_fixture_bundle

    fixtures = [
        attach_kickoff_display(
            {
                "id": 101,
                "home": "Hibs",
                "away": "Hearts",
                "date": "2026-05-15T14:00:00+00:00",
                "league": "SCOTLAND",
                "league_name": "Scottish Premiership",
                "league_flag": "",
                "home_position": {
                    "position": 4,
                    "played": 30,
                    "won": 14,
                    "drawn": 8,
                    "lost": 8,
                    "goals_for": 44,
                    "goals_against": 33,
                    "goal_diff": 11,
                    "points": 50,
                },
                "away_position": {
                    "position": 6,
                    "played": 30,
                    "won": 12,
                    "drawn": 8,
                    "lost": 10,
                    "goals_for": 40,
                    "goals_against": 38,
                    "goal_diff": 2,
                    "points": 44,
                },
                "data_quality": {"score_pct": 90, "blocks": []},
                "xg_source": "api_fixture_xg",
                "has_value_bet": False,
                "home_last10": [],
                "away_last10": [],
                "prediction": {
                    "prediction_unavailable": True,
                    "prediction_quality_hint": {"summary": "Prediction unavailable"},
                    "bookmaker_odds": {"home": None, "draw": None, "away": None},
                    "value_bets": {},
                    "line_odds": {},
                    "pick_menu": [],
                },
            }
        ),
        attach_kickoff_display(
            {
                "id": 102,
                "home": "Aberdeen",
                "away": "Dundee",
                "date": "2026-05-15T15:00:00+00:00",
                "league": "SCOTLAND",
                "league_name": "Scottish Premiership",
                "league_flag": "",
                "home_position": {"position": 3, "played": 30, "won": 15, "drawn": 7, "lost": 8, "goals_for": 45, "goals_against": 31, "goal_diff": 14, "points": 52},
                "away_position": {"position": 5, "played": 30, "won": 13, "drawn": 7, "lost": 10, "goals_for": 39, "goals_against": 34, "goal_diff": 5, "points": 46},
                "data_quality": {"score_pct": 86, "blocks": []},
                "xg_source": "api_fixture_xg",
                "has_value_bet": False,
                "home_last10": [],
                "away_last10": [],
                "prediction": {
                    "prediction_unavailable": True,
                    "prediction_quality_hint": {"summary": "Prediction unavailable"},
                    "bookmaker_odds": {"home": None, "draw": None, "away": None},
                    "value_bets": {},
                    "line_odds": {},
                    "pick_menu": [],
                },
            }
        ),
    ]
    return _finalize_fixture_bundle(fixtures)


def test_insights_tables_routes_and_snapshots():
    """Insights, tables, and compact table snapshots render with fixture-row fallback."""
    print("\nTesting insights/tables routes and table snapshots...")
    try:
        from unittest.mock import patch
        from hibs_predictor.web import app

        bundle = _sample_table_fixture_bundle()
        full_rows = [
            {"position": 3, "team": "Aberdeen", "played": 30, "won": 15, "drawn": 7, "lost": 8, "goals_for": 45, "goals_against": 31, "goal_diff": 14, "points": 52, "source": "test"},
            {"position": 4, "team": "Hibs", "played": 30, "won": 14, "drawn": 8, "lost": 8, "goals_for": 44, "goals_against": 33, "goal_diff": 11, "points": 50, "source": "test"},
            {"position": 5, "team": "Dundee", "played": 30, "won": 13, "drawn": 7, "lost": 10, "goals_for": 39, "goals_against": 34, "goal_diff": 5, "points": 46, "source": "test"},
            {"position": 6, "team": "Hearts", "played": 30, "won": 12, "drawn": 8, "lost": 10, "goals_for": 40, "goals_against": 38, "goal_diff": 2, "points": 44, "source": "test"},
        ]
        with patch("hibs_predictor.web.fetch_all_fixtures", return_value=bundle), patch(
            "hibs_predictor.web._fetch_full_table_rows", return_value=full_rows
        ):
            client = app.test_client()
            insights = client.get("/insights")
            tables = client.get("/tables")
            guide = client.get("/guide")
            settings = client.get("/settings")
            dashboard = client.get("/")

        assert insights.status_code == 200, insights.get_data(as_text=True)[:200]
        assert tables.status_code == 200, tables.get_data(as_text=True)[:200]
        assert guide.status_code == 200, guide.get_data(as_text=True)[:200]
        assert settings.status_code == 200, settings.get_data(as_text=True)[:200]
        assert b"League Tables" in tables.data
        assert b"Betting Guide" in guide.data
        assert b"Bet engine profile" in settings.data
        assert dashboard.status_code == 200, dashboard.get_data(as_text=True)[:200]
        body = dashboard.get_data(as_text=True)
        assert "Aberdeen" in body and "Hibs" in body and "Dundee" in body
        assert "What this page does" in body
        assert "1 leagues loaded" in body
        assert "Scottish Premiership" in body
        assert "Table N/A" not in body
        print("  ✓ /insights, /tables, /settings, and dashboard context render")
        return True
    except Exception as e:
        print(f"  ✗ Insights/tables route test failed: {e}")
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


def test_competition_display_titles():
    """Provider league/round maps to human headings (cup finals, playoffs)."""
    print("\nTesting competition display titles...")
    try:
        from hibs_predictor.display_tz import attach_kickoff_display
        from hibs_predictor.fixture_utils import display_competition_title
        from hibs_predictor.web import _dashboard_days_groups

        cup = display_competition_title(
            fallback_name="Scottish Premiership",
            api_league_name="Scottish Cup",
            api_round="Final",
        )
        assert "scottish cup" in cup.lower()
        assert "final" in cup.lower()

        efl_po = display_competition_title(
            fallback_name="Championship",
            api_league_name="Championship",
            api_round="Play-offs - Final",
        )
        assert "play" in efl_po.lower() or "final" in efl_po.lower()

        raw = [
            attach_kickoff_display(
                {
                    "id": 501,
                    "home": "Hull City",
                    "away": "Middlesbrough",
                    "date": "2026-05-24T14:00:00+00:00",
                    "league": "CHAMPIONSHIP",
                    "league_name": "Championship — Play-offs - Final",
                }
            )
        ]
        days = _dashboard_days_groups(raw)
        assert days[0]["leagues"][0]["name"] == "Championship — Play-offs - Final"

        print("  ✓ Competition display titles OK")
        return True
    except Exception as e:
        print(f"  ✗ Competition display titles failed: {e}")
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


def test_fdo_recent_matches_for_serie_a_shape():
    """Football-Data.org last matches normalize for rate calculators."""
    print("\nTesting FDO recent-match adapter...")
    try:
        from hibs_predictor.data_aggregator import _fdo_match_to_recent_format, _recent_match_rates

        m = {
            "homeTeam": {"id": 99, "name": "ACF Fiorentina"},
            "awayTeam": {"id": 102, "name": "Atalanta BC"},
            "score": {"fullTime": {"home": 2, "away": 1}},
        }
        norm = _fdo_match_to_recent_format(m)
        assert norm and norm["goals"]["home"] == 2
        rates = _recent_match_rates([norm], 99)
        assert rates["n"] >= 1.0
        assert rates["avg_gf"] > 0
        print("  ✓ FDO match adapter")
        return True
    except Exception as e:
        print(f"  ✗ FDO adapter failed: {e}")
        return False


def test_understat_serie_a_name_match():
    print("\nTesting Understat Serie A name matching...")
    try:
        from hibs_predictor.scrapers.understat_client import _names_match

        assert _names_match("ACF Fiorentina", "Fiorentina")
        assert _names_match("FC Internazionale Milano", "Inter")
        assert _names_match("Atalanta BC", "Atalanta")
        assert not _names_match("Manchester United", "Manchester City")
        print("  ✓ Understat name aliases")
        return True
    except Exception as e:
        print(f"  ✗ Understat names failed: {e}")
        return False


def test_understat_scraped_xg_coverage():
    """Understat match or team rolling xG upgrades goals_proxy and data_quality."""
    print("\nTesting Understat scraped xG coverage...")
    try:
        from unittest.mock import patch

        from hibs_predictor.data_quality import compute_fixture_data_quality
        from hibs_predictor.scraped_xg import apply_scraped_xg_to_enriched

        fixture = {
            "fixture": {"id": 501, "date": "2026-05-24T15:00:00+00:00"},
            "date": "2026-05-24T15:00:00+00:00",
            "teams": {"home": {"id": 1, "name": "Brighton"}, "away": {"id": 2, "name": "Manchester United"}},
        }
        enriched = {
            "fixture": {"id": 501},
            "teams": fixture["teams"],
            "home_recent_n": 6,
            "away_recent_n": 6,
            "home_stats": {"played": 15, "goals_for": 22, "goals_against": 20},
            "away_stats": {"played": 15, "goals_for": 24, "goals_against": 18},
            "home_position": {"position": 8},
            "away_position": {"position": 6},
            "xg_home": 1.2,
            "xg_away": 1.1,
            "xg_source": "goals_proxy",
            "odds_available": True,
            "odds_home": 2.1,
            "odds_draw": 3.4,
            "odds_away": 3.5,
            "supplemental": {},
            "fixture_injuries": [],
        }
        before = compute_fixture_data_quality(enriched)["score_pct"]
        mock_payload = {"xg_home": 1.55, "xg_away": 1.42}
        with patch(
            "hibs_predictor.scrapers.understat_client.resolve_understat_xg",
            return_value=(mock_payload, "understat_team_xg", {"team_rolling": True, "home_n": 5, "away_n": 4}),
        ):
            out = apply_scraped_xg_to_enriched(fixture, "EPL", enriched)
        assert out["xg_source"] == "understat_team_xg", out.get("xg_source")
        after = compute_fixture_data_quality(out)["score_pct"]
        assert after > before
        out_dq = compute_fixture_data_quality(out)
        xg_block = next(b for b in out_dq["blocks"] if b["key"] == "xg")
        assert xg_block["earned"] >= 14.0
        print(f"  ✓ Understat xG coverage {before}% -> {after}%")
        return True
    except Exception as e:
        print(f"  ✗ Understat scraped xG coverage failed: {e}")
        return False


def test_fbref_schedule_xg_championship():
    """EFL Championship uses fbref_schedule_xg tag (mocked rows)."""
    print("\nTesting FBref schedule xG (Championship)...")
    try:
        from unittest.mock import patch

        from hibs_predictor.scraped_xg import apply_scraped_xg_to_enriched

        rows = [{"home": "Leeds United", "away": "Sheffield United", "xg_home": 1.7, "xg_away": 1.1}]
        fixture = {
            "teams": {"home": {"id": 1, "name": "Leeds United"}, "away": {"id": 2, "name": "Sheffield United"}},
            "home": {"name": "Leeds United"},
            "away": {"name": "Sheffield United"},
        }
        enriched = {"xg_home": 1.0, "xg_away": 1.0, "xg_source": "goals_proxy", "supplemental": {}}
        with patch("hibs_predictor.scrapers.fbref_scottish_xg.fetch_schedule_rows", return_value=rows):
            out = apply_scraped_xg_to_enriched(fixture, "CHAMPIONSHIP", enriched)
        assert out["xg_source"] == "fbref_schedule_xg", out.get("xg_source")
        assert out["xg_home"] == 1.7
        print("  ✓ Championship FBref schedule xG")
        return True
    except Exception as e:
        print(f"  ✗ FBref schedule xG test failed: {e}")
        return False


def test_soccerstats_standings_parse():
    """SoccerStats HTML table parser extracts positions."""
    print("\nTesting SoccerStats standings parse...")
    try:
        from hibs_predictor.scrapers import soccerstats_standings as ss

        html = """
        <html><body><table>
        <tr><th>#</th><th>Team</th><th>GP</th><th>W</th><th>D</th><th>L</th><th>GF</th><th>GA</th><th>Pts</th></tr>
        <tr><td>1.</td><td>Arsenal</td><td>38</td><td>28</td><td>5</td><td>5</td><td>86</td><td>28</td><td>89</td></tr>
        <tr><td>2.</td><td>Liverpool</td><td>38</td><td>27</td><td>6</td><td>5</td><td>80</td><td>32</td><td>87</td></tr>
        </table></body></html>
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        rows = []
        for tr in table.find_all("tr")[1:]:
            tds = tr.find_all("td")
            texts = [td.get_text(strip=True) for td in tds]
            rows.append(texts)
        assert len(rows) == 2
        parsed = ss.fetch_league_table.__wrapped__ if hasattr(ss.fetch_league_table, "__wrapped__") else None
        row = ss.find_team_row(
            [
                {"position": 1, "team": "Arsenal", "played": 38, "points": 89},
                {"position": 2, "team": "Liverpool", "played": 38, "points": 87},
            ],
            "Arsenal",
        )
        assert row and row["position"] == 1
        print("  ✓ SoccerStats team row match")
        return True
    except Exception as e:
        print(f"  ✗ SoccerStats test failed: {e}")
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

        enriched_form = {
            "xg_home": 1.35,
            "xg_away": 1.05,
            "xg_source": "goals_proxy",
            "home_recent_n": 8,
            "away_recent_n": 7,
            "home_recent": [],
            "away_recent": [],
            "supplemental": {},
        }
        out_form = apply_scraped_xg_to_enriched(fixture, "EPL", enriched_form)
        assert out_form["xg_source"] == "form_derived_xg", out_form.get("xg_source")
        enriched_ss = {
            "xg_home": 1.0,
            "xg_away": 1.0,
            "xg_source": "goals_proxy",
            "supplemental": {
                "sofascore_xg": {
                    "home_avg_for": 1.62,
                    "away_avg_for": 1.41,
                    "home_n": 5,
                    "away_n": 4,
                }
            },
        }
        out_ss = apply_scraped_xg_to_enriched(fixture, "BELGIUM_FIRST", enriched_ss)
        assert out_ss["xg_source"] == "sofascore_xg", out_ss.get("xg_source")
        assert out_ss["xg_home"] == 1.62
        assert out_ss["xg_away"] == 1.41

        from hibs_predictor.scrapers.sofascore_client import parse_xg_from_statistics_payload

        stats = {
            "statistics": [
                {
                    "period": "ALL",
                    "groups": [
                        {
                            "groupName": "Football",
                            "statisticsItems": [
                                {"name": "Expected goals", "home": "1.84", "away": "0.53"},
                            ],
                        }
                    ],
                }
            ]
        }
        pair = parse_xg_from_statistics_payload(stats)
        assert pair == (1.84, 0.53), pair

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


def test_nordic_leagues_configured():
    """Norway Eliteserien and Finland Veikkausliiga are in dashboard league set."""
    print("\nTesting Nordic league config...")
    try:
        from hibs_predictor.config import LEAGUES, ALL_LEAGUE_CODES, LEAGUE_REGIONS

        assert "NORWAY_ELITESERIEN" in LEAGUES
        assert LEAGUES["NORWAY_ELITESERIEN"]["api_sports_id"] == 103
        assert "FINLAND_VEIKKAUSLIIGA" in LEAGUES
        assert LEAGUES["FINLAND_VEIKKAUSLIIGA"]["api_sports_id"] == 244
        assert "NORWAY_ELITESERIEN" in ALL_LEAGUE_CODES
        assert "FINLAND_VEIKKAUSLIIGA" in ALL_LEAGUE_CODES
        euro = LEAGUE_REGIONS.get("🏆 European", [])
        assert "NORWAY_ELITESERIEN" in euro
        assert "FINLAND_VEIKKAUSLIIGA" in euro
        print("  ✓ Norway/Finland leagues configured")
        return True
    except Exception as e:
        print(f"  ✗ Nordic league config failed: {e}")
        return False


def test_calendar_year_season_candidate():
    """May calendar-year leagues try current year season (2026) before Jul-based id."""
    print("\nTesting calendar-year season candidates...")
    try:
        from datetime import datetime, timezone
        from hibs_predictor.web import _fixture_fetch_season_candidates

        now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
        seasons = _fixture_fetch_season_candidates(None, "2026-05-20", "2026-05-25", now)
        assert seasons[0] == 2026, seasons
        print("  ✓ Calendar-year season candidate OK")
        return True
    except Exception as e:
        print(f"  ✗ Season candidate test failed: {e}")
        return False


def test_live_scores_merge_mocked():
    """Live snapshot fields merge onto dashboard fixture rows."""
    print("\nTesting live scores merge...")
    try:
        from hibs_predictor.live_scores import merge_live_into_fixtures, parse_api_fixture_live

        raw = {
            "fixture": {"id": 99901, "status": {"short": "1H", "long": "First Half", "elapsed": 23}},
            "goals": {"home": 2, "away": 1},
            "teams": {"home": {"name": "A"}, "away": {"name": "B"}},
        }
        parsed = parse_api_fixture_live(raw)
        assert parsed["is_live"] is True
        assert parsed["live_score"] == "2-1"
        assert parsed["live_minute"] == 23
        fixtures = [{"id": 99901, "home": "A", "away": "B"}]
        n = merge_live_into_fixtures(fixtures, {99901: parsed})
        assert n == 1
        assert fixtures[0]["live_score"] == "2-1"
        assert fixtures[0]["live_status"] == "1H"
        print("  ✓ Live merge OK")
        return True
    except Exception as e:
        print(f"  ✗ Live scores test failed: {e}")
        return False


def test_fixture_window_includes_todays_kicked_off():
    """Today's cup finals stay in the fetch window after kick-off (UK calendar day)."""
    print("\nTesting fixture window (today after KO)...")
    try:
        from datetime import datetime, timezone, timedelta

        from hibs_predictor.display_tz import fixture_window_start_utc, fixture_window_end_utc

        now = datetime(2026, 5, 20, 20, 30, tzinfo=timezone.utc)
        ko = datetime(2026, 5, 20, 19, 0, tzinfo=timezone.utc)
        start = fixture_window_start_utc(now)
        cutoff = fixture_window_end_utc(now, 5)
        assert start <= ko <= cutoff, "Europa final KO should remain visible on final day"
        uecl_final = datetime(2026, 5, 27, 19, 0, tzinfo=timezone.utc)
        cutoff7 = fixture_window_end_utc(now, 7)
        assert start <= uecl_final <= cutoff7, "late KO on last window day should be included"
        assert now > ko, "sanity: after kick-off"
        from hibs_predictor.config import LEAGUES, ALL_LEAGUE_CODES

        assert "EUROPA_LEAGUE" in LEAGUES
        assert LEAGUES["EUROPA_LEAGUE"].get("api_sports_id") == 3
        assert "EUROPA_LEAGUE" in ALL_LEAGUE_CODES
        print("  ✓ Fixture window + Europa League mapping OK")
        return True
    except Exception as e:
        print(f"  ✗ Fixture window test failed: {e}")
        return False


def test_sky_sports_news_media_config():
    """Sky Sports News uses official YouTube embed + Sky watch link (no scraped streams)."""
    print("\nTesting Sky Sports News media config...")
    try:
        from hibs_predictor.media_config import (
            SKY_SPORTS_NEWS_WATCH_URL,
            SKY_SPORTS_NEWS_YOUTUBE_EMBED_URL,
            SKY_SPORTS_NEWS_YOUTUBE_CHANNEL_ID,
        )

        assert "skysports.com" in SKY_SPORTS_NEWS_WATCH_URL
        assert SKY_SPORTS_NEWS_YOUTUBE_CHANNEL_ID in SKY_SPORTS_NEWS_YOUTUBE_EMBED_URL
        assert "youtube.com/embed/live_stream" in SKY_SPORTS_NEWS_YOUTUBE_EMBED_URL
        print("  ✓ Sky Sports News official URLs configured")
        return True
    except Exception as e:
        print(f"  ✗ Sky Sports News config test failed: {e}")
        return False


def test_fotmob_adapter_mocked():
    """FotMob fixture fallback parses mocked public daily payload without network."""
    print("\nTesting FotMob adapter...")
    try:
        from datetime import date
        from unittest.mock import patch
        from hibs_predictor.cache import Cache
        from hibs_predictor.scrapers import fotmob_client
        import tempfile

        payload = {
            "leagues": [
                {
                    "id": 47,
                    "name": "Premier League",
                    "matches": [
                        {
                            "id": 123,
                            "utcTime": "2026-05-18T19:00:00Z",
                            "home": {"id": 1, "name": "Arsenal"},
                            "away": {"id": 2, "name": "Burnley"},
                            "status": {"short": "NS"},
                        }
                    ],
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmp:
            cache = Cache(cache_dir=tmp)
            with patch("hibs_predictor.scrapers.fotmob_client.fetch_matches_for_date", return_value=payload):
                rows = fotmob_client.fixtures_for_league("EPL", date(2026, 5, 18), date(2026, 5, 18), cache=cache)
        assert len(rows) == 1
        assert rows[0]["home"]["name"] == "Arsenal"
        print("  ✓ FotMob adapter parses mocked fixtures")
        return True
    except Exception as e:
        print(f"  ✗ FotMob adapter test failed: {e}")
        return False


def test_football_data_standings_mocked():
    """Football-Data.org standings parser resolves a team row without network."""
    print("\nTesting Football-Data standings...")
    try:
        from unittest.mock import patch
        from hibs_predictor.api_clients import FootballDataOrgClient

        payload = {
            "standings": [
                {
                    "type": "TOTAL",
                    "table": [
                        {
                            "position": 1,
                            "team": {"id": 57, "name": "Arsenal FC"},
                            "playedGames": 38,
                            "won": 26,
                            "draw": 8,
                            "lost": 4,
                            "goalsFor": 84,
                            "goalsAgainst": 31,
                            "goalDifference": 53,
                            "points": 86,
                            "form": "WWDWW",
                        }
                    ],
                }
            ]
        }
        client = FootballDataOrgClient("test-key")
        with patch.object(client, "_get_json", return_value=payload):
            row = client.fetch_team_position(57, "PL", 2025)
        assert row["position"] == 1
        assert row["source"] == "football_data_org"
        assert row["played"] == 38
        print("  ✓ Football-Data standings parser OK")
        return True
    except Exception as e:
        print(f"  ✗ Football-Data standings test failed: {e}")
        return False


def test_table_rows_use_previous_season_standings():
    """Tables fall back to cached last-completed standings when current season is empty."""
    print("\nTesting previous-season table fallback...")
    try:
        import tempfile
        from unittest.mock import patch
        from hibs_predictor.cache import Cache
        from hibs_predictor import web

        class FakeFootballData:
            def __init__(self, cache):
                self.cache = cache

            def fetch_standings(self, competition_code, season):
                if season == 2025:
                    return []
                return [
                    {
                        "type": "TOTAL",
                        "table": [
                            {
                                "position": 2,
                                "team": {"id": 57, "name": "Arsenal FC"},
                                "playedGames": 38,
                                "won": 24,
                                "draw": 9,
                                "lost": 5,
                                "goalsFor": 80,
                                "goalsAgainst": 34,
                                "goalDifference": 46,
                                "points": 81,
                            }
                        ],
                    }
                ]

        with tempfile.TemporaryDirectory() as tmp:
            fake_client = FakeFootballData(Cache(cache_dir=tmp))
            with patch.dict(web.aggregator.clients, {"football_data_org": fake_client}, clear=True), patch(
                "hibs_predictor.web.datetime"
            ) as fake_dt:
                from datetime import datetime as real_datetime, timezone

                fake_dt.now.return_value = real_datetime(2026, 5, 18, tzinfo=timezone.utc)
                fake_dt.fromisoformat.side_effect = real_datetime.fromisoformat
                rows = web._fetch_full_table_rows("EPL", live_fetch=True)
        assert rows and rows[0]["team"] == "Arsenal FC"
        assert rows[0]["season_status"] == "last_completed"
        table = web._build_league_tables([], include_live=False)
        assert isinstance(table, list)
        print("  ✓ Previous-season standings fallback OK")
        return True
    except Exception as e:
        print(f"  ✗ Previous-season standings fallback failed: {e}")
        return False


def test_assistant_freeform_clarifies_ambiguity():
    """Assistant is free-form and asks for clarification when a team query matches multiple fixtures."""
    print("\nTesting free-form assistant clarification...")
    try:
        from hibs_predictor.assistant_chat import handle_chat

        packets = [
            {"id": 1, "home": "Arsenal", "away": "Burnley", "league": "EPL", "structured_insight": {}, "data_quality_pct": 80},
            {"id": 2, "home": "Chelsea", "away": "Arsenal", "league": "EPL", "structured_insight": {}, "data_quality_pct": 80},
        ]
        res = handle_chat("analyze Arsenal", packets, recommendations={"disclaimer": ""})
        text = " ".join(" ".join(b.get("lines", [])) for b in res.get("blocks", []))
        assert "more than one" in text.lower()
        assert "Arsenal v Burnley" in text or "Chelsea v Arsenal" in text
        print("  ✓ Assistant asks concise clarification")
        return True
    except Exception as e:
        print(f"  ✗ Assistant clarification test failed: {e}")
        return False


def test_field_quality_and_league_profile():
    """Field-level trust buckets and league profile calibration are exposed."""
    print("\nTesting field quality and league profile calibration...")
    try:
        from hibs_predictor.data_quality import compute_fixture_data_quality
        from hibs_predictor.league_profiles import apply_league_probability_profile, value_margin_extra

        dq = compute_fixture_data_quality(
            {
                "fixture": {"id": 99},
                "teams": {"home": {"id": 1}, "away": {"id": 2}},
                "home_recent_n": 8,
                "away_recent_n": 2,
                "home_stats": {"played": 20, "goals_for": 35, "goals_against": 20},
                "away_stats": {},
                "home_position": {"position": 2},
                "away_position": {},
                "xg_source": "goals_proxy",
                "odds_home": 1.8,
                "odds_draw": 3.6,
                "odds_away": 4.5,
                "market_odds": {},
                "supplemental": {},
                "fixture_injuries": [],
            }
        )
        assert "field_scores" in dq
        assert dq["field_scores"]["standings"]["status"] in ("thin", "usable", "missing")
        assert dq["weak_fields"]

        dq_form = compute_fixture_data_quality(
            {
                "fixture": {"id": 100},
                "teams": {"home": {"id": 1}, "away": {"id": 2}},
                "home_recent_n": 10,
                "away_recent_n": 10,
                "home_stats": {"played": 20, "goals_for": 35, "goals_against": 20},
                "away_stats": {"played": 20, "goals_for": 30, "goals_against": 25},
                "home_position": {"position": 2},
                "away_position": {"position": 5},
                "xg_source": "form_derived_xg",
                "odds_available": True,
                "odds_home": 1.8,
                "odds_draw": 3.6,
                "odds_away": 4.5,
                "line_odds": {"btts_yes": 1.7, "over25": 1.9},
                "market_odds": {},
                "supplemental": {"wikipedia_league_supported": True},
                "fixture_injuries": [],
            }
        )
        assert dq_form["score_pct"] >= 90.0
        xg_block = next(b for b in dq_form["blocks"] if b["key"] == "xg")
        assert xg_block["earned"] >= 14.0

        adjusted, debug = apply_league_probability_profile({"home": 0.62, "draw": 0.18, "away": 0.20}, "LEAGUE_TWO")
        assert round(sum(adjusted.values()), 5) == 1.0
        assert debug["label"] == "English lower-league profile"
        assert value_margin_extra("LEAGUE_TWO", 65) > value_margin_extra("EPL", 90)
        print("  ✓ Field quality and league profiles exposed")
        return True
    except Exception as e:
        print(f"  ✗ Field quality / league profile test failed: {e}")
        return False


def test_insights_trust_digest_and_audit():
    """Insights include trust digest, avoid list and audit placeholder."""
    print("\nTesting insights trust digest...")
    try:
        from hibs_predictor.insights import build_insights

        fixtures = [
            {
                "id": 300,
                "home": "Top FC",
                "away": "Thin Data FC",
                "date": "2026-05-18T15:00:00+00:00",
                "league": "EPL",
                "league_name": "Premier League",
                "home_last10": [],
                "away_last10": [],
                "home_position": {"position": 1},
                "away_position": {"position": 18},
                "fixture_injuries": [],
                "xg_source": "goals_proxy",
                "has_value_bet": False,
                "data_quality": {
                    "score_pct": 58,
                    "trust_label": "Thin data",
                    "weak_fields": ["Expected goals", "Team news / context"],
                    "field_scores": {},
                    "blocks": [],
                },
                "prediction": {
                    "prediction_unavailable": False,
                    "structured_insight": {"pick_key": "avoid", "pick": "AVOID", "rationale": []},
                    "pick_menu": [],
                    "probability_scores": {"home_win_pct": 55, "draw_pct": 25, "away_win_pct": 20},
                    "value_bets_display": [],
                    "value_bets_rejected": {"away": "low_probability_longshot"},
                    "bookmaker_odds": {"home": 1.6, "draw": 4.0, "away": 6.0},
                    "line_odds": {},
                },
            }
        ]
        insights = build_insights(fixtures)
        assert insights["trust_digest"]["labels"]["Thin data"] == 1
        assert insights["trust_digest"]["weak_fields"][0]["label"] == "Expected goals"
        assert insights["avoid_watchlist"]
        assert "audit" in insights
        print("  ✓ Insights trust digest built")
        return True
    except Exception as e:
        print(f"  ✗ Insights trust digest test failed: {e}")
        return False


def test_templates():
    """Test template loading."""
    print("\nTesting templates...")
    try:
        from jinja2 import Environment, FileSystemLoader
        template_dir = os.path.join(os.path.dirname(__file__), 'templates')
        env = Environment(loader=FileSystemLoader(template_dir))
        templates = ["base.html", "dashboard.html", "acca_builder.html", "api_status.html", "insights.html", "tables.html", "guide.html", "settings.html"]
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
        test_insights_tables_routes_and_snapshots,
        test_api_health_prediction_quality,
        test_api_cache_clear,
        test_structured_insight,
        test_value_edge_fields,
        test_bottom_top_underdog_not_home_value,
        test_pick_menu,
        test_dashboard_days_grouping,
        test_competition_display_titles,
        test_kickoff_display_tz,
        test_fixture_window_includes_todays_kicked_off,
        test_nordic_leagues_configured,
        test_calendar_year_season_candidate,
        test_live_scores_merge_mocked,
        test_sky_sports_news_media_config,
        test_fotmob_adapter_mocked,
        test_football_data_standings_mocked,
        test_table_rows_use_previous_season_standings,
        test_scottish_fbref_xg,
        test_fdo_recent_matches_for_serie_a_shape,
        test_understat_serie_a_name_match,
        test_understat_scraped_xg_coverage,
        test_fbref_schedule_xg_championship,
        test_soccerstats_standings_parse,
        test_scraped_xg_resolution,
        test_assistant_recommendations,
        test_insights_and_bet_builders,
        test_assistant_chat,
        test_assistant_freeform_clarifies_ambiguity,
        test_field_quality_and_league_profile,
        test_insights_trust_digest_and_audit,
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
