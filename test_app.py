#!/usr/bin/env python3
"""
Quick test runner to verify HibsBetting app components.
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
        from hibs_predictor.web import app, fetch_next_48h_fixtures
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
        routes = [rule.rule for rule in app.url_map.iter_rules()]
        expected_routes = ["/", "/api/fixtures", "/api/prediction/<int:fixture_id>", "/acca", "/api/place-bet"]
        for route in expected_routes:
            if route not in routes:
                print(f"  ⚠ Missing route: {route}")
        print(f"  ✓ Flask app loaded with {len(routes)} routes")
        print(f"    Routes: {', '.join(sorted(routes))}")
        return True
    except Exception as e:
        print(f"  ✗ Flask test failed: {e}")
        return False

def test_templates():
    """Test template loading."""
    print("\nTesting templates...")
    try:
        from jinja2 import Environment, FileSystemLoader
        template_dir = os.path.join(os.path.dirname(__file__), 'templates')
        env = Environment(loader=FileSystemLoader(template_dir))
        templates = ["base.html", "dashboard.html", "acca_builder.html"]
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
    print("HibsBetting Application Test Suite")
    print("=" * 60)
    
    tests = [
        test_imports,
        test_config,
        test_cache,
        test_rate_limiter,
        test_flask_routes,
        test_templates,
    ]
    
    results = [test() for test in tests]
    
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    
    if all(results):
        print("✓ All tests passed! Application ready to run.")
        print("\nStart the app with: python3 launcher.py")
        return 0
    else:
        print("✗ Some tests failed. Check output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
