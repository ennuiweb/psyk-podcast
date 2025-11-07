# Personal Listening Feed

This show is a private catch-all feed for any audio dropped into the Drive folder
`1GrwLcua1UN_tCX0ec9NmDU6ynLkuM_0G`. There is no auto-spec; publish dates come
directly from each file’s Drive `modifiedTime`, so avoid re-uploading or editing
files once they appear in podcast apps.

## Key files
- `config.local.json` – real folder ID for local runs.
- `config.github.json` – checked-in template that CI hydrates with secrets.
- `config.template.json` – copy when provisioning new environments.
- `episode_metadata.json` – optional overrides (leave `{}` to mirror Drive).
- `assets/cover.png` – square artwork referenced by the RSS feed.

## Local generation
```bash
python podcast-tools/gdrive_podcast_feed.py --config shows/personal/config.local.json --dry-run
python podcast-tools/gdrive_podcast_feed.py --config shows/personal/config.local.json
```

The dry run validates permissions without changing Drive sharing links;
rerunning without `--dry-run` updates `feeds/rss.xml`.

## CI wiring
- Drive ID lives in the checked-in config (same strategy as other shows).
- Workflow matrix entry: `.github/workflows/generate-feed.yml` lists `personal`.
- Apps Script watcher: `apps-script/drive_change_trigger.gs` includes the folder ID so uploads trigger the workflow automatically.
