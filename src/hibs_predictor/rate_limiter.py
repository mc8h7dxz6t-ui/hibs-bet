"""Rate limiter for tracking API calls against free-tier limits."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict


class RateLimiter:
    def __init__(self, state_file: str = ".rate_limit_state.json") -> None:
        self.state_file = Path(state_file)
        self.limits = {
            "football_data_org": 100,
            "api_sports": 150,
            "sportsmonk": 150,
            "odds_api": 500,
            "stats_api": 150,
        }
        self._load_state()

    def _load_state(self) -> None:
        if self.state_file.exists():
            with open(self.state_file, "r") as f:
                self.state = json.load(f)
        else:
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
