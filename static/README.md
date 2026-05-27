# Static assets

## Hibernian heritage badges (UI only)

These crests are **branding assets** for hibs-bet — they are **not** scraped and do not feed the prediction engine.

| File | Era / use |
|------|-----------|
| `badge_2000_present.png` | Current crest — **primary** (favicon, launch, footer, headers) |
| `badge_harp_embroidered.png` | Harp shield — secondary header + pattern tile |
| `badge_1979_circle.png` | 1979 circular crest — empty states, accents |
| `badge_1979_shield_green.png` | Green shield (1979) — watermark corner |
| `badge_1989_2000_oval.png` | Oval sash crest (1989–2000) — watermark |

`badge_harp_shield.png` is an alias of `badge_harp_embroidered.png` for older links.

Templates use macros in `templates/_hibs_brand.html`; config in `src/hibs_predictor/hibs_brand.py`.

**Do not use** `hibs_badge.svg` — not an official crest.

Legacy files (`crest_*.png`, `badges_heritage_montage.png`) may remain for reference; new UI uses the five badges above.

## Optional launch video (`launch-wait.mp4`)

The dashboard can show a full-screen loading overlay while fixtures and enrichment load. By default it uses CSS-only branding (Hibs crest + rotating tips).

To enable an optional **muted** background loop:

1. Set `HIBS_LAUNCH_MEDIA=1` in `.env` (see `.env.example`).
2. Place your own file at `static/launch-wait.mp4` on the server or in local dev.

**Do not commit copyrighted match footage.** If the file is missing or the browser cannot play it, the overlay falls back to CSS-only (no error shown to the user).

Deploy: rsync includes `static/` (see `scripts/deploy_to_vps.sh`). After adding the MP4 on the VPS, set `HIBS_LAUNCH_MEDIA=1` in `/opt/hibs-bet/.env` and restart `hibs-bet`.
