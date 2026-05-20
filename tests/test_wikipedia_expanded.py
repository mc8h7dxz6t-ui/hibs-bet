"""Wikipedia standings coverage for expanded leagues."""

from hibs_predictor.scrapers import wikipedia_standings as wp


def test_wp_suffix_includes_nordic():
    assert "NORWAY_ELITESERIEN" in wp.WP_SUFFIX
    assert "FINLAND_VEIKKAUSLIIGA" in wp.WP_SUFFIX


def test_article_title_norway():
    title = wp._article_title("NORWAY_ELITESERIEN")
    assert title is not None
    assert "Eliteserien" in title
