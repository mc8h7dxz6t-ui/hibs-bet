"""Tests for SoccerStats standings scraper."""

from hibs_predictor.scrapers import soccerstats_standings as ss


SCOTLAND_TABLE_HTML = """
<html><body><table>
<tr><td colspan="20">Championship group Team GP W D L GF GA GD Pts 1 Celtic 38 26 4 8 73 41 32 82</td></tr>
<tr><td></td><td>Team</td><td>GP</td><td>W</td><td>D</td><td>L</td><td>GF</td><td>GA</td><td>GD</td><td>Pts</td></tr>
<tr><td>1</td><td>Celtic</td><td>38</td><td>26</td><td>4</td><td>8</td><td>73</td><td>41</td><td>32</td><td>82</td></tr>
<tr><td>2</td><td>Hearts</td><td>38</td><td>24</td><td>8</td><td>6</td><td>67</td><td>34</td><td>33</td><td>80</td></tr>
<tr><td>3</td><td>Hibernian</td><td>38</td><td>15</td><td>12</td><td>11</td><td>58</td><td>44</td><td>14</td><td>57</td></tr>
</table></body></html>
"""


def test_parse_latest_html_scotland():
    rows = ss.parse_latest_html(SCOTLAND_TABLE_HTML)
    assert len(rows) == 3
    assert rows[0]["team"] == "Celtic"
    assert rows[0]["position"] == 1
    assert rows[0]["points"] == 82
    assert rows[2]["team"] == "Hibernian"


def test_find_team_row_hibernian():
    rows = ss.parse_latest_html(SCOTLAND_TABLE_HTML)
    row = ss.find_team_row(rows, "Hibernian FC")
    assert row is not None
    assert row["position"] == 3
    assert row["points"] == 57


def test_league_param_scotland_slug():
    assert ss.LEAGUE_PARAM["SCOTLAND"] == "scotland"
    assert ss.LEAGUE_PARAM["SCOTLAND_CHAMP"] == "scotland2"
