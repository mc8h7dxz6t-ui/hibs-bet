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


def _rich_assistant_packet(**overrides):
    base = {
        "id": 99,
        "home": "Hibs",
        "away": "Hearts",
        "kickoff_time": "15:00",
        "data_quality_pct": 87.0,
        "xg_source": "understat",
        "sources_summary": "xG: understat · Hibs table: api",
        "home_recent_n": 8,
        "away_recent_n": 8,
        "bet_confidence": 72.0,
        "bet_confidence_min_value": 45.0,
        "has_value_bet": True,
        "has_value_dual_agree": True,
        "is_live": False,
        "home_position": {"position": 3, "points": 58, "played": 30, "goal_diff": 12, "form": "WWDLW", "source": "api"},
        "away_position": {"position": 5, "points": 52, "played": 30, "goal_diff": 4, "form": "DLWWL", "source": "api"},
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
        "value_bets_display": [
            {
                "market_key": "over_25",
                "market_label": "Over 2.5",
                "edge_pct": 5.2,
                "value_dual_agree": True,
                "model_probability_pct": 61.0,
                "implied_probability_pct": 52.6,
                "odds": 1.9,
            }
        ],
        "home_form_summary": {"played": 5, "wins": 3, "draws": 1, "losses": 1, "gf": 8, "ga": 5, "btts": 3, "over25": 3},
        "away_form_summary": {"played": 5, "wins": 2, "draws": 1, "losses": 2, "gf": 6, "ga": 6, "btts": 4, "over25": 2},
    }
    base.update(overrides)
    return base


def test_assistant_context_includes_dq():
    from hibs_predictor.assistant_context import build_fixture_context_lines
    from hibs_predictor.assistant_chat import handle_chat

    pkt = _rich_assistant_packet()
    lines = build_fixture_context_lines(pkt)
    joined = " ".join(lines)
    assert "87" in joined and "Data coverage" in joined
    assert "understat" in joined.lower() or "xG" in joined
    assert "Bet confidence" in joined and "72" in joined
    assert "Table:" in joined and "**3**" in joined
    assert "dual finder" in joined.lower()
    assert "Hibs" in joined and "Form:" in joined

    reply = handle_chat("stats for Hibs v Hearts", [pkt])
    stats_blocks = [b for b in reply["blocks"] if b.get("type") == "stats"]
    assert stats_blocks
    assert "87" in " ".join(stats_blocks[0].get("lines", []))


def test_build_assistant_packet_includes_live_and_confidence():
    from hibs_predictor.assistant_context import enrich_assistant_packet
    from hibs_predictor.match_insight import build_assistant_packet

    row = {
        "id": 42,
        "home": "Arsenal",
        "away": "Chelsea",
        "kickoff_time": "17:30",
        "league": "EPL",
        "league_name": "Premier League",
        "xg_source": "stats_api_xg",
        "is_live": True,
        "live_score": "1-0",
        "live_status": "1H",
        "live_minute": 34,
        "live_xg_home": 0.9,
        "live_xg_away": 0.4,
        "home_last10": [{"result": "W", "score": "2-0", "gf": 2, "ga": 0}],
        "away_last10": [{"result": "L", "score": "0-1", "gf": 0, "ga": 1}],
        "home_position": {"position": 2, "points": 70, "source": "api"},
        "away_position": {"position": 4, "points": 65, "source": "api"},
        "data_quality": {"score_pct": 91.0},
        "has_value_bet": True,
        "prediction": {
            "structured_insight": {"mode": "prediction", "pick": "Home Win", "confidence_pct": 58},
            "probability_scores": {"home_win_pct": 55, "xg_home": 1.7, "xg_away": 1.1},
            "pick_menu": [{"key": "home_win", "label": "Home Win", "model_pct": 55, "odds": 1.8}],
            "value_bets_display": [{"market_key": "home_win", "value_dual_agree": True, "edge_pct": 4.0}],
            "bet_confidence": 68.0,
            "bet_confidence_min_value": 40.0,
        },
    }
    pkt = enrich_assistant_packet(build_assistant_packet(row))
    assert pkt["is_live"] is True
    assert pkt["live_score"] == "1-0"
    assert pkt["bet_confidence"] == 68.0
    assert pkt["has_value_dual_agree"] is True
    assert pkt["sources_summary"]
    assert "stats_api" in pkt["sources_summary"].lower() or "xG" in pkt["sources_summary"]


