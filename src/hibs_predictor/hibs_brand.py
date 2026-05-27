"""Hibernian FC heritage badge assets for UI (static files only — not data scrapers)."""

from __future__ import annotations

from typing import Any, Dict, List

# Primary header / favicon / launch
HIBS_BADGE_PRIMARY = "badge_2000_present.png"
HIBS_BADGE_HARP = "badge_harp_embroidered.png"

HIBS_HERITAGE_BADGES: List[Dict[str, Any]] = [
    {
        "file": "badge_2000_present.png",
        "label": "Hibernian FC (2000–present)",
        "era": "2000–present",
    },
    {
        "file": "badge_harp_embroidered.png",
        "label": "Harp shield (embroidered)",
        "era": "heritage",
    },
    {
        "file": "badge_1979_circle.png",
        "label": "Hibernian FC Edinburgh (1979)",
        "era": "1979",
    },
    {
        "file": "badge_1979_shield_green.png",
        "label": "Green shield crest (1979)",
        "era": "1979",
    },
    {
        "file": "badge_1989_2000_oval.png",
        "label": "Oval crest (1989–2000)",
        "era": "1989–2000",
    },
]

# Watermark layer order (body::after background-image)
HIBS_WATERMARK_BADGES: List[str] = [b["file"] for b in HIBS_HERITAGE_BADGES]


def hibs_brand_context() -> Dict[str, Any]:
    """Template context for crests across the app."""
    return {
        "hibs_badge_primary": HIBS_BADGE_PRIMARY,
        "hibs_badge_harp": HIBS_BADGE_HARP,
        "hibs_heritage_badges": HIBS_HERITAGE_BADGES,
        "hibs_watermark_badges": HIBS_WATERMARK_BADGES,
    }
