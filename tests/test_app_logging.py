"""App file logging configuration."""

import logging
from pathlib import Path

from hibs_predictor import app_logging as al


def test_configure_app_logging_creates_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HIBS_APP_LOG_ENABLED", "1")
    monkeypatch.setenv("HIBS_APP_LOG_FILE", str(tmp_path / "test.log"))
    monkeypatch.setenv("HIBS_APP_LOG_TEE_STDIO", "0")
    monkeypatch.setenv("HIBS_APP_LOG_HTTP", "0")
    al.configure_app_logging._configured = False  # type: ignore[attr-defined]
    path = al.configure_app_logging(str(tmp_path), tee_stdio=False)
    assert path is not None
    assert path.exists()
    log = al.get_logger("test")
    log.info("hello")
    for h in logging.getLogger("hibs").handlers:
        h.flush()
    assert "hello" in path.read_text(encoding="utf-8")
