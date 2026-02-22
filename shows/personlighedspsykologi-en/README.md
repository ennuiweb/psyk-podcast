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
Block note: `course_week_lecture` renders compact `U#F#` (from `W#L#`), `week_date_range` renders `dd/mm - dd/mm`, and `feed.description_prepend_semester_week_lecture: true` prepends `Semesteruge X, Forelæsning Y` as a heading with a blank line before the next description block.
Description order note: for `reading`, `brief`, and `weekly_overview`, `feed.description_blocks_by_kind` is set to `quiz -> summary -> key points`; when no quiz link exists, the summary/key-points blocks render without the quiz block.
Quiz localization note: `quiz.labels` controls heading and difficulty labels in descriptions (currently `Quizzer` with `Let/Mellem/Svær`).
Feed ordering note: `feed.sort_mode: "wxlx_kind_priority"` groups by `W#L#` and orders each block as `Brief -> Alle kilder -> Oplæst/TTS readings -> other readings`; blocks are still ordered by newest publish timestamp.
Unassigned TTS note: audio files without week tokens (for example in Drive folder `grundbog-tts/`) are auto-scheduled before week 1 and therefore render at the end of the feed.
Feed pubDate note: `feed.pubdate_year_rewrite` rewrites only item `<pubDate>` year tokens during generation (for this show: `2026 -> 2025`) and does not change channel `<lastBuildDate>`.

Reading-summary workflow:
- Scaffold/update cached entries from local episodes:
  - `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --dry-run`
  - `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py`
- Scaffold/update per-lecture `Alle kilder` cache from reading-summary coverage + draft aggregate:
  - `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --sync-weekly-overview --dry-run`
  - `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --sync-weekly-overview`
- Validate completeness (warn-only):
  - `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --validate-only`
  - `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --validate-only --validate-weekly`
- Build feed after sync:
  - `python3 podcast-tools/gdrive_podcast_feed.py --config shows/personlighedspsykologi-en/config.local.json`
- Sync behavior:
  - uses local audio files (`.mp3`/`.wav`) to discover `reading`, `brief`, and `TTS` episode keys.
  - excludes `Alle kilder` / `All sources` files from the reading summary inventory.
  - preserves existing filled entries and only adds missing placeholders in `reading_summaries.json`.
  - run scaffold/update before validation when checking a fresh cache (`--validate-only` reads current file contents only).
  - manual fill targets are `2-4` summary lines and `3-5` key points per entry.
  - language rule: when the source text is Danish, write both `summary_lines` and `key_points` in Danish (otherwise keep English).
  - `shows/personlighedspsykologi-en/reading_summaries.json` is the combined file to edit and commit.
  - `Alle kilder` cache is `shows/personlighedspsykologi-en/weekly_overview_summaries.json`; entries are lecture-level (`W#L#`) and scaffolded from all source summaries for that lecture, then manually finalized in Danish.
  - weekly validation is warn-only for missing entries, incomplete fields, non-Danish content, and source coverage gaps.

Feed build prerequisites: install `google-auth` + `google-api-python-client`, then provide `shows/personlighedspsykologi-en/service-account.json`.
Troubleshooting: if system Python shows `Missing Google API dependencies`, run with `./notebooklm-podcast-auto/.venv/bin/python` or install deps via `pip install -r requirements.txt`.
Troubleshooting: warning `missing Grundbog lydbog tail source(s)` means one or more expected tail chapters are absent in Drive; feed generation still completes, but those tail entries are skipped.
Update the Drive folder ID, owner email, and upload service account credentials before enabling automation.

Quiz link sync note:
- `scripts/sync_quiz_links.py` and `podcast-tools/sync_drive_quiz_links.py` use quiz JSON exports as the source of truth.
- `shows/personlighedspsykologi-en/quiz_links.json` intentionally keeps `.html` relative paths so public links remain `/q/<id>.html`.

Reading key sync note:
- Source of truth file: `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Personlighedspsykologi/.ai/reading-file-key.md`
- Primary repo mirror used by feed config: `shows/personlighedspsykologi-en/docs/reading-file-key.md`
- Secondary repo mirror (NotebookLM docs): `notebooklm-podcast-auto/personlighedspsykologi/docs/reading-file-key.md`
- Sync commands:
  - Dry-run: `python3 scripts/sync_personlighedspsykologi_reading_file_key.py`
  - Apply: `python3 scripts/sync_personlighedspsykologi_reading_file_key.py --apply`
  - One-time bootstrap source from current repo file: `python3 scripts/sync_personlighedspsykologi_reading_file_key.py --bootstrap-source-from-repo --apply`
