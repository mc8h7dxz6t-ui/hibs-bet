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
