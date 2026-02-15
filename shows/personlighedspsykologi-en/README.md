# Personlighedspsykologi

Scaffolding for the "Personlighedspsykologi" feed.

- `config.local.json` - local test run against a Drive folder.
- `config.github.json` - committed config for CI once secrets exist.
- `auto_spec.json` - W01-W22 schedule derived from the 2026 forelaesningsplan.
- `episode_metadata.json` - optional per-file overrides.
- `reading_summaries.json` - cached per-reading summary + key-points blocks for episode descriptions.
- `assets/cover-new.png` - square artwork (min. 1400x1400) referenced by the feed.
- `docs/` - planning material and any "important text" docs.

Feed note: generated episode `title` and `description` are block-composed. Use `feed.title_blocks` / `feed.description_blocks` (and optional `*_by_kind`) for formatting control.
Feed ordering note: `feed.sort_mode: "wxlx_kind_priority"` groups by `W#L#` and orders each block as `Brief -> Alle kilder -> Oplæst/TTS readings -> other readings`; blocks are still ordered by newest publish timestamp.

Reading-summary workflow:
- Scaffold/update cached entries from local episodes:
  - `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --dry-run`
  - `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py`
- Validate completeness (warn-only):
  - `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --validate-only`
- Build feed after sync:
  - `python3 podcast-tools/gdrive_podcast_feed.py --config shows/personlighedspsykologi-en/config.local.json`
- Sync behavior:
  - uses local audio files (`.mp3`/`.wav`) to discover `reading`, `brief`, and `TTS` episode keys.
  - excludes weekly overview files (`Alle kilder` / `All sources`) from the summary inventory.
  - preserves existing filled entries and only adds missing placeholders in `reading_summaries.json`.
  - run scaffold/update before validation when checking a fresh cache (`--validate-only` reads current file contents only).
  - manual fill targets are `2-4` summary lines and `3-5` key points per entry.
  - `shows/personlighedspsykologi-en/reading_summaries.json` is the combined file to edit and commit.

Feed build prerequisites: install `google-auth` + `google-api-python-client`, then provide `shows/personlighedspsykologi-en/service-account.json`.
Update the Drive folder ID, owner email, and upload service account credentials before enabling automation.
