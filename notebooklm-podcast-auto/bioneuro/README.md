# Bioneuro (NotebookLM Generation)

Dette fag er en let wrapper omkring den eksisterende ugegenerator, med `bioneuro`-defaults.

## Kilde-rod (default)
- `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Bioneuro/Readings`

## Filer
- `prompt_config.json` - prompt/language/artifact defaults.
- `scripts/generate_week.py` - wrapper til den fælles ugegenerator med `bioneuro`-stier som default.
- `scripts/download_week.py` - wrapper til download af artifacts fra request-logs med `bioneuro` output-root som default.

## Brug

Dry-run for én uge:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/bioneuro/scripts/generate_week.py --week W1L1 --dry-run
```

Generér audio:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/bioneuro/scripts/generate_week.py --week W1L1 --content-types audio
```

Download artifacts for flere uger:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/bioneuro/scripts/download_week.py --weeks 1,2,3,4,5,6,8,9,10,11,12
```

Bemærk:
- Du kan stadig overskrive defaults med egne argumenter (`--sources-root`, `--prompt-config`, `--output-root`).
