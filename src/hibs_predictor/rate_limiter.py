"""Rate limiter for tracking API calls against free-tier limits."""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional


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
        self.minute_limits = {
            "api_sports": int(os.getenv("HIBS_API_SPORTS_PER_MIN_LIMIT", "22")),
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
        self.state = {
            key: {"count": 0, "reset_at": None, "minute_count": 0, "minute_reset_at": None}
            for key in self.limits
        }

    def _ensure_entry_shape(self, service: str) -> Dict[str, object]:
        if service not in self.state or not isinstance(self.state.get(service), dict):
            self.state[service] = {
                "count": 0,
                "reset_at": None,
                "minute_count": 0,
                "minute_reset_at": None,
            }
        entry = self.state[service]
        if "minute_count" not in entry:
            entry["minute_count"] = 0
        if "minute_reset_at" not in entry:
            entry["minute_reset_at"] = None
        if "count" not in entry:
            entry["count"] = 0
        if "reset_at" not in entry:
            entry["reset_at"] = None
        return entry

    def _save_state(self) -> None:
        with open(self.state_file, "w") as f:
            json.dump(self.state, f)

    def _hour_window_active(self, entry: Dict[str, object]) -> bool:
        reset_at = entry.get("reset_at")
        return bool(reset_at and datetime.fromisoformat(str(reset_at)) > datetime.now())

    def _minute_window_active(self, entry: Dict[str, object]) -> bool:
        minute_reset_at = entry.get("minute_reset_at")
        return bool(minute_reset_at and datetime.fromisoformat(str(minute_reset_at)) > datetime.now())

    def block_reason(self, service: str) -> Optional[str]:
        """Why a request is blocked: local guard (minute/hour) or None if allowed."""
        if service not in self.limits:
            return None
        entry = self._ensure_entry_shape(service)
        if self._hour_window_active(entry):
            count = int(entry.get("count", 0) or 0)
            if count >= self.limits[service]:
                return "guard_hour"
        minute_limit = self.minute_limits.get(service, 0)
        if minute_limit > 0 and self._minute_window_active(entry):
            minute_count = int(entry.get("minute_count", 0) or 0)
            if minute_count >= minute_limit:
                return "guard_minute"
        return None

    def check_rate_limit(self, service: str) -> bool:
        return self.block_reason(service) is None

    def record_request(self, service: str) -> None:
        entry = self._ensure_entry_shape(service)
        reset_at = entry.get("reset_at")

        if reset_at is None or datetime.fromisoformat(reset_at) <= datetime.now():
            entry["count"] = 1
            entry["reset_at"] = (datetime.now() + timedelta(hours=1)).isoformat()
        else:
            entry["count"] = entry.get("count", 0) + 1

        minute_limit = self.minute_limits.get(service, 0)
        if minute_limit > 0:
            minute_reset_at = entry.get("minute_reset_at")
            if minute_reset_at is None or datetime.fromisoformat(str(minute_reset_at)) <= datetime.now():
                entry["minute_count"] = 1
                entry["minute_reset_at"] = (datetime.now() + timedelta(minutes=1)).isoformat()
            else:
                entry["minute_count"] = int(entry.get("minute_count", 0) or 0) + 1

        self._save_state()

    def get_stats(self, service: str) -> Dict[str, any]:
        entry = self._ensure_entry_shape(service)
        return {
            "count": entry.get("count", 0),
            "limit": self.limits.get(service, 0),
            "reset_at": entry.get("reset_at"),
            "minute_count": entry.get("minute_count", 0),
            "minute_limit": self.minute_limits.get(service, 0),
            "minute_reset_at": entry.get("minute_reset_at"),
        }

    def reset_service(self, service: str) -> None:
        """Clear hourly counter for one provider (e.g. after fixture cache clear)."""
        if service in self.limits:
            self.state[service] = {
                "count": 0,
                "reset_at": None,
                "minute_count": 0,
                "minute_reset_at": None,
            }
            self._save_state()

    def reset_all(self) -> None:
        """Clear all provider counters."""
        self.state = {
            key: {"count": 0, "reset_at": None, "minute_count": 0, "minute_reset_at": None}
            for key in self.limits
        }
        self._save_state()

    def is_blocked(self, service: str) -> bool:
        return self.block_reason(service) is not None

    def diagnostics(self, service: str) -> Dict[str, object]:
        """Expose guard state for logs and /status-style probes."""
        entry = self._ensure_entry_shape(service)
        reason = self.block_reason(service)
        return {
            "service": service,
            "blocked": reason is not None,
            "block_reason": reason,
            "hour_count": int(entry.get("count", 0) or 0),
            "hour_limit": self.limits.get(service, 0),
            "hour_reset_at": entry.get("reset_at"),
            "minute_count": int(entry.get("minute_count", 0) or 0),
            "minute_limit": self.minute_limits.get(service, 0),
            "minute_reset_at": entry.get("minute_reset_at"),
        }
