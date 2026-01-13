# Berlingske Narrated Articles

Feed setup for Berlingske narrated articles sourced from the downloader manifest.
This show expects episode metadata to be generated from the manifest and Drive
uploads.

## Key files
- `config.local.json` – local test run against the Drive folder.
- `config.github.json` – checked-in config for CI; Drive folder ID is supplied
  via secrets.
- `episode_metadata.json` – generated metadata keyed by Drive file ID.
- `assets/cover.png` – square artwork referenced by the feed.

## Ingest + metadata generation
Use the ingestion helper to upload local downloads to Drive and build metadata
from `manifest.tsv`:

```bash
python podcast-tools/ingest_manifest_to_drive.py \
  --manifest /Users/oskar/repo/avisartikler-dl/downloads/manifest.tsv \
  --downloads-dir /Users/oskar/repo/avisartikler-dl/downloads \
  --config shows/berlingske/config.local.json
```

This writes `shows/berlingske/episode_metadata.json` and uploads any missing
files to Drive. The feed generator then uses the publication date from the
manifest instead of the Drive upload time.
