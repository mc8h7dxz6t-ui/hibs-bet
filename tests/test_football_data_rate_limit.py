"""Football-Data.org local 10 req/min guard."""

from unittest.mock import patch

from hibs_predictor.api_clients import FootballDataOrgClient
from hibs_predictor.rate_limiter import RateLimiter


def test_football_data_minute_guard_blocks_at_limit(monkeypatch, tmp_path):
    state = tmp_path / "rl.json"
    monkeypatch.setenv("HIBS_FOOTBALL_DATA_PER_MIN_LIMIT", "3")
    rl = RateLimiter(state_file=str(state))
    for _ in range(3):
        rl.record_request("football_data_org")
    assert rl.block_reason("football_data_org") == "guard_minute"


def test_fdo_client_skips_http_when_minute_guard_full(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HIBS_FOOTBALL_DATA_PER_MIN_LIMIT", "1")
    RateLimiter().record_request("football_data_org")
    client = FootballDataOrgClient("dummy")
    with patch("hibs_predictor.api_clients.BaseApiClient._get_json") as base_get:
        out = client._get_json("competitions/PL/matches", params={"season": 2025})
    base_get.assert_not_called()
    assert out.get("errorCode") == 429