def test_fixtures_summary_caps_at_80():
    from hibs_predictor.assistant_context import build_fixtures_summary

    packets = [_rich_assistant_packet(id=i, home=f"H{i}", away=f"A{i}") for i in range(100)]
    summary = build_fixtures_summary(packets, max_n=80)
    assert len(summary) == 80
    row = summary[0]
    assert row["data_quality_pct"] == 87.0
    assert row["xg_home"] == 1.5
    assert row["has_value_dual_agree"] is True
    assert row["bet_confidence"] == 72.0
    assert row["sources_summary"]
    assert "L5:" in row["form_brief"] and "BTTS" in row["form_brief"]


def test_assistant_snapshot_bundle_has_fixtures_summary(monkeypatch):
    import sys

    if str(_ROOT / "src") not in sys.path:
        sys.path.insert(0, str(_ROOT / "src"))
    from hibs_predictor.web import app, _assistant_bundle

    fake_row = {
        "id": 7,
        "home": "Hibs",
        "away": "Hearts",
        "kickoff_time": "15:00",
        "league": "SCOTLAND",
        "league_name": "Scottish Prem",
        "xg_source": "understat",
        "data_quality": {"score_pct": 88.0},
        "home_last10": [{"result": "W", "score": "2-1", "gf": 2, "ga": 1}],
        "away_last10": [{"result": "D", "score": "1-1", "gf": 1, "ga": 1}],
        "home_position": {"position": 3, "points": 50, "source": "api"},
        "away_position": {"position": 6, "points": 44, "source": "api"},
        "has_value_bet": False,
        "prediction": {
            "structured_insight": {"mode": "prediction", "pick": "BTTS Yes", "confidence_pct": 60},
            "probability_scores": {"btts_pct": 62, "xg_home": 1.4, "xg_away": 1.3},
            "pick_menu": [{"key": "btts_yes", "label": "BTTS Yes", "model_pct": 62, "odds": 1.7}],
            "bet_confidence": 65.0,
            "bet_confidence_min_value": 40.0,
        },
    }
    bundle = _assistant_bundle([fake_row])
    assert len(bundle["fixtures_summary"]) == 1
    assert bundle["fixtures_summary"][0]["bet_confidence"] == 65.0
    assert bundle["packets"][0]["sources_summary"]

    monkeypatch.setattr("hibs_predictor.web.fetch_all_fixtures", lambda **kw: {"all": [fake_row]})
    client = app.test_client()
    resp = client.get("/api/assistant/snapshot")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "fixtures_summary" in data
    assert len(data["fixtures_summary"]) <= 80
    assert data["packets"][0]["bet_confidence"] == 65.0


def test_live_intent_lists_in_play_fixtures():
    from hibs_predictor.assistant_chat import handle_chat

    live_pkt = _rich_assistant_packet(
        id=1,
        home="Live FC",
        away="Away Utd",
        is_live=True,
        live_score="2-1",
        live_status="2H",
        live_minute=78,
    )
    reply = handle_chat("live games now", [live_pkt, _rich_assistant_packet(id=2, is_live=False)])
    assert reply["intent"] == "live"
    text = " ".join(
        line
        for b in reply["blocks"]
        if b.get("type") == "text"
        for line in (b.get("lines") or [])
    )
    assert "Live FC" in text or "in play" in text.lower()
    fixture_blocks = [b for b in reply["blocks"] if b.get("type") == "fixtures"]
    assert fixture_blocks and fixture_blocks[0]["items"][0]["is_live"]


def test_value_intent_mentions_dual_agree():
    from hibs_predictor.assistant_chat import handle_chat

    pkt = _rich_assistant_packet(has_value_bet=True)
    reply = handle_chat("value bets", [pkt])
    assert reply["intent"] == "value"
    intro = " ".join(
        line
        for b in reply["blocks"]
        if b.get("type") == "text"
        for line in (b.get("lines") or [])
    )
    assert "dual" in intro.lower()


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

    def _fake_fetch(**_kwargs):
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


