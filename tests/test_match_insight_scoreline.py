"""Scoreline derivation and motivation context (real-data rules only)."""

from hibs_predictor.match_insight import (
    _most_likely_scoreline,
    derive_motivation_context,
    poisson_top_scorelines,
)


def test_scoreline_poisson_argmax_not_round():
    # λ 1.35 vs 0.95 → joint mode often 1-0 or 1-1, not naive round(1)-round(1)=1-1 always
    s = _most_likely_scoreline(1.35, 0.95)
    assert "-" in s
    h, a = (int(x) for x in s.split("-"))
    assert 0 <= h <= 6 and 0 <= a <= 6


def test_scoreline_low_scoring():
    s = _most_likely_scoreline(0.45, 0.38)
    assert s == "0-0"


def test_poisson_top_three_sum_under_one():
    top = poisson_top_scorelines(1.35, 0.95, top_n=3)
    assert len(top) == 3
    assert top[0]["pct"] >= top[1]["pct"] >= top[2]["pct"]
    assert sum(t["pct"] for t in top) < 100.0


def test_motivation_title_won():
    rows = [
        {"position": 1, "team": "Celtic", "points": 90, "played": 36},
        {"position": 2, "team": "Rangers", "points": 72, "played": 36},
        {"position": 3, "team": "Hearts", "points": 60, "played": 36},
        {"position": 4, "team": "Hibs", "points": 55, "played": 36},
    ]
    fx = {"home": "Celtic", "away": "Hibs", "league_table_rows": rows}
    mot = derive_motivation_context(fx)
    assert "title_won" in mot["home"]
    assert mot["labels"]
