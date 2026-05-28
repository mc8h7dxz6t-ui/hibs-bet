"""API client rate-limit guard vs provider diagnostics."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from hibs_predictor.api_clients import ApiSportsFootballClient


def test_api_sports_local_guard_returns_block_reason_without_stale(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = ApiSportsFootballClient("test-key")
    client.rate_limiter.state["api_sports"] = {
        "count": 0,
        "reset_at": None,
        "minute_count": 99,
        "minute_reset_at": "2099-01-01T00:00:00",
    }
    client.rate_limiter.limits["api_sports"] = 400
    client.rate_limiter.minute_limits["api_sports"] = 2
    out = client._get_json("injuries", params={"fixture": 1}, use_cache=False)
    assert out.get("errors", {}).get("block_reason") == "guard_minute"


def test_api_sports_reuses_stale_on_local_guard(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = ApiSportsFootballClient("test-key")
    cache_key = f"api_sports_injuries_{str({'fixture': 1})}"
    stale = {"response": [{"player": {"name": "Test"}}], "results": 1}
    client.cache.set(cache_key, stale, ttl_hours=4)
    client.rate_limiter.state["api_sports"] = {
        "count": 500,
        "reset_at": "2099-01-01T00:00:00",
        "minute_count": 0,
        "minute_reset_at": None,
    }
    with patch.object(client.cache, "get", return_value=None):
        out = client._get_json("injuries", params={"fixture": 1}, use_cache=True)
    assert out.get("response") == stale["response"]
