"""Heritage badge registry for UI."""

from hibs_predictor.hibs_brand import (
    HIBS_BADGE_PRIMARY,
    HIBS_HERITAGE_BADGES,
    HIBS_WATERMARK_BADGES,
    hibs_brand_context,
)


def test_heritage_badge_files():
    files = {b["file"] for b in HIBS_HERITAGE_BADGES}
    assert HIBS_BADGE_PRIMARY == "badge_2000_present.png"
    assert len(files) == 5
    assert HIBS_WATERMARK_BADGES == [b["file"] for b in HIBS_HERITAGE_BADGES]


def test_brand_context_keys():
    ctx = hibs_brand_context()
    assert ctx["hibs_badge_primary"] == HIBS_BADGE_PRIMARY
    assert len(ctx["hibs_heritage_badges"]) == 5
