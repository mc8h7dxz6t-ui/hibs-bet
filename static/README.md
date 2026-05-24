# Static assets

## Badge assets

Use `badge_harp_shield.png` for all user-facing crest/badge UI (headers, favicon, launch overlay, watermarks). `hibs_badge.svg` is deprecated and must not be used — it is not an official Hibernian crest.

## Optional launch video (`launch-wait.mp4`)

The dashboard can show a full-screen loading overlay while fixtures and enrichment load. By default it uses CSS-only branding (Hibs crest + rotating tips).

To enable an optional **muted** background loop:

1. Set `HIBS_LAUNCH_MEDIA=1` in `.env` (see `.env.example`).
2. Place your own file at `static/launch-wait.mp4` on the server or in local dev.

**Do not commit copyrighted match footage.** If the file is missing or the browser cannot play it, the overlay falls back to CSS-only (no error shown to the user).

Deploy: rsync includes `static/` (see `scripts/deploy_to_vps.sh`). After adding the MP4 on the VPS, set `HIBS_LAUNCH_MEDIA=1` in `/opt/hibs-bet/.env` and restart `hibs-bet`.
