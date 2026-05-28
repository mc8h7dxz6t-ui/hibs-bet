"""Session auth for hibs-bet web routes."""

from __future__ import annotations

import importlib

import pytest


def _reload_web(monkeypatch, **env):
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    import hibs_predictor.auth as auth_mod
    import hibs_predictor.web as web_mod

    importlib.reload(auth_mod)
    web = importlib.reload(web_mod)
    monkeypatch.setattr(web, "_sky_dock_context", lambda: {"show_sky_panel": False})
    monkeypatch.setattr(
        web,
        "_players_dock_context",
        lambda **kwargs: {
            "show_players_dock": False,
            "players_dock_groups": [],
            "players_dock_cold_start": False,
        },
    )
    monkeypatch.setattr(
        "hibs_predictor.web.gather_health",
        lambda: {"ok": True, "sources": []},
    )
    return web


def _login(client, password="testpass"):
    return client.post(
        "/login",
        data={"password": password, "next": "/"},
        follow_redirects=False,
    )


def test_routes_public_when_auth_disabled(monkeypatch):
    web = _reload_web(
        monkeypatch,
        HIBS_AUTH_ENABLED="0",
        HIBS_SECRET_KEY="",
    )
    client = web.app.test_client()
    assert client.get("/login").status_code == 302
    assert client.get("/").status_code in (200, 304)
    assert client.get("/api/health").status_code == 200
    assert client.post("/api/cache/clear").status_code == 200


def test_routes_require_login_when_auth_enabled(monkeypatch):
    web = _reload_web(
        monkeypatch,
        HIBS_AUTH_ENABLED="1",
        HIBS_AUTH_PASSWORD="testpass",
        HIBS_SECRET_KEY="test-secret-key",
    )
    client = web.app.test_client()
    assert client.get("/").status_code == 302
    assert client.get("/").headers["Location"].startswith("/login")
    api = client.get("/api/health")
    assert api.status_code == 401
    assert api.get_json()["error"] == "login_required"
    assert client.post("/api/cache/clear").status_code == 401


def test_login_logout_flow(monkeypatch):
    web = _reload_web(
        monkeypatch,
        HIBS_AUTH_ENABLED="1",
        HIBS_AUTH_PASSWORD="testpass",
        HIBS_SECRET_KEY="test-secret-key",
    )
    client = web.app.test_client()
    bad = _login(client, password="wrong")
    assert bad.status_code == 200
    assert b"Incorrect password" in bad.data

    ok = _login(client)
    assert ok.status_code == 302
    assert ok.headers["Location"] == "/"

    with client.session_transaction() as sess:
        assert sess.get("hibs_authenticated") is True

    assert client.get("/settings").status_code == 200
    assert client.get("/api/health").status_code == 200

    out = client.get("/logout")
    assert out.status_code == 302
    assert out.headers["Location"].endswith("/login")
    assert client.get("/settings").status_code == 302


def test_hibs_hibs_password_alias(monkeypatch):
    web = _reload_web(
        monkeypatch,
        HIBS_AUTH_ENABLED="1",
        HIBS_AUTH_PASSWORD=None,
        HIBS_HIBS_PASSWORD="alias-pass",
        HIBS_SECRET_KEY="test-secret-key",
    )
    client = web.app.test_client()
    ok = _login(client, password="alias-pass")
    assert ok.status_code == 302
    assert client.get("/settings").status_code == 200


def test_public_health_when_configured(monkeypatch):
    web = _reload_web(
        monkeypatch,
        HIBS_AUTH_ENABLED="1",
        HIBS_AUTH_PASSWORD="testpass",
        HIBS_SECRET_KEY="test-secret-key",
        HIBS_AUTH_PUBLIC_HEALTH="1",
    )
    client = web.app.test_client()
    assert client.get("/api/health").status_code == 200
    assert client.get("/status").status_code == 302


def test_auth_enabled_requires_secret_key(monkeypatch):
    monkeypatch.setenv("HIBS_AUTH_ENABLED", "1")
    monkeypatch.setenv("HIBS_AUTH_PASSWORD", "testpass")
    monkeypatch.delenv("HIBS_SECRET_KEY", raising=False)
    import hibs_predictor.auth as auth_mod
    import hibs_predictor.web as web_mod

    importlib.reload(auth_mod)
    with pytest.raises(RuntimeError, match="HIBS_SECRET_KEY"):
        importlib.reload(web_mod)


def test_auth_enabled_requires_password(monkeypatch):
    monkeypatch.setenv("HIBS_AUTH_ENABLED", "1")
    monkeypatch.delenv("HIBS_AUTH_PASSWORD", raising=False)
    monkeypatch.delenv("HIBS_HIBS_PASSWORD", raising=False)
    monkeypatch.setenv("HIBS_SECRET_KEY", "test-secret-key")
    import hibs_predictor.auth as auth_mod
    import hibs_predictor.web as web_mod

    importlib.reload(auth_mod)
    with pytest.raises(RuntimeError, match="HIBS_AUTH_PASSWORD"):
        importlib.reload(web_mod)
