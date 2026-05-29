"""Football-Data.org local 10 req/min guard."""

from hibs_predictor.rate_limiter import RateLimiter


def test_football_data_minute_guard_blocks_at_limit(monkeypatch, tmp_path):
    state = tmp_path / "rl.json"
    monkeypatch.setenv("HIBS_FOOTBALL_DATA_PER_MIN_LIMIT", "3")
    rl = RateLimiter(state_file=str(state))
    for _ in range(3):
        rl.record_request("football_data_org")
    assert rl.block_reason("football_data_org") == "guard_minute"
