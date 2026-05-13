"""Local caching system with TTL metadata and safe on-disk stale pruning."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional


class Cache:
    def __init__(self, cache_dir: str = ".cache") -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

    def _sanitize_key(self, key: str) -> str:
        return "".join(c if c.isalnum() or c in "._-" else "_" for c in key)

    def _get_cache_path(self, key: str) -> Path:
        sanitized_key = self._sanitize_key(key)
        return self.cache_dir / f"{sanitized_key}.json"

    def get(self, key: str, ttl_hours: float = 4.0) -> Optional[Any]:
        path = self._get_cache_path(key)
        if not path.exists():
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError, TypeError):
            try:
                path.unlink()
            except OSError:
                pass
            return None

        try:
            cached_at = datetime.fromisoformat(data.get("cached_at", ""))
        except (TypeError, ValueError, OSError):
            try:
                path.unlink()
            except OSError:
                pass
            return None

        stored_ttl = data.get("ttl_hours")
        effective_ttl = float(stored_ttl) if stored_ttl is not None else float(ttl_hours)
        if effective_ttl <= 0:
            effective_ttl = float(ttl_hours)

        if datetime.now() - cached_at > timedelta(hours=effective_ttl):
            try:
                path.unlink()
            except OSError:
                pass
            return None

        return data.get("value")

    def set(self, key: str, value: Any, ttl_hours: float = 4.0) -> None:
        path = self._get_cache_path(key)
        data = {
            "cached_at": datetime.now().isoformat(),
            "ttl_hours": float(ttl_hours),
            "value": value,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def clear(self) -> None:
        for file in self.cache_dir.glob("*.json"):
            file.unlink()

    def prune_stale(self, *, legacy_unknown_ttl_hours: float = 168.0) -> int:
        """Delete cache files that are past TTL.

        Entries written with ``set(..., ttl_hours=…)`` carry that TTL on disk and
        expire accordingly. Older files without ``ttl_hours`` use ``legacy_unknown_ttl_hours``
        (default 7 days) so we do not delete unknown-age entries too aggressively.

        Corrupt JSON files are removed. Returns the number of files deleted.
        """
        removed = 0
        now = datetime.now()
        for path in self.cache_dir.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError, TypeError):
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    pass
                continue

            try:
                cached_at = datetime.fromisoformat(data.get("cached_at", ""))
            except (TypeError, ValueError):
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    pass
                continue

            stored_ttl = data.get("ttl_hours")
            if stored_ttl is not None:
                try:
                    effective = float(stored_ttl)
                except (TypeError, ValueError):
                    effective = float(legacy_unknown_ttl_hours)
                if effective <= 0:
                    effective = float(legacy_unknown_ttl_hours)
            else:
                effective = float(legacy_unknown_ttl_hours)

            if now - cached_at > timedelta(hours=effective):
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    pass

        return removed
