# psyk-podcast

Automation to build an RSS feed from audio files stored in a single Google Drive folder. A GitHub Actions workflow regenerates `podcast/rss.xml` on a schedule so the feed always reflects the contents of the folder.

## Repository layout
- `podcast/gdrive_podcast_feed.py` – main generator script.
- `podcast/config.sample.json` – starter config for local runs.
- `podcast/config.github.json` – config template consumed by the GitHub Actions workflow.
- `podcast/episode_metadata.sample.json` – optional overrides per episode.
- `requirements.txt` – Python dependencies.

## One-time Google setup
1. Enable the Google Drive API in a Google Cloud project.
2. Create a service account, download the JSON key, and keep it private.
3. Share the target Google Drive folder (Viewer) with the service-account email so it can list files.
4. Turn on link sharing for existing audio files or let the script do it automatically.

## Local testing
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp podcast/config.sample.json podcast/config.local.json
# edit podcast/config.local.json and (optionally) podcast/episode_metadata.sample.json
python podcast/gdrive_podcast_feed.py --config podcast/config.local.json
```
`podcast/rss.xml` is overwritten on each run.

The repository ships with `podcast/config.json` and `podcast/episode_metadata.json` pre-populated for the Autumn 2025 Social Psychology course—update the titles, artwork, contact email, and descriptions to match your own show before publishing.

## Configure GitHub Actions
1. Create two repository secrets:
   - `GOOGLE_SERVICE_ACCOUNT_JSON` – paste the entire JSON key exactly as downloaded (no extra quoting or base64).
   - `DRIVE_FOLDER_ID` – the folder ID from the Google Drive URL.
2. Edit `podcast/config.github.json` with your show metadata. Leave `service_account_file` untouched; the workflow writes the key to that path at runtime. Add a real `podcast/episode_metadata.json` if you want to control titles, descriptions, publish dates, durations, and artwork per episode.
3. (Optional) Commit your custom `podcast/episode_metadata.json`.

To kick off a build manually, go to **Actions → Generate Podcast Feed → Run workflow**. The job also runs every day at 06:00 UTC via cron.

### Using shared drives
- If the Google Drive folder lives inside a Shared Drive (formerly Team Drive), set the `shared_drive_id` field in the config to that drive's ID (the portion after `/drives/` in the URL).
- Keep `include_items_from_all_drives` set to `true` so the Drive API can enumerate the contents.
- Grant the service account at least Viewer access on the shared drive itself (Sharing → Manage members). It is not enough to share a single folder if the account isn't a member of the drive.
- Turn on `include_subfolders` when you want the generator to crawl nested folders; the script performs a breadth-first walk and includes every audio file it finds.
- Set `skip_permission_updates` to `true` if your service account already has publicly shared files or lacks permission to modify sharing settings; the generator will then leave Drive permissions untouched. Turn it back to `false` once the account can manage sharing so new uploads become public automatically.

The workflow (`.github/workflows/generate-feed.yml`) runs on a daily cron and on manual trigger (`workflow_dispatch`). It performs these steps:
- check out the repository;
- install dependencies;
- write the service-account JSON secret to `podcast/service_account.json` via an inline Python helper;
- inject the Drive folder ID into a temporary config file;
- run the generator script;
- commit an updated `podcast/rss.xml` back to the default branch when it changes.

Ensure the default branch has permissions for GitHub Actions to push (`Repository Settings → Actions → General → Workflow permissions → Read and write`).

## Deploying the feed
Wherever you host the feed (GitHub Pages, S3, Netlify, etc.), publish `podcast/rss.xml`.

### Hosting on GitHub Pages
1. In repository settings, enable **Pages** for the `main` branch.
2. The file will then be reachable at `https://<username>.github.io/psyk-podcast/podcast/rss.xml` with the correct `application/rss+xml` MIME type.
3. Update podcast directories to point at that URL. (The raw GitHub URL works for quick testing but may be throttled and is served as `text/plain`.)

## Customising metadata
- Put per-episode overrides in `podcast/episode_metadata.json` (copy the sample and extend it). Keys can be the file name, or nest under `"by_name"` / `"by_id"` to mix strategies.
- Add `duration` (seconds or `HH:MM:SS`) so players show runtime.
- Supply episode-specific `image` URLs for chapters/artwork if desired.

## Troubleshooting
- The script prints whenever it enables public sharing on a file. Run with `--dry-run` to preview without modifying permissions.
- If the workflow fails with JSON parsing errors, ensure `GOOGLE_SERVICE_ACCOUNT_JSON` is stored as plain JSON (no quotes or base64) so the inline writer can emit a valid key file.
- If the workflow fails with `File not found: podcast/config.github.json`, copy the template to that path and commit it.
- Rate limiting: Google Drive may throttle anonymous downloads. Consider moving media to static hosting (S3, Cloudflare R2, etc.) if directories or listeners report access issues.
