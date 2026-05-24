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


def _env_truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


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


def check_credentials(username: str, password: str) -> bool:
    expected_user = configured_username()
    stored = (os.getenv("HIBS_AUTH_PASSWORD") or "").strip()
    if not stored:
        return False
    user_ok = secrets.compare_digest((username or "").strip(), expected_user)
    if stored.startswith(("pbkdf2:", "scrypt:")):
        pass_ok = check_password_hash(stored, password or "")
    else:
        pass_ok = secrets.compare_digest(password or "", stored)
    if not user_ok:
        secrets.compare_digest("x", "y")
        return False
    return pass_ok


def login_user() -> None:
    session[SESSION_AUTH_KEY] = True
    session.permanent = True


def logout_user() -> None:
    session.pop(SESSION_AUTH_KEY, None)


def init_app(app: Flask) -> None:
    secret = (os.getenv("HIBS_SECRET_KEY") or "").strip()
    if auth_enabled() and not secret:
        raise RuntimeError("HIBS_SECRET_KEY is required when HIBS_AUTH_ENABLED=1")
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
