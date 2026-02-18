# Bio / Neuropsychology

Scaffolding for the "Bio / Neuropsychology" feed.

- `config.local.json` - local test run against a Drive folder.
- `config.github.json` - checked-in config for CI once secrets exist.
- `config.template.json` - template copy for additional environments.
- `auto_spec.json` - W1-W13 schedule seeded from Bio/Neuro Readings folders.
- `episode_metadata.json` - seeded by-name placeholders from discovered Readings MP3 files.
- `reading_summaries.json` - per-episode summary/key-point cache (default authoring language: Danish).
- `assets/cover.png` - expected square artwork referenced by the feed.
- `docs/` - planning notes and week/source mapping context.

Local generation:

```bash
python3 podcast-tools/gdrive_podcast_feed.py --config shows/bioneuro/config.local.json --dry-run
python3 podcast-tools/gdrive_podcast_feed.py --config shows/bioneuro/config.local.json
```

Setup notes:
- `drive_folder_id` is intentionally left as `__DRIVE_FOLDER_ID__` in all config variants.
- Current matching expectation is plain `W#` tokens in Drive folder/file names (for example `W1`, `W2`, ...).
