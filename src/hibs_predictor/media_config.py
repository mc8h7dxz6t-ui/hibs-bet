"""Official third-party media URLs (embed/link only — no scraped streams)."""

# Sky Sports News — free-to-air on UK TV; web player at skysports.com (not iframe-embeddable).
SKY_SPORTS_NEWS_WATCH_URL = "https://www.skysports.com/watch/sky-sports-news"

# Official @SkySportsFootball YouTube (https://www.youtube.com/@SkySportsFootball)
SKY_SPORTS_NEWS_YOUTUBE_CHANNEL_ID = "UCZ7wY7MRDSygp63HIEfdQZA"

# Channel uploads playlist (UC… → UU…). Works when the channel is not live; live_stream embed shows "unavailable" offline.
SKY_SPORTS_NEWS_YOUTUBE_UPLOADS_PLAYLIST_ID = "UU" + SKY_SPORTS_NEWS_YOUTUBE_CHANNEL_ID[2:]

# Primary dashboard embed: recent official clips (nocookie). Live 24/7 stream is on Sky’s site, not this iframe.
SKY_SPORTS_NEWS_YOUTUBE_EMBED_URL = (
    "https://www.youtube-nocookie.com/embed/videoseries"
    f"?list={SKY_SPORTS_NEWS_YOUTUBE_UPLOADS_PLAYLIST_ID}"
)
