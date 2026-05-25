"""xG priority chain documentation for /status."""

from hibs_predictor.xg_priority_chain import xg_priority_chain_dict


def test_xg_priority_chain_has_steps():
    doc = xg_priority_chain_dict()
    assert doc.get("headline")
    steps = doc.get("steps") or []
    assert len(steps) >= 5
    tags = {s["source"] for s in steps}
    assert "api_fixture_xg" in tags
    assert "goals_proxy" in tags
    assert "scraped_recent_xg" in tags
    assert "api_season_team_xg" in tags
    ranks = [s["rank"] for s in steps]
    assert ranks.index("5") < ranks.index("9")
    leagues = doc.get("per_league_notes") or []
    codes = " ".join(r["code"] for r in leagues)
    assert "UECL" in codes
    assert "SCOTTISH_CUP" in codes or "SCOTLAND" in codes


def test_xg_priority_chain_notes_fbref_blocked(monkeypatch):
    monkeypatch.setenv("HIBS_FBREF_BLOCKED", "1")
    doc = xg_priority_chain_dict()
    assert doc.get("fbref_blocked") is True
    notes = " ".join(doc.get("ops_notes") or [])
    assert "FBREF_BLOCKED" in notes
