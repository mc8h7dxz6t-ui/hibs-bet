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
            "/api/audit/summary",
            "/acca",
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
        templates = ["base.html", "dashboard.html", "acca_builder.html", "api_status.html"]
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
        test_structured_insight,
        test_value_edge_fields,
        test_pick_menu,
        test_dashboard_days_grouping,
        test_kickoff_display_tz,
        test_assistant_recommendations,
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
