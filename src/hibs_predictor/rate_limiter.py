"""Rate limiter for tracking API calls against free-tier limits."""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict


class RateLimiter:
    def __init__(self, state_file: str = ".rate_limit_state.json") -> None:
        self.state_file = Path(state_file)
        api_default = "1200" if (os.getenv("HIBS_DEV_FULL_DQ") or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        ) else "400"
        self.limits = {
            "football_data_org": 100,
            "api_sports": int(os.getenv("HIBS_API_SPORTS_HOURLY_LIMIT", api_default)),
            "sportsmonk": 150,
            "odds_api": 500,
            "stats_api": 150,
        }
        self._load_state()

    def _load_state(self) -> None:
        if self.state_file.exists():
            try:
                with open(self.state_file, "r") as f:
                    self.state = json.load(f)
                if not isinstance(self.state, dict):
                    raise ValueError("rate limit state is not an object")
                return
            except (json.JSONDecodeError, ValueError, OSError):
                pass
        self.state = {key: {"count": 0, "reset_at": None} for key in self.limits}

    def _save_state(self) -> None:
        with open(self.state_file, "w") as f:
            json.dump(self.state, f)

    def check_rate_limit(self, service: str) -> bool:
        if service not in self.limits:
            return True

        entry = self.state.get(service, {})
        reset_at = entry.get("reset_at")

        if reset_at and datetime.fromisoformat(reset_at) > datetime.now():
            count = entry.get("count", 0)
            return count < self.limits[service]

        return True

    def record_request(self, service: str) -> None:
        if service not in self.state:
            self.state[service] = {"count": 0, "reset_at": None}

        entry = self.state[service]
        reset_at = entry.get("reset_at")

        if reset_at is None or datetime.fromisoformat(reset_at) <= datetime.now():
            entry["count"] = 1
            entry["reset_at"] = (datetime.now() + timedelta(hours=1)).isoformat()
        else:
            entry["count"] = entry.get("count", 0) + 1

        self._save_state()

    def get_stats(self, service: str) -> Dict[str, any]:
        entry = self.state.get(service, {})
        return {
            "count": entry.get("count", 0),
            "limit": self.limits.get(service, 0),
            "reset_at": entry.get("reset_at"),
        }

    def reset_service(self, service: str) -> None:
        """Clear hourly counter for one provider (e.g. after fixture cache clear)."""
        if service in self.limits:
            self.state[service] = {"count": 0, "reset_at": None}
            self._save_state()

    def reset_all(self) -> None:
        """Clear all provider counters."""
        self.state = {key: {"count": 0, "reset_at": None} for key in self.limits}
        self._save_state()

    def is_blocked(self, service: str) -> bool:
        return not self.check_rate_limit(service)
