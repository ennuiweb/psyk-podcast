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
- Sync/update cached summaries from request logs:
  - `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --week W1 --profile default --dry-run`
  - `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --week W1 --profile default`
- Build feed after sync:
  - `python podcast-tools/gdrive_podcast_feed.py --config shows/personlighedspsykologi-en/config.local.json`
- Sync behavior:
  - asks NotebookLM for strict JSON first, then falls back to `source guide` if parsing fails.
  - preserves existing cache entries unless `--refresh` is passed.

Update the Drive folder ID, owner email, and upload the service account credentials before enabling automation.
