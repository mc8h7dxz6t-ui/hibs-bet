"""League fixture row dropdown must expose last-10 form for home and away."""

from __future__ import annotations

import os
import re
from pathlib import Path

from flask import Flask, render_template_string

from hibs_predictor.fixture_utils import position_rank, table_team_display

_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "_fixture_row_compact.html"


def _league_snap_snippet() -> str:
    text = _TEMPLATE.read_text(encoding="utf-8")
    start = text.index('<select class="fr-league-snap"')
    end = text.index("</select>", start) + len("</select>")
    return text[start:end]


def _render_league_snap(fixture: dict) -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app = Flask(__name__, template_folder=os.path.join(root, "templates"), root_path=root)
    app.add_template_filter(lambda v: table_team_display(v) or "—", "table_team_label")
    app.add_template_filter(
        lambda value: (
            str(position_rank(value))
            if isinstance(value, dict) and position_rank(value) is not None
            else str(value or "")
        ),
        "position_rank",
    )
    template = (
        "{% set hl10 = fixture.home_last10 %}{% set al10 = fixture.away_last10 %}"
        + _league_snap_snippet()
    )
    with app.app_context():
        return render_template_string(template, fixture=fixture)


def test_league_snap_last10_outside_cup_only_branch():
    """Regression: last-10 optgroups must not live only under is_cup_competition."""
    text = _league_snap_snippet()
    cup_branch = re.search(
        r"{% if fixture\.is_cup_competition %}.*?{% else %}",
        text,
        flags=re.DOTALL,
    )
    assert cup_branch is not None
    assert "— last 10" not in cup_branch.group(0)
    assert text.index("— last 10") > text.index("{% endif %}", text.index("{% else %}"))


def test_league_dropdown_includes_both_last10_optgroups():
    html = _render_league_snap(
        {
            "home": "Fiorentina",
            "away": "Atalanta",
            "league": "SERIE_A",
            "is_cup_competition": False,
            "league_table_rows": [
                {
                    "position": 4,
                    "team": "Fiorentina",
                    "played": 30,
                    "goals_for": 50,
                    "goals_against": 40,
                    "goal_diff": 10,
                    "points": 55,
                    "form": "WDWLW",
                    "is_home_team": True,
                    "is_away_team": False,
                    "is_focus": True,
                },
            ],
            "home_last10": [
                {
                    "result": "W",
                    "score": "2-0",
                    "opponent": "Roma",
                    "home_away": "H",
                    "date": "2026-05-01",
                }
            ],
            "away_last10": [
                {
                    "result": "L",
                    "score": "0-1",
                    "opponent": "Lazio",
                    "home_away": "A",
                    "date": "2026-05-02",
                }
            ],
        }
    )
    assert 'label="Fiorentina — last 10"' in html
    assert 'label="Atalanta — last 10"' in html
    assert "W 2-0 vs Roma" in html
    assert "L 0-1 vs Lazio" in html