def _full_sample_packet(**overrides):
    base = {
        "id": 42,
        "home": "Hibs",
        "away": "Hearts",
        "league_name": "Scottish Premiership",
        "competition_display": "Scottish Premiership · Matchday 12",
        "data_quality_pct": 87.0,
        "trust_label": "strong",
        "weak_fields": ["injuries"],
        "xg_source": "understat",
        "home_last10_wdl": "WDWLW",
        "away_last10_wdl": "LWDWD",
        "structured_insight": {
            "mode": "prediction",
            "pick": "Over 2.5",
            "confidence_pct": 61.0,
        },
        "probability_scores": {
            "home_win_pct": 42,
            "draw_pct": 28,
            "away_win_pct": 30,
            "btts_pct": 58,
            "over25_pct": 61,
            "xg_home": 1.5,
            "xg_away": 1.2,
        },
        "value_bets_display": [
            {
                "market_label": "Over 2.5",
                "edge_pct": 4.2,
                "value_dual_agree": True,
                "outcome": "over25",
            }
        ],
        "value_bets_alt": {"over25": {"roi_percent": 5.0}},
        "value_bets_rejected": {"draw": "bet_confidence_below_floor"},
        "line_odds": {"over25": 1.85, "btts_yes": 1.72},
        "best_odds_1x2": {"home": 2.1, "draw": 3.4, "away": 3.2},
        "sharp_anchor_implied": {"home": 0.48, "draw": 0.27, "away": 0.25},
        "bet_confidence": 82.0,
        "has_value_dual_agree": True,
        "supplemental_tags": ["understat", "wikipedia"],
        "calibration_shrink": {"shrink_factor": 0.92},
    }
    base.update(overrides)
    return base


def test_build_assistant_packet_includes_full_data_fields():
    from hibs_predictor.match_insight import build_assistant_packet

    row = {
        "id": 7,
        "home": "A",
        "away": "B",
        "league_name": "EPL",
        "competition_meta": {"api_round": "GW10"},
        "home_last10": [{"result": "W"}, {"result": "D"}],
        "away_last10": [{"result": "L"}],
        "xg_source": "fbref",
        "data_quality": {"score_pct": 90.0, "trust_label": "strong", "weak_fields": []},
        "best_odds_1x2": {"home": 2.0},
        "sharp_anchor_implied": {"home": 0.5},
        "supplemental": {"understat_light": True},
        "prediction": {
            "structured_insight": {"mode": "prediction", "pick": "Home Win"},
            "probability_scores": {"home_win_pct": 55, "xg_home": 1.4, "xg_away": 1.0},
            "value_bets": {"home": {"value_dual_agree": True}},
            "value_bets_alt": {},
            "value_bets_display": [],
            "line_odds": {"btts_yes": 1.7},
            "bet_confidence": 80,
            "historic_calibration": {"calibration_shrink": {"shrink_factor": 0.9}},
        },
    }
    pkt = build_assistant_packet(row)
    for key in (
        "home_last10_wdl",
        "away_last10_wdl",
        "value_bets",
        "line_odds",
        "sharp_anchor_implied",
        "bet_confidence",
        "trust_label",
        "supplemental_tags",
        "calibration_shrink",
        "competition_display",
    ):
        assert key in pkt, key


def test_snapshot_fixtures_summary_dq_xg_value_signals(monkeypatch):
    import sys

    if str(_ROOT / "src") not in sys.path:
        sys.path.insert(0, str(_ROOT / "src"))
    from hibs_predictor.web import app

    pkt = _full_sample_packet()

    monkeypatch.setattr(
        "hibs_predictor.web.fetch_all_fixtures",
        lambda *args, **kwargs: {"all": []},
    )
    monkeypatch.setattr(
        "hibs_predictor.web._assistant_packets_from_fixtures",
        lambda _fixtures: [pkt],
    )

    client = app.test_client()
    resp = client.get("/api/assistant/snapshot")
    assert resp.status_code == 200
    data = resp.get_json()
    summary = data.get("fixtures_summary") or []
    assert summary
    row = summary[0]
    assert row.get("data_quality_pct") == 87.0
    assert row.get("trust_label") == "strong"
    assert row.get("xg_source") == "understat"
    assert row.get("value_signals")
    assert row.get("sharp_anchor_pct")
    assert row.get("home_last10_wdl") == "WDWLW"


def test_assistant_context_trust_and_wdl():
    from hibs_predictor.assistant_context import build_fixture_context_lines

    pkt = _full_sample_packet()
    lines = build_fixture_context_lines(pkt)
    joined = " ".join(lines)
    assert "strong" in joined
    assert "WDWLW" in joined
    assert "understat" in joined.lower()
    assert "Best lines" in joined


def test_parse_intent_btts_10_fold():
    from hibs_predictor.assistant_chat import parse_intent

    intent, params = parse_intent("btts 10 fold")
    assert intent == "btts_acca"
    assert params["leg_count"] == 10
    assert params.get("ranked_only") is not True


def test_parse_intent_best_3_btts_ranked():
    from hibs_predictor.assistant_chat import parse_intent

    intent, params = parse_intent("best 3 btts")
    assert intent == "multi_leg_btts"
    assert params["leg_count"] == 3
    assert params.get("ranked_only") is True


