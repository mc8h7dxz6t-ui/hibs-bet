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
    leagues = doc.get("per_league_notes") or []
    codes = " ".join(r["code"] for r in leagues)
    assert "UECL" in codes
