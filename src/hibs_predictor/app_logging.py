"""Application file logging (Flask + hibs modules). Does not alter enrich or predictions."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


def _env_on(name: str, default: str = "0") -> bool:
    return (os.getenv(name, default) or default).strip().lower() not in ("0", "false", "no", "off")


def app_log_enabled() -> bool:
    return _env_on("HIBS_APP_LOG_ENABLED", "1")


def app_log_path(base_dir: str) -> Path:
    raw = (os.getenv("HIBS_APP_LOG_FILE") or "").strip()
    if raw:
        p = Path(raw)
        return p if p.is_absolute() else Path(base_dir) / p
    return Path(base_dir) / "logs" / "hibs-bet.log"


def _log_level() -> int:
    raw = (os.getenv("HIBS_APP_LOG_LEVEL") or "INFO").strip().upper()
    return getattr(logging, raw, logging.INFO)


class _StreamToLogger:
    """Forward print() lines to the hibs logger (best-effort; keeps console output)."""

    def __init__(self, stream, logger: logging.Logger, level: int) -> None:
        self._stream = stream
        self._logger = logger
        self._level = level

    def write(self, data: str) -> None:
        self._stream.write(data)
        text = (data or "").strip()
        if text:
            for line in text.splitlines():
                line = line.strip()
                if line:
                    self._logger.log(self._level, line)

    def flush(self) -> None:
        self._stream.flush()

    def isatty(self) -> bool:
        return self._stream.isatty()


def configure_app_logging(base_dir: str, *, tee_stdio: bool = True) -> Optional[Path]:
    """
    Enable rotating file log under ``logs/hibs-bet.log`` (or ``HIBS_APP_LOG_FILE``).
    Safe to call multiple times; only configures once per process.
    """
    if not app_log_enabled():
        return None
    if getattr(configure_app_logging, "_configured", False):
        return getattr(configure_app_logging, "_path", None)

    path = app_log_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    level = _log_level()
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger("hibs")
    root.setLevel(level)
    root.handlers.clear()

    fh = RotatingFileHandler(
        path,
        maxBytes=int(os.getenv("HIBS_APP_LOG_MAX_BYTES", str(5 * 1024 * 1024))),
        backupCount=int(os.getenv("HIBS_APP_LOG_BACKUP_COUNT", "5")),
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)

    if _env_on("HIBS_APP_LOG_CONSOLE", "1"):
        ch = logging.StreamHandler(sys.stderr)
        ch.setFormatter(fmt)
        root.addHandler(ch)

    if _env_on("HIBS_APP_LOG_HTTP", "1"):
        wz = logging.getLogger("werkzeug")
        wz.setLevel(logging.INFO)
        wz.handlers.clear()
        wz.addHandler(fh)
        if _env_on("HIBS_APP_LOG_CONSOLE", "1"):
            wz.addHandler(ch)
        wz.propagate = False

    root.info("hibs-bet file logging enabled → %s", path)

    if tee_stdio and _env_on("HIBS_APP_LOG_TEE_STDIO", "1"):
        sys.stdout = _StreamToLogger(sys.stdout, root, logging.INFO)  # type: ignore[assignment]
        sys.stderr = _StreamToLogger(sys.stderr, root, logging.ERROR)  # type: ignore[assignment]

    configure_app_logging._configured = True  # type: ignore[attr-defined]
    configure_app_logging._path = path  # type: ignore[attr-defined]
    return path


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"hibs.{name}")
