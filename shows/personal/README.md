# Personal Listening Feed

This show is a private catch-all feed backed by Cloudflare R2. The feed itself
is now generated from `media_manifest.r2.json` and `episode_inventory.json`,
while the one-off importer in `scripts/migrate_drive_show_to_r2.py` remains the
pragmatic way to sweep a legacy Drive folder into R2 without changing episode
GUIDs.

There is no auto-spec. Publish dates and ordering are derived from the stored
media metadata, so avoid rewriting existing objects or changing stable object
keys once episodes are in podcast apps.

## Key files
- `config.local.json` – local R2-backed feed config.
- `config.github.json` – checked-in config used by GitHub Actions.
- `config.template.json` – copy when provisioning new environments.
- `episode_metadata.json` – optional overrides (leave `{}` to mirror Drive).
- `episode_inventory.json` – generated inventory used to preserve feed identity.
- `media_manifest.r2.json` – generated R2 object manifest with `stable_guid`.
- `assets/cover.png` – square artwork referenced by the RSS feed.

## Local generation
```bash
python podcast-tools/gdrive_podcast_feed.py --config shows/personal/config.local.json
```

This rebuilds `feeds/rss.xml` and `episode_inventory.json` from the checked-in
R2 manifest.

## Import from legacy Drive

If you still have new audio accumulating in the old Drive folder, sweep it into
R2 and refresh the manifest with:

```bash
python scripts/migrate_drive_show_to_r2.py \
  --config shows/personal/config.local.json \
  --source-config /tmp/personal-drive-source.json \
  --bucket freudd \
  --endpoint https://abf1940818ee3c8a0fa4bc84c7b1bba9.r2.cloudflarestorage.com \
  --prefix shows/personal \
  --public-base-url https://pub-fe942499398a478c8a8f432207051244.r2.dev
python podcast-tools/gdrive_podcast_feed.py --config shows/personal/config.local.json
```

The importer is resumable:

- it skips already-uploaded objects by key and size
- it preserves old Drive-based GUIDs in `stable_guid`
- it retries transient Drive and R2 transfer failures instead of failing cold

## CI wiring
- The show remains `publication.owner = "legacy_workflow"`.
- GitHub Actions reads `media_manifest.r2.json` and requires R2 secrets.
- Workflow matrix entry: `.github/workflows/generate-feed.yml` lists `personal`.
- `apps-script/drive_change_trigger.gs` no longer watches the old personal Drive folder because live publication is now R2-backed.
