from __future__ import annotations

from unittest.mock import patch

import requests

from hibs_predictor.api_clients import BaseApiClient, FootballDataOrgClient


def _http_error(status: int) -> requests.HTTPError:
    resp = requests.Response()
    resp.status_code = status
    return requests.HTTPError(f"http {status}", response=resp)


def test_fdo_403_is_short_cached(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    client = FootballDataOrgClient("dummy")
    endpoint = "competitions/PL/matches"
    params = {"season": 2025}

    with patch("hibs_predictor.api_clients.BaseApiClient._get_json", side_effect=_http_error(403)):
        first = client._get_json(endpoint, params=params, use_cache=True)
    assert first.get("errorCode") == 403

    with patch("hibs_predictor.api_clients.BaseApiClient._get_json", side_effect=AssertionError("should use deny-cache")):
        second = client._get_json(endpoint, params=params, use_cache=True)
    assert second.get("errorCode") == 403


class _DummyClient(BaseApiClient):
    def __init__(self):
        super().__init__("k", "https://example.com", "X-Test", "dummy")


def test_base_client_local_rate_limit_uses_stale_cache(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    client = _DummyClient()
    endpoint = "foo"
    params = {"a": 1}
    cache_key = f"dummy_{endpoint}_{str(params)}"
    client.cache.set(cache_key, {"ok": 1}, ttl_hours=4)
    with patch.object(client.rate_limiter, "check_rate_limit", return_value=False):
        data = client._get_json(endpoint, params=params, use_cache=True)
    assert data == {"ok": 1}
