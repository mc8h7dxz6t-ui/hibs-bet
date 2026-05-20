"""Official third-party media URLs (YouTube embeds only — no scraped streams)."""

# @SkySportsNews — rolling 24/7 news simulcast on YouTube (https://www.youtube.com/@SkySportsNews/live).
SKY_SPORTS_NEWS_YOUTUBE_CHANNEL_ID = "UCcw05gGzjLIs5dnxGkQHMvw"
SKY_SPORTS_NEWS_YOUTUBE_CHANNEL_URL = "https://www.youtube.com/@SkySportsNews"
SKY_SPORTS_NEWS_YOUTUBE_LIVE_PAGE_URL = "https://www.youtube.com/@SkySportsNews/live"
SKY_SPORTS_NEWS_YOUTUBE_PRESET_DISPLAY = "youtube.com/@SkySportsNews/live"

# Stable live broadcast video on the News channel (program title rotates; same stream URL).
# Verified via @SkySportsNews/live (isLiveNow). Sky may rotate this ID — update if embed goes offline.
SKY_SPORTS_NEWS_YOUTUBE_LIVE_VIDEO_ID = "a-E_HJ7p1qg"
SKY_SPORTS_NEWS_YOUTUBE_LIVE_VIDEO_URL = (
    f"https://www.youtube.com/watch?v={SKY_SPORTS_NEWS_YOUTUBE_LIVE_VIDEO_ID}"
)
SKY_SPORTS_NEWS_YOUTUBE_UPLOADS_PLAYLIST_ID = "UU" + SKY_SPORTS_NEWS_YOUTUBE_CHANNEL_ID[2:]

# @SkySportsFootball — match highlights and football clips (not the Sky Sports News wire).
SKY_SPORTS_FOOTBALL_YOUTUBE_CHANNEL_ID = "UCZ7wY7MRDSygp63HIEfdQZA"
SKY_SPORTS_FOOTBALL_YOUTUBE_CHANNEL_URL = "https://www.youtube.com/@SkySportsFootball"
SKY_SPORTS_FOOTBALL_YOUTUBE_PRESET_DISPLAY = "youtube.com/@SkySportsFootball"
SKY_SPORTS_FOOTBALL_YOUTUBE_UPLOADS_PLAYLIST_ID = "UU" + SKY_SPORTS_FOOTBALL_YOUTUBE_CHANNEL_ID[2:]

_NOCOOKIE_EMBED = "https://www.youtube-nocookie.com/embed"


def _youtube_video_embed(video_id: str) -> str:
    return f"{_NOCOOKIE_EMBED}/{video_id}"


def _youtube_live_embed(channel_id: str) -> str:
    return f"{_NOCOOKIE_EMBED}/live_stream?channel={channel_id}"


def _youtube_clips_embed(uploads_playlist_id: str) -> str:
    return f"{_NOCOOKIE_EMBED}/videoseries?list={uploads_playlist_id}"


# Primary: direct 24/7 live video (more reliable than live_stream?channel= when YT marks channel offline).
SKY_SPORTS_NEWS_YOUTUBE_LIVE_EMBED_URL = _youtube_video_embed(
    SKY_SPORTS_NEWS_YOUTUBE_LIVE_VIDEO_ID
)
SKY_SPORTS_NEWS_YOUTUBE_LIVE_CHANNEL_EMBED_URL = _youtube_live_embed(
    SKY_SPORTS_NEWS_YOUTUBE_CHANNEL_ID
)
SKY_SPORTS_NEWS_YOUTUBE_CLIPS_EMBED_URL = _youtube_clips_embed(
    SKY_SPORTS_NEWS_YOUTUBE_UPLOADS_PLAYLIST_ID
)
SKY_SPORTS_FOOTBALL_YOUTUBE_CLIPS_EMBED_URL = _youtube_clips_embed(
    SKY_SPORTS_FOOTBALL_YOUTUBE_UPLOADS_PLAYLIST_ID
)

# Legacy name used by dashboard: News 24/7 live embed.
SKY_SPORTS_NEWS_YOUTUBE_EMBED_URL = SKY_SPORTS_NEWS_YOUTUBE_LIVE_EMBED_URL
