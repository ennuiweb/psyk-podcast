# Podcasts Memory

## Snapshot

- Feed model note, 2026-04-09: the newer subject feeds in this repo are not fully non-Drive. They are still Drive-backed for media inventory via `drive_folder_id`, but repo-first for structure and metadata.
- `podcast-tools/gdrive_podcast_feed.py` still enumerates Drive files, then merges repo-authored inputs such as `episode_metadata.json`, `reading_summaries.json`, `weekly_overview_summaries.json`, `quiz_links.json`, `auto_spec.json`, important-text docs, filters, and feed block rules before writing RSS.
- For Freudd-backed subjects, `content_manifest.json` is the lecture-first merge layer built from reading key + quiz links + RSS + Spotify map + slides catalog; the portal reads that manifest instead of treating Drive as the UI source of truth.
