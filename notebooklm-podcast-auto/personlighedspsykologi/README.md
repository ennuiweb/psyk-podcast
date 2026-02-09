# Personlighedspsykologi (NotebookLM Generation)

This folder contains the generation pipeline assets for Personlighedspsykologi audio + infographic production.
It is **not** a podcast feed. Feeds now live in:

- `shows/personlighedspsykologi-da`
- `shows/personlighedspsykologi-en`

## Key paths
- `scripts/` - generation helpers (`generate_week.py`, `download_week.py`)
- `prompt_config.json` - prompts + language variants for NotebookLM (audio + infographic defaults)
- `sources/` - W## source folders (PDFs, readings)
- `output/` - generated MP3s/PNGs + request logs
- `docs/` - planning notes and reading keys

Archived show configs are stored in `archive-show-config/` for reference.

Current generation is configured for English-only outputs (see `prompt_config.json`).
