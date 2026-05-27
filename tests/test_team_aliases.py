"""Team alias matching for odds and tables."""

from hibs_predictor.team_aliases import team_names_match


def test_loi_st_patricks_variants():
    assert team_names_match("St Patrick's Athletic", "St Patricks Athletic")
    assert team_names_match("St. Patrick's Athletic", "Saint Patricks Athletic")


def test_loi_bohemians():
    assert team_names_match("Bohemians", "Bohemian FC")
    assert team_names_match("Shamrock Rovers", "Shamrock Rovers FC")


def test_uk_aliases_preserved():
    assert team_names_match("Hibs", "Hibernian")
    assert team_names_match("Man Utd", "Manchester United")
