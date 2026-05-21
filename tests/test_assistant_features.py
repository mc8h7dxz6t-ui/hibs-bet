"""Assistant data badges, context, and acca review API."""

from __future__ import annotations

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def test_dq_badge_template_thresholds():
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(str(_ROOT / "templates")))
    tpl = env.get_template("_dq_badge.html")
    for pct, cls in ((92, "ok"), (85, "mid"), (65, "low")):
        html = tpl.module.dq_badge(
            {"data_quality": {"score_pct": pct}},
            None,
            compact=True,
        )
        assert f"fr-dq-compact {cls}" in html
        assert f">{pct}%" in html


def test_assistant_context_includes_dq():
    from hibs_predictor.assistant_context import build_fixture_context_lines
    from hibs_predictor.assistant_chat import handle_chat

    pkt = {
        "id": 99,
        "home": "Hibs",
        "away": "Hearts",
        "data_quality_pct": 87.0,
        "xg_source": "understat",
        "home_recent_n": 8,
        "away_recent_n": 8,
        "structured_insight": {
            "mode": "prediction",
            "match": "Hibs vs Hearts",
            "pick": "Over 2.5",
            "confidence_pct": 61.0,
            "rationale": ["Goals lean high."],
        },
        "probability_scores": {
            "home_win_pct": 42,
            "draw_pct": 28,
            "away_win_pct": 30,
            "xg_home": 1.5,
            "xg_away": 1.2,
            "over25_pct": 61,
        },
        "pick_menu": [{"key": "over_25", "label": "Over 2.5", "model_pct": 61.0, "odds": 1.9}],
        "home_form_summary": {"played": 5, "wins": 3, "draws": 1, "losses": 1, "gf": 8, "ga": 5, "btts": 3, "over25": 3},
        "away_form_summary": {"played": 5, "wins": 2, "draws": 1, "losses": 2, "gf": 6, "ga": 6, "btts": 4, "over25": 2},
    }
    lines = build_fixture_context_lines(pkt)
    joined = " ".join(lines)
    assert "87" in joined and "Data coverage" in joined
    assert "Data coverage" in joined
    assert "understat" in joined.lower() or "xG" in joined

    reply = handle_chat("stats for Hibs v Hearts", [pkt])
    stats_blocks = [b for b in reply["blocks"] if b.get("type") == "stats"]
    assert stats_blocks
    assert "87" in " ".join(stats_blocks[0].get("lines", []))


