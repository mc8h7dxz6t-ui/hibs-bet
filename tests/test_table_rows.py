"""Table row normalization, dedupe, and team name rendering."""

from __future__ import annotations

from hibs_predictor.betting_engine import TeamStrengthCalculator
from hibs_predictor.web import (
    _attach_table_snapshots,
    _build_league_tables,
    _dedupe_table_rows,
    _normalize_table_row,
    _table_row_from_api_entry,
    _table_row_from_fdo_entry,
)


def test_table_row_from_api_entry_uses_team_name_not_dict():
    entry = {
        "rank": 17,
        "team": {"id": 47, "name": "Tottenham", "logo": ""},
        "points": 38,
        "goalsDiff": 5,
        "form": "WWDLW",
        "all": {
            "played": 20,
            "win": 11,
            "draw": 5,
            "lose": 4,
            "goals": {"for": 35, "against": 30},
        },
    }
    row = _table_row_from_api_entry(entry)
    assert row is not None
    assert row["team"] == "Tottenham"
    assert row["team_id"] == 47
    assert row["position"] == 17
    assert row["points"] == 38


def test_table_row_from_fdo_entry_uses_team_name():
    entry = {
        "position": 4,
        "team": {"id": 903, "name": "Hibernian FC", "crest": ""},
        "playedGames": 30,
        "won": 14,
        "draw": 8,
        "lost": 8,
        "goalsFor": 44,
        "goalsAgainst": 33,
        "goalDifference": 11,
        "points": 50,
        "form": "WDWLW",
    }
    row = _table_row_from_fdo_entry(entry)
    assert row is not None
    assert row["team"] == "Hibernian FC"
    assert row["team_id"] == 903
    assert row["position"] == 4


def test_dedupe_table_rows_by_team_id():
    rows = [
        {"position": 1, "team": "HJK", "team_id": 100, "points": 20, "source": "api_sports"},
        {"position": 1, "team": {"id": 100, "name": "HJK Helsinki"}, "points": 20, "source": "fixture"},
        {"position": 2, "team": "KuPS", "team_id": 101, "points": 18, "source": "api_sports"},
        {"position": 2, "team": "KuPS", "team_id": 101, "points": 18, "source": "fixture"},
    ]
    out = _dedupe_table_rows(rows)
    assert len(out) == 2
    names = {r["team"] for r in out}
    assert "HJK" in names
    assert "KuPS" in names
    assert all(isinstance(r["team"], str) for r in out)


def test_normalize_table_row_coerces_nested_position_team():
    raw = {
        "position": {"id": 47, "name": "Tottenham"},
        "team": {"id": 47, "name": "Tottenham"},
        "points": 38,
    }
    row = _normalize_table_row(raw)
    assert row.get("position") is None or isinstance(row["position"], int)
    assert row["team"] == "Tottenham"


def test_attach_table_snapshots_hibs_alias():
    fixtures = [
        {
            "home": "Hibs",
            "away": "Hearts",
            "league": "SCOTLAND",
            "home_position": {"position": 3, "points": 50, "played": 30},
            "away_position": {"position": 4, "points": 44, "played": 30},
        }
    ]
    tables = [
        {
            "code": "SCOTLAND",
            "name": "Scottish Premiership",
            "rows": [
                {
                    "position": 3,
                    "team": "Hibernian",
                    "played": 30,
                    "points": 50,
                    "goals_for": 44,
                    "goals_against": 33,
                    "goal_diff": 11,
                    "source": "api_sports",
                },
                {
                    "position": 4,
                    "team": "Hearts",
                    "played": 30,
                    "points": 44,
                    "goals_for": 40,
                    "goals_against": 38,
                    "goal_diff": 2,
                    "source": "api_sports",
                },
            ],
        }
    ]
    _attach_table_snapshots(fixtures, tables)
    fx = fixtures[0]
    assert fx["home_table_snapshot"]
    focus = [r for r in fx["home_table_snapshot"] if r.get("is_focus")]
    assert focus and focus[0]["team"] == "Hibernian"
    assert any(r.get("is_home_team") for r in fx["league_table_rows"])


def test_build_league_tables_dedupes_fixture_and_api_rows():
    fixtures = [
        {
            "home": "Team A",
            "away": "Team B",
            "league": "FINLAND_VEIKKAUSLIIGA",
            "home_position": {"position": 1, "points": 10, "played": 5, "goals_for": 8, "goals_against": 2},
            "away_position": {"position": 2, "points": 8, "played": 5, "goals_for": 6, "goals_against": 4},
        }
    ]
    full = [
        {"position": 1, "team": "Team A", "team_id": 1, "points": 10, "played": 5, "source": "api_sports"},
        {"position": 2, "team": "Team B", "team_id": 2, "points": 8, "played": 5, "source": "api_sports"},
    ]
    from unittest.mock import patch

    with patch("hibs_predictor.web._fetch_full_table_rows", return_value=full):
        tables = _build_league_tables(fixtures, include_live=False)
    fin = next(t for t in tables if t["code"] == "FINLAND_VEIKKAUSLIIGA")
    assert len(fin["rows"]) == 2


def test_parse_last_10_falls_back_to_team_name_when_id_mismatch():
    matches = [
        {
            "fixture": {"date": "2026-05-01T12:00:00+00:00", "status": {"short": "FT"}},
            "teams": {
                "home": {"id": 999, "name": "Away Side FC"},
                "away": {"id": 888, "name": "Home Side FC"},
            },
            "goals": {"home": 0, "away": 2},
        }
    ]
    rows = TeamStrengthCalculator.parse_last_10_results(matches, team_id=None, team_name="Home Side FC")
    assert len(rows) == 1
    assert rows[0]["result"] == "W"
    assert rows[0]["score"] == "2-0"
