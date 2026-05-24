"""FBref client: season URLs, 403 handling, cache, health probe."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from hibs_predictor.scrapers import fbref_client as fr


def test_fbref_season_labels_may_2026():
    from hibs_predictor.season import fbref_season_labels

    labels = fbref_season_labels("EPL")
    assert labels[0] == "2025-2026"


def test_squad_stats_url_format():
    url = fr._squad_stats_url("9", "Premier-League", "2025-2026")
    assert url == "https://fbref.com/en/comps/9/2025-2026/2025-2026-Stats-Premier-League-Stats"


def test_parse_squad_table_minimal():
    html = """
    <html><body>
    <table id="stats_squads_standard_for">
      <tbody>
        <tr><th data-stat="squad">Arsenal</th><td data-stat="gls">50</td></tr>
        <tr><th data-stat="squad">Chelsea</th><td data-stat="gls">40</td></tr>
      </tbody>
    </table>
    </body></html>
    """
    rows = fr._parse_squad_table(html)
    assert len(rows) == 2
    assert rows[0]["squad"] == "Arsenal"


def test_fetch_fbref_html_403_raises_blocked():
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    with patch("hibs_predictor.scrapers.fbref_client._http_get", return_value=mock_resp):
        with pytest.raises(fr.FbrefFetchError) as excinfo:
            fr.fetch_fbref_html("https://fbref.com/en/comps/9/")
    assert excinfo.value.blocked is True
    assert excinfo.value.http_status == 403


def test_fetch_fbref_html_uses_cache():
    cache = MagicMock()
    cache.get.return_value = "<html>cached</html>"
    out = fr.fetch_fbref_html("https://fbref.com/x", cache_key="k", cache=cache)
    assert out == "<html>cached</html>"


def test_fbref_blocked_env_skips_fetch(monkeypatch):
    monkeypatch.setenv("HIBS_FBREF_BLOCKED", "1")
    with pytest.raises(fr.FbrefFetchError) as excinfo:
        fr.fetch_fbref_html("https://fbref.com/x")
    assert excinfo.value.blocked is True


def test_probe_squad_table_blocked_env(monkeypatch):
    monkeypatch.setenv("HIBS_FBREF_BLOCKED", "1")
    pr = fr.probe_squad_table("EPL")
    assert pr["ok"] is False
    assert pr["blocked"] is True
    assert pr.get("skipped_env") is True
    assert "curl_cffi" in pr
    assert "Understat" in (pr.get("error") or "")


def test_probe_squad_table_http_403():
    err = fr.FbrefFetchError("HTTP 403", blocked=True, http_status=403)
    with patch("hibs_predictor.scrapers.fbref_client.fetch_squad_stats_table", side_effect=err):
        pr = fr.probe_squad_table("EPL")
    assert pr["ok"] is False
    assert pr["blocked"] is True
    assert pr["http_status"] == 403


def test_fetch_squad_tries_season_fallback():
    html = """
    <table id="stats_squads_standard_for"><tbody>
    <tr><th data-stat="squad">A</th></tr><tr><th data-stat="squad">B</th></tr>
    <tr><th data-stat="squad">C</th></tr><tr><th data-stat="squad">D</th></tr>
    <tr><th data-stat="squad">E</th></tr>
    </tbody></table>
    """
    calls = []

    def fake_fetch(url, **kwargs):
        calls.append(url)
        if "2024-2025" in url:
            raise requests.HTTPError("404")
        return html

    with patch("hibs_predictor.scrapers.fbref_client._season_labels", return_value=["2024-2025", "2025-2026"]):
        with patch("hibs_predictor.scrapers.fbref_client.fetch_fbref_html", side_effect=fake_fetch):
            rows = fr.fetch_squad_stats_table("EPL")
    assert len(rows) == 5
    assert len(calls) == 2
