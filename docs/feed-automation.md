# Feed Automation

## Scope

This document covers the shared feed pipeline for shows under `shows/<show-slug>/`.

## Repo layout

- `podcast-tools/gdrive_podcast_feed.py` - shared feed generator.
- `podcast-tools/transcode_drive_media.py` - optional in-place Drive transcoding before feed generation.
- `shows/<show-slug>/` - one directory per show with config, metadata, docs, and generated feed artifacts.
- `.github/workflows/generate-feed.yml` - matrix workflow that builds all configured shows.

Active show directories currently include:

- `shows/personlighedspsykologi-en/`
- `shows/bioneuro/`
- `shows/social-psychology/`
- `shows/berlingske/`
- `shows/personal/`
- `shows/intro-vt/`

## Local feed run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp shows/<show-slug>/config.template.json shows/<show-slug>/config.local.json
python podcast-tools/gdrive_podcast_feed.py --config shows/<show-slug>/config.local.json
```

Output:

- `shows/<show-slug>/feeds/rss.xml`

Per-show metadata files:

- `shows/<show-slug>/config.github.json`
- `shows/<show-slug>/config.local.json`
- `shows/<show-slug>/config.template.json`
- `shows/<show-slug>/episode_metadata.json`
- `shows/<show-slug>/episode_metadata.template.json`

## Google setup

One-time setup:

1. Enable the Google Drive API in a Google Cloud project.
2. Create a service account and download the JSON key.
3. Share the target Drive folder with the service account.
4. Enable link sharing for audio files or let the generator update permissions when allowed.

GitHub Actions secrets:

- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `DRIVE_FOLDER_ID`

The workflow writes:

- `shows/<show-slug>/service-account.json`
- `shows/<show-slug>/config.runtime.json`

## Workflow behavior

`.github/workflows/generate-feed.yml` runs daily and on `workflow_dispatch`.

For each show it:

1. checks secrets
2. writes runtime credentials/config
3. optionally transcodes matching Drive media
4. runs `gdrive_podcast_feed.py`
5. for quiz-enabled subjects, syncs quiz links and rebuilds the subject content manifest
6. commits generated artifacts back to `main` when needed

Tracked feed artifacts live under:

- `shows/**/feeds/rss.xml`

## Feed hosting

Publish:

- `shows/<show-slug>/feeds/rss.xml`

GitHub Pages example:

- `https://<username>.github.io/psyk-podcast/shows/<show-slug>/feeds/rss.xml`

## Apps Script trigger

The Drive trigger helper lives in:

- `apps-script/drive_change_trigger.gs`

Use it when a Drive upload should trigger `generate-feed.yml` via `workflow_dispatch`.

If using `clasp`, the repo helpers are:

- `apps-script/.clasp.json.example`
- `apps-script/push_drive_trigger.sh`

## Shared-drive notes

In per-show config:

- set `shared_drive_id` when the show uses a shared drive
- keep `include_items_from_all_drives` enabled
- set `skip_permission_updates: true` when the service account cannot change sharing

In Apps Script:

- set `CONFIG.drive.sharedDriveId` to the same shared drive

## Metadata and images

Per-episode overrides belong in:

- `shows/<show-slug>/episode_metadata.json`

Optional image automation:

- set `episode_image_from_infographics: true` in the show config to derive episode artwork from matching Drive images

## Troubleshooting

- JSON key parse failures usually mean `GOOGLE_SERVICE_ACCOUNT_JSON` was stored with extra quoting or base64.
- Missing config errors should reference `shows/<show-slug>/config.github.json`; create it from `config.template.json`.
- Anonymous download throttling is a Drive constraint, not a feed-generator bug.

## Related docs

- [../TECHNICAL.md](../TECHNICAL.md)
- [README.md](README.md)
- [../shows/personlighedspsykologi-en/docs/README.md](../shows/personlighedspsykologi-en/docs/README.md)
- [../shows/bioneuro/docs/README.md](../shows/bioneuro/docs/README.md)
