"""Portfolio Kelly: sqrt(N) stake split within kickoff windows + window stake cap."""

from __future__ import annotations

from hibs_predictor.betting_engine import apply_portfolio_kelly


def _fx(fid: int, kickoff: str, value_bets: dict) -> dict:
    return {
        "id": fid,
        "kickoff_sort": kickoff,
        "prediction": {"value_bets": value_bets, "value_bets_alt": {}},
    }


def _vb(suggested_percent: float) -> dict:
    return {
        "odds": 2.1,
        "kelly": {
            "suggested_percent": suggested_percent,
            "confidence_label": "Strong",
            "explanation": "test",
            "example_stake": "£4.00",
        },
    }


def test_portfolio_kelly_divides_by_sqrt_n_same_window(monkeypatch):
    monkeypatch.setenv("HIBS_PORTFOLIO_STAKE_CAP_PCT", "20")
    fixtures = [
        _fx(1, "2026-06-01T15:00:00+00:00", {"home": _vb(8.0)}),
        _fx(2, "2026-06-01T15:30:00+00:00", {"away": _vb(8.0)}),
    ]
    apply_portfolio_kelly(fixtures)
    h = fixtures[0]["prediction"]["value_bets"]["home"]["kelly"]
    a = fixtures[1]["prediction"]["value_bets"]["away"]["kelly"]
    assert h["portfolio_kelly_original_pct"] == 8.0
    assert a["portfolio_kelly_original_pct"] == 8.0
    # N=2 → each 8 / sqrt(2) ≈ 5.7
    assert h["suggested_percent"] == round(8.0 / (2**0.5), 1)
    assert a["suggested_percent"] == h["suggested_percent"]
    assert h["portfolio_window_n"] == 2


def test_portfolio_kelly_separate_windows_unscaled():
    fixtures = [
        _fx(1, "2026-06-01T15:00:00+00:00", {"home": _vb(6.0)}),
        _fx(2, "2026-06-01T17:00:00+00:00", {"away": _vb(6.0)}),
    ]
    apply_portfolio_kelly(fixtures)
    h = fixtures[0]["prediction"]["value_bets"]["home"]["kelly"]
    a = fixtures[1]["prediction"]["value_bets"]["away"]["kelly"]
    assert h["suggested_percent"] == 6.0
    assert a["suggested_percent"] == 6.0
    assert h["portfolio_window_n"] == 1
    assert a["portfolio_window_n"] == 1


def test_portfolio_kelly_same_fixture_joint_sqrt_legs():
    """Two legs on one match: stake / sqrt(2) before window clustering."""
    fixtures = [
        _fx(1, "2026-06-01T15:00:00+00:00", {"home": _vb(8.0), "btts_yes": _vb(6.0)}),
    ]
    apply_portfolio_kelly(fixtures)
    h = fixtures[0]["prediction"]["value_bets"]["home"]["kelly"]
    b = fixtures[0]["prediction"]["value_bets"]["btts_yes"]["kelly"]
    assert h["portfolio_match_legs"] == 2
    assert b["portfolio_match_legs"] == 2
    assert h["suggested_percent"] == round(8.0 / (2**0.5), 1)
    assert b["suggested_percent"] == round(6.0 / (2**0.5), 1)


def test_portfolio_kelly_caps_total_window_stake(monkeypatch):
    monkeypatch.setenv("HIBS_PORTFOLIO_STAKE_CAP_PCT", "10")
    fixtures = [
        _fx(1, "2026-06-01T15:00:00+00:00", {"home": _vb(8.0)}),
        _fx(2, "2026-06-01T15:20:00+00:00", {"draw": _vb(8.0)}),
        _fx(3, "2026-06-01T15:40:00+00:00", {"away": _vb(8.0)}),
    ]
    apply_portfolio_kelly(fixtures)
    total = sum(
        fixtures[i]["prediction"]["value_bets"][k]["kelly"]["suggested_percent"]
        for i, k in enumerate(["home", "draw", "away"])
    )
    assert total <= 10.05
    assert fixtures[0]["prediction"]["value_bets"]["home"]["kelly"]["portfolio_cap_scaled"] is True
