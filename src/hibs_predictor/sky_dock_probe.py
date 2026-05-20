"""Probe YouTube embed viability for the Sky Sports dock (cached, best-effort)."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

import requests

from hibs_predictor.cache import Cache
from hibs_predictor.media_config import (
    SKY_SPORTS_FOOTBALL_YOUTUBE_CHANNEL_URL,
    SKY_SPORTS_FOOTBALL_YOUTUBE_UPLOADS_PLAYLIST_ID,
    SKY_SPORTS_NEWS_YOUTUBE_LIVE_PAGE_URL,
    SKY_SPORTS_NEWS_YOUTUBE_LIVE_VIDEO_ID,
    _youtube_clips_embed,
    _youtube_video_embed,
)

_SKY_DOCK_PROBE_CACHE_KEY = "sky_dock_probe_v1"
_SKY_DOCK_PROBE_TTL_HOURS = 0.5  # 30 minutes
_YOUTUBE_OEMBED = "https://www.youtube.com/oembed"
_REQUEST_TIMEOUT = 18
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _USER_AGENT, "Accept-Language": "en-GB,en;q=0.9"}
_VIDEO_ID_RE = re.compile(r'"videoId":"([A-Za-z0-9_-]{11})"')


def _probe_disabled() -> bool:
    return (os.getenv("HIBS_SKY_DOCK_PROBE") or "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    )


def _youtube_oembed_ok(page_url: str) -> bool:
    try:
        r = requests.get(
            _YOUTUBE_OEMBED,
            params={"url": page_url, "format": "json"},
            headers=_HEADERS,
            timeout=_REQUEST_TIMEOUT,
        )
        if r.status_code != 200:
            return False
        data = r.json()
        return bool(data.get("html") or data.get("title"))
    except (requests.RequestException, json.JSONDecodeError, TypeError, ValueError):
        return False


def _watch_playable_in_embed(video_id: str) -> bool:
    try:
        r = requests.get(
            f"https://www.youtube.com/watch?v={video_id}",
            headers=_HEADERS,
            timeout=_REQUEST_TIMEOUT,
        )
        if r.status_code != 200:
            return False
        text = r.text
        if '"playableInEmbed":true' in text:
            return True
        if '"playableInEmbed":false' in text:
            return False
        # Offline / rotated ID: treat missing flag as not embeddable.
        return False
    except requests.RequestException:
        return False


def _discover_live_video_id_from_live_page(html: str) -> Optional[str]:
    """Best-effort live broadcast video id from @SkySportsNews/live HTML."""
    if not html:
        return None
    if '"isLiveNow":true' not in html and '"isLiveNow": true' not in html:
        return None
    for vid in _VIDEO_ID_RE.findall(html):
        if _watch_playable_in_embed(vid):
            return vid
    return None


def _resolve_live_video_id() -> str:
    configured = SKY_SPORTS_NEWS_YOUTUBE_LIVE_VIDEO_ID
    try:
        r = requests.get(
            SKY_SPORTS_NEWS_YOUTUBE_LIVE_PAGE_URL,
            headers=_HEADERS,
            timeout=_REQUEST_TIMEOUT,
        )
        if r.status_code == 200:
            discovered = _discover_live_video_id_from_live_page(r.text)
            if discovered:
                return discovered
    except requests.RequestException:
        pass
    return configured


def _probe_embed_sources() -> Dict[str, Any]:
    live_video_id = _resolve_live_video_id()
    news_watch_url = f"https://www.youtube.com/watch?v={live_video_id}"
    football_playlist_url = (
        f"https://www.youtube.com/playlist?list={SKY_SPORTS_FOOTBALL_YOUTUBE_UPLOADS_PLAYLIST_ID}"
    )

    news_oembed_ok = _youtube_oembed_ok(news_watch_url)
    news_embed_ok = news_oembed_ok and _watch_playable_in_embed(live_video_id)
    football_oembed_ok = _youtube_oembed_ok(football_playlist_url)

    available = bool(news_embed_ok and football_oembed_ok)
    reasons = []
    if not news_oembed_ok:
        reasons.append("news_oembed_failed")
    elif not news_embed_ok:
        reasons.append("news_not_embeddable")
    if not football_oembed_ok:
        reasons.append("football_playlist_oembed_failed")

    return {
        "available": available,
        "live_video_id": live_video_id,
        "news_embed_ok": news_embed_ok,
        "football_embed_ok": football_oembed_ok,
        "news_live_embed_url": _youtube_video_embed(live_video_id),
        "reason": ",".join(reasons) if reasons else "ok",
    }


def probe_sky_dock_embed(*, force_refresh: bool = False) -> Dict[str, Any]:
    """Return cached Sky dock embed probe (30 min TTL)."""
    if _probe_disabled():
        live_video_id = SKY_SPORTS_NEWS_YOUTUBE_LIVE_VIDEO_ID
        return {
            "available": True,
            "live_video_id": live_video_id,
            "news_embed_ok": True,
            "football_embed_ok": True,
            "news_live_embed_url": _youtube_video_embed(live_video_id),
            "reason": "probe_disabled",
            "cached": False,
        }

    cache = Cache()
    if not force_refresh:
        cached = cache.get(_SKY_DOCK_PROBE_CACHE_KEY, ttl_hours=_SKY_DOCK_PROBE_TTL_HOURS)
        if isinstance(cached, dict) and "available" in cached:
            cached["cached"] = True
            return cached

    result = _probe_embed_sources()
    result["cached"] = False
    cache.set(_SKY_DOCK_PROBE_CACHE_KEY, result, ttl_hours=_SKY_DOCK_PROBE_TTL_HOURS)
    return result


def sky_dock_available() -> bool:
    return bool(probe_sky_dock_embed().get("available"))


def sky_dock_news_live_embed_url() -> str:
    probe = probe_sky_dock_embed()
    url = probe.get("news_live_embed_url")
    if isinstance(url, str) and url.startswith("https://"):
        return url
    return _youtube_video_embed(SKY_SPORTS_NEWS_YOUTUBE_LIVE_VIDEO_ID)


def sky_dock_football_clips_embed_url() -> str:
    return _youtube_clips_embed(SKY_SPORTS_FOOTBALL_YOUTUBE_UPLOADS_PLAYLIST_ID)
