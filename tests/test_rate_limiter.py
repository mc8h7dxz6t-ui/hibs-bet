"""API rate-limit state (local hourly guard)."""

from __future__ import annotations

import json
from pathlib import Path

from hibs_predictor.rate_limiter import RateLimiter


def test_reset_all_clears_blocked_counter(tmp_path, monkeypatch):
    monkeypatch.delenv("HIBS_DEV_FULL_DQ", raising=False)
    monkeypatch.setenv("HIBS_API_SPORTS_HOURLY_LIMIT", "400")
    state = tmp_path / "limits.json"
    state.write_text(
        json.dumps(
            {
                "api_sports": {"count": 403, "reset_at": "2099-01-01T00:00:00"},
            }
        )
    )
    monkeypatch.chdir(tmp_path)
    rl = RateLimiter(state_file=str(state.name))
    assert rl.is_blocked("api_sports") is True
    rl.reset_all()
    assert rl.is_blocked("api_sports") is False


def test_api_sports_minute_limit_blocks_when_exceeded(tmp_path, monkeypatch):
    monkeypatch.delenv("HIBS_DEV_FULL_DQ", raising=False)
    monkeypatch.setenv("HIBS_API_SPORTS_HOURLY_LIMIT", "400")
    monkeypatch.setenv("HIBS_API_SPORTS_PER_MIN_LIMIT", "2")
    state = tmp_path / "limits.json"
    monkeypatch.chdir(tmp_path)
    rl = RateLimiter(state_file=str(state.name))
    assert rl.check_rate_limit("api_sports") is True
    rl.record_request("api_sports")
    assert rl.check_rate_limit("api_sports") is True
    rl.record_request("api_sports")
    assert rl.check_rate_limit("api_sports") is False
