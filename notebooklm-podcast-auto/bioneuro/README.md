# Bioneuro (NotebookLM Generation)

Dette fag er en let wrapper omkring den eksisterende ugegenerator, med `bioneuro`-defaults.

## Kilde-rod (default)
- `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Bioneuro/Readings`

## Filer
- `prompt_config.json` - prompt/language/artifact defaults.
- `scripts/generate_week.py` - wrapper til den fælles ugegenerator med `bioneuro`-stier som default.

## Brug

Dry-run for én uge:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/bioneuro/scripts/generate_week.py --week W1L1 --dry-run
```

Generér audio:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/bioneuro/scripts/generate_week.py --week W1L1 --content-types audio
```

Bemærk:
- Du kan stadig overskrive defaults med egne argumenter (`--sources-root`, `--prompt-config`, `--output-root`).
