# Feed Automation

## Scope

This document covers the shared feed pipeline for shows under `shows/<show-slug>/`.

Current migration program:

- The canonical queue + object-storage migration plan lives in [notebooklm-queue-r2-migration.md](notebooklm-queue-r2-migration.md).

## Repo layout

- `podcast-tools/gdrive_podcast_feed.py` - shared feed generator for both Drive and R2-backed shows.
- `podcast-tools/storage_backends.py` - shared storage abstraction used by feed generation and migration paths.
- `podcast-tools/transcode_drive_media.py` - optional in-place Drive transcoding before feed generation; skipped for object storage-backed feed reads.
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

## Storage providers

Shows now select a provider via `storage.provider`:

- `drive` - legacy Google Drive flow with service account credentials and optional permission updates.
- `r2` - Cloudflare R2 object storage with either:
  - direct bucket listing via `storage.bucket`, `storage.endpoint`, and `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY`
  - or a checked-in manifest via `storage.manifest_file`

Recommended R2 config fields:

- `storage.provider`
- `storage.bucket`
- `storage.endpoint`
- `storage.region`
- `storage.prefix`
- `storage.public_base_url`
- `storage.manifest_file`

The feed generator preserves `guid` / `episode_key` continuity by:

- reusing values from the existing `episode_inventory.json` when present
- honoring `stable_guid` in manifest entries when present
- falling back to the existing checked-in RSS feed identity map when a show does not yet keep a committed `episode_inventory.json`

The feed generator preserves public episode chronology by:

- reusing the existing `published_at` / `pubDate` for already-published logical episodes when rebuilding from `episode_inventory.json`
- falling back to the checked-in RSS feed's existing `pubDate` only when an inventory file is unavailable
- treating regeneration as a variant swap, not a republication event, so active `B` variants inherit the existing public date rather than getting a new one

## Publication ownership

Shows now also support `publication.owner` in `shows/<show-slug>/config.github.json`:

- `legacy_workflow` - `.github/workflows/generate-feed.yml` remains the canonical writer for generated repo artifacts.
- `queue` - the NotebookLM queue is the canonical writer; the GitHub workflow must skip regeneration and commit steps for that show.

Current default and fallback behavior:

- if `publication.owner` is missing, it resolves to `legacy_workflow`
- invalid `publication.owner` values fail closed in CI

This is intentionally separate from `storage.provider`:

- `storage.provider` decides where audio/media comes from
- `publication.owner` decides which system is allowed to regenerate and commit feed-side artifacts

Current operational reality:

- the feed stack supports both Drive and R2
- `bioneuro` is now live on `storage.provider = "r2"` with `publication.owner = "queue"`
- `intro-vt` is now live on `storage.provider = "r2"` with `publication.owner = "legacy_workflow"`; the checked-in `shows/intro-vt/media_manifest.r2.json` is now the canonical feed source
- `personal` is now live on `storage.provider = "r2"` with `publication.owner = "legacy_workflow"`
- `personal` uses the resumable local-to-R2 publisher as its canonical ingest path; that publisher backfills manifest checksums on resumed catalogs and transcodes configured source formats such as `.m4a` and `.wav` to MP3 before upload
- `personlighedspsykologi-en` is now live on `storage.provider = "r2"` with `publication.owner = "queue"`; the checked-in `media_manifest.r2.json` is the canonical published-audio inventory, while preserved Drive IDs remain historical rollout metadata only
- `social-psychology` is now live on `storage.provider = "r2"` with `publication.owner = "legacy_workflow"`; the checked-in `shows/social-psychology/media_manifest.r2.json` is now the canonical feed source
- the current `bioneuro` public enclosure base is the temporary Cloudflare hostname `https://pub-fe942499398a478c8a8f432207051244.r2.dev`
- `intro-vt` currently uses the same temporary Cloudflare hostname for enclosures
- `personal` currently uses the same temporary Cloudflare hostname for enclosures
- `personlighedspsykologi-en` currently uses the same temporary Cloudflare hostname for enclosures
- `social-psychology` currently uses the same temporary Cloudflare hostname for enclosures
- all active audio-publishing shows are now R2-backed and no longer depend on Drive source ingest

## Google setup

One-time setup:

1. Enable the Google Drive API in a Google Cloud project.
2. Create a service account and download the JSON key.
3. Share the target Drive folder with the service account.
4. Enable link sharing for audio files or let the generator update permissions when allowed.

GitHub Actions secrets:

- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`

The workflow writes:

- `shows/<show-slug>/config.runtime.json`

## Workflow behavior

`.github/workflows/generate-feed.yml` runs daily and on `workflow_dispatch`.

The repo's active GitHub workflows now use Node 24-ready action majors:

- `actions/checkout@v6`
- `actions/setup-python@v6`

For each show it:

1. resolves show policy from `config.github.json`
2. if `publication.owner=queue`, exits the legacy writer path for that show without regenerating artifacts
3. otherwise checks R2 secrets and writes runtime config
4. runs `gdrive_podcast_feed.py`
5. for quiz-enabled subjects, syncs quiz links from local NotebookLM output when present; on legacy non-queue subjects where no local `output/` tree is present in CI, it reuses the committed `quiz_links.json` catalog for remote validation instead of failing on the missing directory, then rebuilds the subject content manifest
6. commits generated artifacts back to `main` when needed

Operationally, this means:

- queue-owned show publishes do not require `generate-feed.yml` on every commit because the queue is already the canonical writer
- the workflow is still required when a `legacy_workflow` show changes, when shared feed/workflow code changes, or when you explicitly want cross-show CI validation

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

Drive-triggered publication for the active show surface is retired. Keep the
script only as a dormant legacy helper for paused feeds or historical recovery.

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

## R2 notes

- Prefer a custom domain or `storage.public_base_url` that points at the bucket’s public hostname.
- Temporary `r2.dev` hostnames are acceptable for cutover validation, but they should be treated as transitional and replaced with the intended production audio domain.
- Keep the bucket key structure stable across rewrites so object URLs remain deterministic.
- If the bucket is listed directly, the workflow requires `R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY`.
- If you want stricter migration control, use `storage.manifest_file` and store `stable_guid` per object.
- For R2-backed shows, feed generation should prefer storage-level public URL settings over legacy top-level `public_link_template` values. This matters for mixed configs where Drive remains the import source but R2 is the published storage target.

## Metadata and images

Per-episode overrides belong in:

- `shows/<show-slug>/episode_metadata.json`

Optional image automation:

- set `episode_image_from_infographics: true` in the show config to derive episode artwork from matching Drive images

## Troubleshooting

- JSON key parse failures usually mean `GOOGLE_SERVICE_ACCOUNT_JSON` was stored with extra quoting or base64.
- Missing config errors should reference `shows/<show-slug>/config.github.json`; create it from `config.template.json`.
- Anonymous download throttling is a Drive constraint, not a feed-generator bug.
- R2 feeds without `storage.public_base_url` or a matching `public_link_template` will generate invalid enclosure URLs.
- If an R2 migration changes object keys without preserving `stable_guid`, downstream clients may treat old episodes as new ones.

## Related docs

- [../TECHNICAL.md](../TECHNICAL.md)
- [README.md](README.md)
- [../shows/personlighedspsykologi-en/docs/README.md](../shows/personlighedspsykologi-en/docs/README.md)
- [../shows/bioneuro/docs/README.md](../shows/bioneuro/docs/README.md)
