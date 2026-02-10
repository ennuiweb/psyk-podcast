# Personlighedspsykologi (NotebookLM Generation)

This folder contains the generation pipeline assets for Personlighedspsykologi audio + infographic + quiz production.
It is **not** a podcast feed. Feeds now live in:

- `shows/personlighedspsykologi-da`
- `shows/personlighedspsykologi-en`

## Key paths
- `scripts/` - generation helpers (`generate_week.py`, `download_week.py`)
- `prompt_config.json` - prompts + language variants for NotebookLM (audio + infographic + quiz defaults)
- `sources/` - W## source folders (PDFs, readings)
- `output/` - generated MP3s/PNGs/quiz exports + request logs
- `docs/` - planning notes and reading keys

Archived show configs are stored in `archive-show-config/` for reference.

Current generation is configured for English-only outputs (see `prompt_config.json`).

## Quiz generation
- Configure quiz settings in `prompt_config.json` under `quiz` (difficulty, quantity, format, prompt).
- Generate quizzes for a week:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py --week W01 --content-types quiz --profile default
```

- Download quiz exports from request logs:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py --week W01 --content-types quiz
```

- Override quiz download format (html/markdown/json):

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py --week W01 --content-types quiz --format html
```

## Quiz hosting (droplet)
Quiz HTML exports are hosted on the droplet under:
`http://64.226.79.109/quizzes/personlighedspsykologi-en/<Week>/<Filename>.html`

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