def test_acca_review_endpoint_returns_legs_array(monkeypatch):
    import sys

    if str(_ROOT / "src") not in sys.path:
        sys.path.insert(0, str(_ROOT / "src"))
    from hibs_predictor.web import app

    fake_packets = [
        {
            "id": 1,
            "home": "Arsenal",
            "away": "Burnley",
            "data_quality_pct": 88.0,
            "xg_source": "api",
            "home_recent_n": 8,
            "away_recent_n": 8,
            "structured_insight": {"mode": "prediction", "pick": "Home Win", "confidence_pct": 55},
            "probability_scores": {"home_win_pct": 62, "draw_pct": 22, "away_win_pct": 16, "xg_home": 1.8, "xg_away": 0.9},
            "pick_menu": [
                {"key": "home_win", "label": "Home Win", "model_pct": 62.0, "odds": 1.45},
            ],
            "home_form_summary": {"played": 5, "wins": 4, "draws": 0, "losses": 1, "gf": 10, "ga": 3, "btts": 2, "over25": 3},
            "away_form_summary": {"played": 5, "wins": 1, "draws": 1, "losses": 3, "gf": 4, "ga": 9, "btts": 2, "over25": 2},
        }
    ]

    def _fake_fetch():
        return {"all": []}

    monkeypatch.setattr("hibs_predictor.web.fetch_all_fixtures", _fake_fetch)
    monkeypatch.setattr(
        "hibs_predictor.web._assistant_packets_from_fixtures",
        lambda _fixtures: fake_packets,
    )

    client = app.test_client()
    resp = client.post(
        "/api/assistant/acca-review",
        json={
            "legs": [
                {
                    "fixture_id": 1,
                    "home": "Arsenal",
                    "away": "Burnley",
                    "market_key": "home",
                    "market_label": "Home Win",
                    "odds": 1.45,
                }
            ]
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data.get("legs"), list)
    assert len(data["legs"]) == 1
    leg = data["legs"][0]
    assert leg.get("paragraph")
    assert leg.get("data_quality_pct") == 88.0
    assert "model_pct" in leg or leg.get("implied_pct") is not None


def _sample_packets_multi():
    base = {
        "kickoff_time": "15:00",
        "data_quality_pct": 88.0,
        "home_recent_n": 8,
        "away_recent_n": 8,
        "structured_insight": {"mode": "prediction", "pick": "BTTS Yes", "confidence_pct": 60},
        "probability_scores": {
            "home_win_pct": 45,
            "draw_pct": 28,
            "away_win_pct": 27,
            "btts_pct": 62,
            "over25_pct": 58,
        },
        "home_form_summary": {"played": 5, "wins": 3, "draws": 1, "losses": 1, "gf": 8, "ga": 5, "btts": 3, "over25": 3},
        "away_form_summary": {"played": 5, "wins": 2, "draws": 1, "losses": 2, "gf": 6, "ga": 6, "btts": 4, "over25": 2},
    }
    return [
        {
            **base,
            "id": 1,
            "home": "Arsenal",
            "away": "Burnley",
            "pick_menu": [
                {"key": "btts_yes", "label": "BTTS Yes", "model_pct": 62.0, "odds": 1.72, "is_value": True, "edge_pct": 4.0},
                {"key": "over_25", "label": "Over 2.5", "model_pct": 58.0, "odds": 1.85},
            ],
        },
        {
            **base,
            "id": 2,
            "home": "Celtic",
            "away": "Rangers",
            "pick_menu": [
                {"key": "home_win", "label": "Home Win", "model_pct": 55.0, "odds": 2.05},
                {"key": "btts_yes", "label": "BTTS Yes", "model_pct": 60.0, "odds": 1.65},
            ],
        },
        {
            **base,
            "id": 3,
            "home": "Liverpool",
            "away": "Fulham",
            "pick_menu": [
                {"key": "over_25", "label": "Over 2.5", "model_pct": 64.0, "odds": 1.7},
                {"key": "over_15", "label": "Over 1.5", "model_pct": 80.0, "odds": 1.22},
            ],
        },
    ]


def test_best_acca_includes_slip_payload_on_legs():
    from hibs_predictor.assistant_chat import handle_chat
    from hibs_predictor.assistant_recommendations import build_assistant_recommendations

    packets = _sample_packets_multi()
    rec = build_assistant_recommendations(packets)
    reply = handle_chat("best acca", packets, recommendations=rec)
    assert reply["intent"] == "best_acca"
    acca_blocks = [b for b in reply["blocks"] if b.get("type") == "accas"]
    assert acca_blocks
    legs = acca_blocks[0]["items"][0]["legs"]
    assert legs
    slip = legs[0].get("slip") or legs[0]
    for key in ("fixture_id", "home", "away", "market_key", "market_label", "odds"):
        assert key in slip


def test_suggest_legs_intent_returns_candidates():
    from hibs_predictor.assistant_chat import handle_chat
    from hibs_predictor.assistant_context import build_acca_candidates

    packets = _sample_packets_multi()
    reply = handle_chat("suggest legs", packets)
    assert reply["intent"] == "suggest_legs"
    leg_blocks = [b for b in reply["blocks"] if b.get("type") == "suggest_legs"]
    assert leg_blocks and leg_blocks[0]["items"]
    assert build_acca_candidates(packets)


def test_assistant_add_to_slip_hook(monkeypatch):
    """JS exports HibsAssistant.addLegToSlip — verify leg payload shape for betslip."""
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "static" / "hibs_assistant.js").read_text(encoding="utf-8")
    assert "HibsBetslip.addSelection" in js
    assert "addLegToSlip" in js
    assert "data-leg" in js
    assert "HibsAssistant" in js


def test_acca_review_flags_thin_data(monkeypatch):
    from hibs_predictor.acca_review import review_acca_legs

    thin = {
        "id": 2,
        "home": "A",
        "away": "B",
        "data_quality_pct": 55.0,
        "home_recent_n": 0,
        "away_recent_n": 0,
        "structured_insight": {"mode": "odds_only", "pick": "Odds only"},
        "pick_menu": [],
    }
    out = review_acca_legs(
        [{"fixture_id": 2, "home": "A", "away": "B", "market_key": "home_win", "odds": 2.0}],
        [thin],
    )
    assert out["legs"][0]["thin_data"] is True
    assert "thin data" in out["legs"][0]["paragraph"].lower()
