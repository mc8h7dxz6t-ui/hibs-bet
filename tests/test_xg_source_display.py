from hibs_predictor.xg_source_display import (
    attach_xg_display_fields,
    compact_fixture_xg,
    xg_confidence_tier,
    xg_source_hint,
    xg_source_label,
)


def test_labels_and_tiers():
    assert "API match" in xg_source_label("api_fixture_xg")
    assert "statistics" in xg_source_label("api_statistics_xg").lower()
    assert xg_confidence_tier("api_fixture_xg") == "strong"
    assert xg_confidence_tier("api_statistics_xg") == "strong"
    assert xg_confidence_tier("fotmob_league_xg", meta={"home_n": 4, "away_n": 4}) == "usable"
    assert xg_confidence_tier("goals_proxy") == "proxy"
    assert "cautiously" in xg_source_hint("goals_proxy").lower()


def test_attach_display_fields():
    row = {"xg_source": "scraped_recent_xg", "home_recent_n": 6, "away_recent_n": 5}
    attach_xg_display_fields(row)
    assert row["xg_source_label"]
    assert row["xg_confidence_tier"] == "strong"
    assert row["xg_source_hint"]


def test_compact_fixture_xg_from_team_stats():
    fixture = {
        "home_stats": {"played": 10, "goals_for": 15, "goals_against": 12},
        "away_stats": {"played": 10, "goals_for": 14, "goals_against": 11},
    }
    xh, xa = compact_fixture_xg(fixture)
    assert xh is not None and xa is not None
    assert xh > 0 and xa > 0


def test_compact_fixture_xg_prefers_fixture_fields():
    fixture = {"xg_home": 1.8, "xg_away": 0.9, "home_stats": {"played": 10, "goals_for": 15, "goals_against": 12}}
    xh, xa = compact_fixture_xg(fixture)
    assert xh == 1.8 and xa == 0.9


def test_api_season_hint_includes_per_match():
    hint = xg_source_hint(
        "api_season_team_xg",
        meta={"home_xg_per_match": 1.5, "away_xg_per_match": 1.2, "api_season_xg_measured": True},
    )
    assert "Season xG/match" in hint
    assert "1.5" in hint
