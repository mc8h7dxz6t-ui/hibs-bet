"""Thin-data scrape rescue when API enrichment is sparse."""

from hibs_predictor.scrapers import fotmob_client as fm
from hibs_predictor.scrapers.thin_data_rescue import (
    apply_thin_data_rescue,
    enriched_needs_thin_rescue,
    recompute_recent_derived,
)


def test_fotmob_match_to_recent_format_finished():
    m = {
        "id": 9,
        "home": {"id": 1, "name": "France", "score": 2},
        "away": {"id": 2, "name": "Germany", "score": 1},
        "status": {"reason": {"short": "FT"}, "utcTime": "2026-05-20T19:00:00.000Z"},
    }
    row = fm.fotmob_match_to_recent_format(m)
    assert row
    assert row["goals"] == {"home": 2, "away": 1}
    assert row["_source"] == "fotmob_calendar"


def test_parse_league_standings_table():
    payload = {
        "table": [
            {
                "data": {
                    "table": {
                        "all": [
                            {
                                "name": "Arsenal",
                                "played": 38,
                                "pts": 89,
                                "goals": 88,
                                "goalsConceded": 28,
                                "idx": 1,
                            }
                        ]
                    }
                }
            }
        ]
    }
    rows = fm.parse_league_standings_table(payload)
    assert len(rows) == 1
    stats = fm.row_to_season_stats(rows[0])
    assert stats["goals_for"] == 88
    assert stats["position"] == 1


def test_enriched_needs_thin_rescue_when_no_recent():
    enriched = {"home_recent": [], "away_recent": [], "home_stats": {}, "away_stats": {}}
    assert enriched_needs_thin_rescue(enriched, 1, 2) is True


def test_apply_thin_data_rescue_fills_recent(monkeypatch):
    fixture = {
        "home": {"id": 1, "name": "France"},
        "away": {"id": 2, "name": "Germany"},
        "league": "INTL_FRIENDLIES",
    }
    enriched = {
        "home": fixture["home"],
        "away": fixture["away"],
        "home_recent": [],
        "away_recent": [],
        "home_stats": {},
        "away_stats": {},
        "league": "INTL_FRIENDLIES",
    }
    recent = [
        {
            "fixture": {"date": "2026-05-01", "status": {"short": "FT"}},
            "teams": {
                "home": {"id": 1, "name": "France"},
                "away": {"id": 3, "name": "Italy"},
            },
            "goals": {"home": 2, "away": 0},
        }
    ]

    monkeypatch.setenv("HIBS_THIN_DATA_SCRAPE", "1")
    monkeypatch.setattr(
        fm,
        "team_recent_from_fotmob_calendar",
        lambda lc, name, **kw: recent if name == "France" else [],
    )
    monkeypatch.setattr(fm, "team_season_stats_from_fotmob_league", lambda *a, **k: {})

    out = apply_thin_data_rescue(
        enriched,
        fixture,
        "INTL_FRIENDLIES",
        home_id=1,
        away_id=2,
    )
    assert len(out["home_recent"]) == 1
    assert out.get("thin_data_rescue", {}).get("home_recent_source") == "fotmob_calendar"


def test_recompute_recent_derived_by_name():
    enriched = {
        "home_recent": [
            {
                "fixture": {"date": "2026-05-01", "status": {"short": "FT"}},
                "teams": {
                    "home": {"id": 99, "name": "France"},
                    "away": {"id": 88, "name": "Italy"},
                },
                "goals": {"home": 2, "away": 1},
            }
        ],
        "away_recent": [],
    }
    recompute_recent_derived(
        enriched,
        home_id=0,
        away_id=0,
        home_name="France",
        away_name="Germany",
    )
    assert enriched["home_recent_n"] >= 1
    assert enriched["home_form"] > 0.5
