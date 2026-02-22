## Deployment Policy

- Når ændringer i `freudd_portal` er færdigimplementerede, skal der altid deployes til freudd-portal-miljøet som sidste trin.

## README Command Inventory (checked 2026-02-12)

### Selected explicit runnable commands

`shows/berlingske/README.md`
- `python podcast-tools/ingest_manifest_to_drive.py --manifest /Users/oskar/repo/avisartikler-dl/downloads/manifest.tsv --downloads-dir /Users/oskar/repo/avisartikler-dl/downloads --config shows/berlingske/config.local.json`

`shows/personal/README.md`
- `python podcast-tools/gdrive_podcast_feed.py --config shows/personal/config.local.json --dry-run`
- `python podcast-tools/gdrive_podcast_feed.py --config shows/personal/config.local.json`

`notebooklm-podcast-auto/personlighedspsykologi/README.md`
- `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py --week W1 --content-types quiz --profile default`
- `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py --week W1 --content-types quiz`
- `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py --week W01 --content-types quiz --format html`
- `python3 scripts/sync_quiz_links.py --subject-slug personlighedspsykologi --dry-run`
- `python3 scripts/sync_quiz_links.py --subject-slug personlighedspsykologi`
