"""Session-based login for hibs-bet (optional via HIBS_AUTH_ENABLED)."""

from __future__ import annotations

import os
import secrets
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

from flask import Flask, jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash

F = TypeVar("F", bound=Callable[..., Any])

SESSION_AUTH_KEY = "hibs_authenticated"
DEFAULT_USERNAME = "admin"
PASSWORD_ENV_KEYS = ("HIBS_AUTH_PASSWORD", "HIBS_HIBS_PASSWORD")


def _env_truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def configured_password() -> str:
    for key in PASSWORD_ENV_KEYS:
        value = (os.getenv(key) or "").strip()
        if value:
            return value
    return ""


def password_configured() -> bool:
    return bool(configured_password())


def auth_enabled() -> bool:
    return _env_truthy("HIBS_AUTH_ENABLED")


def public_health_enabled() -> bool:
    return _env_truthy("HIBS_AUTH_PUBLIC_HEALTH")


def configured_username() -> str:
    return (os.getenv("HIBS_AUTH_USERNAME") or DEFAULT_USERNAME).strip() or DEFAULT_USERNAME


def is_logged_in() -> bool:
    if not auth_enabled():
        return True
    return bool(session.get(SESSION_AUTH_KEY))


def safe_next_url(raw: Optional[str]) -> str:
    if not raw:
        return "/"
    if not raw.startswith("/") or raw.startswith("//"):
        return "/"
    return raw


def _auth_required_response():
    if request.path.startswith("/api/") or (
        request.accept_mimetypes.best == "application/json"
        and request.accept_mimetypes[request.accept_mimetypes.best] > request.accept_mimetypes["text/html"]
    ):
        return jsonify({"error": "login_required"}), 401
    return redirect(url_for("login", next=safe_next_url(request.full_path if request.query_string else request.path)))


def _password_matches(stored: str, password: str) -> bool:
    if stored.startswith(("pbkdf2:", "scrypt:")):
        return check_password_hash(stored, password or "")
    return secrets.compare_digest(password or "", stored)


def check_password(password: str) -> bool:
    stored = configured_password()
    if not stored:
        return False
    return _password_matches(stored, password or "")


def check_credentials(username: str, password: str) -> bool:
    stored = configured_password()
    if not stored:
        return False
    expected_user = configured_username()
    user_ok = secrets.compare_digest((username or "").strip(), expected_user)
    if not user_ok:
        secrets.compare_digest("x", "y")
        return False
    return _password_matches(stored, password or "")


def login_user() -> None:
    session[SESSION_AUTH_KEY] = True
    session.permanent = True


def logout_user() -> None:
    session.pop(SESSION_AUTH_KEY, None)


def validate_auth_config() -> None:
    if not auth_enabled():
        return
    secret = (os.getenv("HIBS_SECRET_KEY") or "").strip()
    if not secret:
        raise RuntimeError("HIBS_SECRET_KEY is required when HIBS_AUTH_ENABLED=1")
    if not password_configured():
        raise RuntimeError(
            "HIBS_AUTH_PASSWORD or HIBS_HIBS_PASSWORD is required when HIBS_AUTH_ENABLED=1"
        )


def init_app(app: Flask) -> None:
    validate_auth_config()
    secret = (os.getenv("HIBS_SECRET_KEY") or "").strip()
    app.secret_key = secret or "hibs-dev-insecure-secret"
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")


def login_required(view: Optional[F] = None, *, allow_public_health: bool = False) -> Any:
    def decorator(f: F) -> F:
        @wraps(f)
        def wrapped(*args: Any, **kwargs: Any):
            if not auth_enabled():
                return f(*args, **kwargs)
            if allow_public_health and public_health_enabled():
                return f(*args, **kwargs)
            if is_logged_in():
                return f(*args, **kwargs)
            return _auth_required_response()

        return wrapped  # type: ignore[return-value]

    if view is not None:
        return decorator(view)
    return decorator
