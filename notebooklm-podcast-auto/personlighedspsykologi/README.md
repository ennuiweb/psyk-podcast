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

## Weekly "Alle kilder" behavior
- Weekly `Alle kilder` generation uses a fresh NotebookLM notebook on every run (no notebook reuse).
- This guarantees the run re-uploads the full weekly source list instead of relying on existing notebook sources.

## Output filename config tags
- `generate_week.py` appends a human-readable config tag before the extension: ` {...}`.
- The tag includes artifact output options (type/language + API settings) and a full effective generation config hash.
- Weekly `Alle kilder` audio outputs additionally include `sources=<n>` (number of uploaded sources in the weekly notebook).
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
- Sync summary + key points from request logs (dry-run first):

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --week W1 --profile default --dry-run
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --week W1 --profile default
```

- Rebuild the feed after syncing summaries:

```bash
python podcast-tools/gdrive_podcast_feed.py --config shows/personlighedspsykologi-en/config.local.json
```

- Sync behavior:
  - Attempts a strict JSON `notebooklm ask` extraction first.
  - Falls back to `notebooklm source guide` when ask output cannot be parsed.
  - Keeps existing entries unless `--refresh` is passed.
  - Writes cache to `shows/personlighedspsykologi-en/reading_summaries.json`.

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
python3 scripts/sync_quiz_links.py --dry-run
python3 scripts/sync_quiz_links.py
```

The mapping file lives at `shows/personlighedspsykologi-en/quiz_links.json` and is
used by the feed generator to append quiz links to episode descriptions when
available.
