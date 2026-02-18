# Personlighedspsykologi (NotebookLM Generation)

This folder contains the generation pipeline assets for Personlighedspsykologi audio + infographic + quiz production.
It is **not** a podcast feed. Feed config now lives in:

- `shows/personlighedspsykologi-en`
- Feed ordering preference is configured there via `feed.sort_mode: "wxlx_kind_priority"` (`Brief -> Alle kilder -> Oplæst/TTS readings -> other readings` within each `W#L#` block).

## Key paths
- `scripts/` - generation helpers (`generate_week.py`, `download_week.py`, `sync_reading_summaries.py`)
- `prompt_config.json` - prompts + language variants for NotebookLM (audio + infographic + quiz defaults)
- `sources/` - W## source folders (PDFs, readings)
- `output/` - generated MP3s/PNGs/quiz exports + request logs
- `docs/` - planning notes

Archived show configs are stored in `archive-show-config/` for reference.

Current generation is configured for English-only outputs (see `prompt_config.json`).

## "Alle kilder" notebook behavior (lecture-level episodes)
- `Alle kilder` generation runs per lecture (`W#L#`) and uses a fresh NotebookLM notebook on every run (no notebook reuse).
- This guarantees the run re-uploads the full lecture source list instead of relying on existing notebook sources.

## Output filename config tags
- `generate_week.py` appends a human-readable config tag before the extension: ` {...}`.
- The tag includes artifact output options (type/language + API settings) and a full effective generation config hash.
- `Alle kilder` audio outputs additionally include `sources=<n>` (number of uploaded sources in the lecture notebook).
- Output filenames never append profile collision suffixes like `[default]` or `[default-2]`; canonical paths are always used.
- Reading filenames are normalized to a single leading week token (`W#L# - ...`) even when source PDFs include repeated week labels.
- Legacy files generated before this normalization fix are not auto-renamed; you can keep them as-is or run a one-time cleanup.
- Example: `W11L2 - X Raggatt (2006) [EN] {type=audio lang=en format=deep-dive length=long hash=7f1bf8c4}.mp3`
- Tag regex contract (case-insensitive in parsers):
  - `\s\{[a-z0-9._:+-]+=[^{}\s]+(?:\s+[a-z0-9._:+-]+=[^{}\s]+)*\}`
- Controls:
  - `--config-tagging` (default on)
  - `--no-config-tagging`
  - `--config-tag-len N` (default: 8)

## Quiz generation
- Configure quiz settings in `prompt_config.json` under `quiz` (difficulty, quantity, format, prompt).
- Generate quizzes for a week:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py --week W1 --content-types quiz --profile default
```

- Download quiz exports from request logs:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py --week W1 --content-types quiz
```

- Download all output types (audio + infographic + quiz) for a full week or a specific lecture:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py --weeks W2
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py --weeks W2L1
```

- Override quiz download format (html/markdown/json):

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py --week W01 --content-types quiz --format html
```

## Reading summaries cache (for feed descriptions)
- Scaffold missing summary entries from local episode files (dry-run first):

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --dry-run
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py
```

- Scaffold/update per-lecture `Alle kilder` cache from all source summaries:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --sync-weekly-overview --dry-run
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --sync-weekly-overview
```

- Validate coverage (warn-only, no writes):

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --validate-only
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --validate-only --validate-weekly
```

- Rebuild the feed after syncing summaries:

```bash
python3 podcast-tools/gdrive_podcast_feed.py --config shows/personlighedspsykologi-en/config.local.json
```

- Sync behavior:
  - Uses local audio files under `output/` as inventory (`reading`, `brief`, and `TTS` variants).
  - Excludes `Alle kilder` / `All sources` files from the reading summary inventory.
  - Adds missing `by_name` placeholders with empty `summary_lines` + `key_points`.
  - `--validate-only` reports missing/incomplete entries and always exits non-blocking for coverage gaps.
  - Run scaffold/update before validation when checking a fresh cache (`--validate-only` reads current file state only).
  - Writes cache to `shows/personlighedspsykologi-en/reading_summaries.json`.
  - `Alle kilder` cache path is `shows/personlighedspsykologi-en/weekly_overview_summaries.json`; it stores Danish manual lecture-level summaries plus source-coverage metadata and draft aggregate text.
  - `--sync-weekly-overview` updates lecture-level `Alle kilder` coverage metadata and draft fields, while preserving manual `summary_lines` / `key_points`.
  - `--validate-weekly` adds warn-only lecture-level checks (`weekly_missing_entry`, `weekly_incomplete_summary`, `weekly_incomplete_key_points`, `weekly_non_danish`, `weekly_source_coverage_gap`).
  - Manual fill targets are `2-4` summary lines and `3-5` key points per entry.
  - Language rule: if the source text is Danish, write `summary_lines` and `key_points` in Danish (otherwise keep English).
  - Feed build requires Google dependencies (`google-auth`, `google-api-python-client`) and `shows/personlighedspsykologi-en/service-account.json`.

## Troubleshooting
- If you interrupt `download_week.py` while waiting, rerun the same command. Already-downloaded outputs are skipped.
- To avoid long waits for in-progress artifacts, set `--timeout` and rerun later.
- To list legacy double-prefix files (`W1L1 - W1L1 ...`), run:
  `find notebooklm-podcast-auto/personlighedspsykologi/output -type f | rg '/W[0-9]+L[0-9]+/W[0-9]+L[0-9]+ - W[0-9]+L[0-9]+'`

## Quiz hosting (droplet)
Quiz HTML exports are hosted on the droplet under:
`http://64.226.79.109/quizzes/personlighedspsykologi/<Week>/<Filename>.html`
Keep a compatibility alias from `/quizzes/personlighedspsykologi-en/` while old links are still in circulation.

The mapping and upload can run automatically in GitHub Actions (when quiz HTML
files are uploaded to Drive) via `podcast-tools/sync_drive_quiz_links.py`, as
long as the repository has the secret `DIGITALOCEAN_SSH_KEY` set. The Apps Script
Drive trigger must include `text/` in `mimePrefixes` to detect quiz HTML changes.

Use the sync script locally to upload quizzes and update the mapping used by the feed:

```bash
python3 scripts/sync_quiz_links.py --quiz-difficulty medium --dry-run
python3 scripts/sync_quiz_links.py --quiz-difficulty medium
```

The mapping file lives at `shows/personlighedspsykologi-en/quiz_links.json` and is
used by the feed generator to append quiz links to episode descriptions when
available.
Use `--quiz-difficulty any` if you intentionally want to map all difficulties.
