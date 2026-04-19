# NotebookLM Automation

## Scope

This document covers the repo-level NotebookLM automation layout and the subject wrappers that depend on it.

## Layout

- `notebooklm-podcast-auto/personlighedspsykologi/` - Personlighedspsykologi wrapper scripts, docs, tests, and evaluation assets.
- `notebooklm-podcast-auto/bioneuro/` - Bioneuro wrapper scripts and output flow.
- `notebooklm-podcast-auto/notebooklm-py/` - tracked submodule with the underlying client, docs, and test surface.

## Primary commands

Personlighedspsykologi:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py --week W01L1 --dry-run
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --validate-only --validate-weekly
```

Bioneuro:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/bioneuro/scripts/generate_week.py --week W1L1 --dry-run
```

## Output and mirrors

Default output roots:

- `notebooklm-podcast-auto/personlighedspsykologi/output`
- `notebooklm-podcast-auto/bioneuro/output`

Mirror helper:

- `scripts/mirror_output_dirs.py`

Examples:

```bash
python3 scripts/mirror_output_dirs.py --subject bioneuro --dry-run
python3 scripts/mirror_output_dirs.py --subject personlighedspsykologi --dry-run
python3 scripts/mirror_output_dirs.py --subject all
```

Pre-push currently mirrors both subjects, but mirror failures are warning-only.

Important operational note:

- `notebooklm-podcast-auto/personlighedspsykologi/output` must be a real directory, not a macOS Alias file. Alias files break the shared mirror step and create noisy pre-push warnings.

## Personlighedspsykologi source rules

The canonical reading source is the absolute OneDrive Readings root:

- `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Personlighedspsykologi/Readings`

Relevant sync utilities:

- `scripts/sync_personlighedspsykologi_reading_file_key.py`
- `scripts/sync_personlighedspsykologi_readings_to_droplet.py`
- `notebooklm-podcast-auto/personlighedspsykologi/scripts/migrate_onedrive_sources.py`

## Manual summary policy

Hand-authored summary sources:

- `shows/personlighedspsykologi-en/reading_summaries.json`
- `shows/personlighedspsykologi-en/weekly_overview_summaries.json`

`sync_reading_summaries.py` validates and scaffolds, but it is not the source of final summary prose.

## Related docs

- [../shows/personlighedspsykologi-en/docs/README.md](../shows/personlighedspsykologi-en/docs/README.md)
- [../shows/bioneuro/docs/README.md](../shows/bioneuro/docs/README.md)
- [../notebooklm-podcast-auto/notebooklm-py/docs/README.md](../notebooklm-podcast-auto/notebooklm-py/docs/README.md)
- [README.md](README.md)
