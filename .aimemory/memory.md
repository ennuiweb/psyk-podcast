# Podcasts Memory

## Snapshot

- Feed model note, 2026-04-19: the shared feed pipeline now supports both `storage.provider=drive` and `storage.provider=r2`. Feed generation uses `podcast-tools/storage_backends.py`, preserves GUID continuity from `episode_inventory.json`, and can read Cloudflare R2 either from a manifest or direct bucket listing.
- `podcast-tools/gdrive_podcast_feed.py` now merges storage-backed media inventory with repo-authored inputs such as `episode_metadata.json`, `reading_summaries.json`, `weekly_overview_summaries.json`, `quiz_links.json`, `auto_spec.json`, important-text docs, filters, and feed block rules before writing RSS.
- `podcast-tools/transcode_drive_media.py` remains Drive-only by design and exits cleanly for object-storage-backed shows; the intended R2 path is to upload already-publishable audio at stable object keys.
- For Freudd-backed subjects, `content_manifest.json` is the lecture-first merge layer built from reading key + quiz links + RSS + Spotify map + slides catalog; the portal reads that manifest instead of treating Drive as the UI source of truth.