def test_parse_intent_best_3_btts_win_detailed():
    from hibs_predictor.assistant_chat import parse_intent

    intent, params = parse_intent("best 3 btts win with detailed reasoning")
    assert intent == "win_btts_combo"
    assert params["leg_count"] == 3
    assert params.get("detailed") is True


def test_btts_10_fold_acca_with_disclaimer_when_short_card():
    from hibs_predictor.assistant_chat import handle_chat

    packets = _sample_packets_multi()
    reply = handle_chat("btts 10 fold", packets)
    assert reply["intent"] == "btts_acca"
    text = " ".join(
        line
        for b in reply["blocks"]
        if b.get("type") == "text"
        for line in (b.get("lines") or [])
    )
    assert "10" in text
    accas = [b for b in reply["blocks"] if b.get("type") == "accas"]
    if accas:
        acca = accas[0]["items"][0]
        assert acca["leg_count"] <= 10
        assert len(acca["legs"]) == acca["leg_count"]
        if acca.get("requested_count", 10) > acca.get("qualified_count", 0):
            assert "Only" in text or acca["qualified_count"] < 10
        for leg in acca["legs"]:
            assert leg.get("model_pct") is not None
            assert leg.get("odds") is not None
            assert leg.get("data_quality_pct") is not None


def test_best_3_btts_returns_ranked_legs_with_reasoning():
    from hibs_predictor.assistant_chat import handle_chat

    packets = _sample_packets_multi()
    reply = handle_chat("best 3 btts", packets)
    assert reply["intent"] == "multi_leg_btts"
    leg_blocks = [b for b in reply["blocks"] if b.get("type") == "suggest_legs"]
    assert leg_blocks
    items = leg_blocks[0]["items"]
    assert 1 <= len(items) <= 3
    for leg in items:
        assert leg.get("market_key") == "btts_yes"
        rat = leg.get("rationale")
        assert rat
        bullets = rat if isinstance(rat, list) else [rat]
        joined = " ".join(str(b) for b in bullets).lower()
        assert "model" in joined or "btts" in joined
        assert leg.get("data_quality_pct") is not None


def test_best_3_btts_win_detailed_reasoning():
    from hibs_predictor.assistant_chat import handle_chat

    base = {
        "kickoff_time": "15:00",
        "data_quality_pct": 88.0,
        "home_recent_n": 8,
        "away_recent_n": 8,
        "structured_insight": {"mode": "prediction", "pick": "Home Win & BTTS"},
        "probability_scores": {"home_win_pct": 55, "btts_pct": 62, "xg_home": 1.6, "xg_away": 1.1},
        "home_form_summary": {"played": 5, "wins": 3, "draws": 1, "losses": 1, "gf": 8, "ga": 5, "btts": 3, "over25": 3},
        "away_form_summary": {"played": 5, "wins": 2, "draws": 1, "losses": 2, "gf": 6, "ga": 6, "btts": 4, "over25": 2},
    }
    packets = [
        {
            **base,
            "id": 10,
            "home": "Celtic",
            "away": "Rangers",
            "pick_menu": [
                {"key": "home_and_btts", "label": "Home Win & BTTS", "model_pct": 24.0, "odds": 3.8},
                {"key": "btts_yes", "label": "BTTS Yes", "model_pct": 60.0, "odds": 1.65},
            ],
        },
        {
            **base,
            "id": 11,
            "home": "Arsenal",
            "away": "Burnley",
            "pick_menu": [
                {"key": "away_and_btts", "label": "Away Win & BTTS", "model_pct": 20.0, "odds": 4.2},
            ],
        },
    ]
    reply = handle_chat("best 3 btts win with detailed reasoning", packets)
    assert reply["intent"] == "win_btts_combo"
    intro = " ".join(
        line
        for b in reply["blocks"]
        if b.get("type") == "text"
        for line in (b.get("lines") or [])
    )
    assert "detailed" in intro.lower() or "snapshot" in intro.lower()
    items = [b for b in reply["blocks"] if b.get("type") == "suggest_legs"][0]["items"]
    assert items
    bullets = items[0].get("rationale") or []
    joined = " ".join(str(b) for b in (bullets if isinstance(bullets, list) else [bullets])).lower()
    assert "model" in joined
    assert "xg" in joined or "form" in joined or "table" in joined


def test_assistant_js_mentions_btts_fold_examples():
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "static" / "hibs_assistant.js").read_text(encoding="utf-8")
    assert "btts 10 fold" in js
    assert "rationaleListHtml" in js


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
