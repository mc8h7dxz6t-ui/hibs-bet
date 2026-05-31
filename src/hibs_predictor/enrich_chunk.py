"""Chunked processing for API-heavy enrich passes (Football-Data.org 10 req/min guard)."""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Iterable, List, TypeVar

T = TypeVar("T")


def enrich_chunk_size() -> int:
    try:
        return max(1, int(os.getenv("HIBS_ENRICH_CHUNK_SIZE", "8")))
    except ValueError:
        return 8


def enrich_chunk_pause_seconds() -> float:
    try:
        return max(0.0, float(os.getenv("HIBS_ENRICH_CHUNK_PAUSE_SEC", "65")))
    except ValueError:
        return 65.0


def chunked_enrich_enabled() -> bool:
    raw = (os.getenv("HIBS_ENRICH_CHUNKED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def process_in_chunks(
    items: Iterable[T],
    worker: Callable[[T], Any],
    *,
    chunk_size: int | None = None,
    pause_seconds: float | None = None,
    enabled: bool | None = None,
) -> List[Any]:
    """
    Run ``worker`` over ``items`` in blocks; pause between blocks when chunked mode is on.

    Used by league fixture builds so a Saturday card does not trip Football-Data.org 10/min caps.
    """
    seq = list(items)
    if not seq:
        return []
    if enabled is None:
        enabled = chunked_enrich_enabled()
    if not enabled:
        return [worker(x) for x in seq]

    size = chunk_size if chunk_size is not None else enrich_chunk_size()
    pause = pause_seconds if pause_seconds is not None else enrich_chunk_pause_seconds()
    out: List[Any] = []
    for i in range(0, len(seq), size):
        block = seq[i : i + size]
        for item in block:
            out.append(worker(item))
        if i + size < len(seq) and pause > 0:
            time.sleep(pause)
    return out
