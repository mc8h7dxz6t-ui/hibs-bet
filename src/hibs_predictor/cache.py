"""Local caching system for API responses with TTL."""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional


class Cache:
    def __init__(self, cache_dir: str = ".cache") -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

    def _sanitize_key(self, key: str) -> str:
        return "".join(
            c if c.isalnum() or c in '._-' else '_' for c in key
        )

    def _get_cache_path(self, key: str) -> Path:
        sanitized_key = self._sanitize_key(key)
        return self.cache_dir / f"{sanitized_key}.json"

    def get(self, key: str, ttl_hours: int = 4) -> Optional[Any]:
        path = self._get_cache_path(key)
        if not path.exists():
            return None

        with open(path, "r") as f:
            data = json.load(f)

        cached_at = datetime.fromisoformat(data.get("cached_at", ""))
        if datetime.now() - cached_at > timedelta(hours=ttl_hours):
            path.unlink()
            return None

        return data.get("value")

    def set(self, key: str, value: Any) -> None:
        path = self._get_cache_path(key)
        data = {
            "cached_at": datetime.now().isoformat(),
            "value": value,
        }
        with open(path, "w") as f:
            json.dump(data, f)

    def clear(self) -> None:
        for file in self.cache_dir.glob("*.json"):
            file.unlink()
