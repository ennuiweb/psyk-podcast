# psyk-podcast · [RSS feed](https://raw.githubusercontent.com/ennuiweb/psyk-podcast/main/shows/social-psychology/feeds/rss.xml)

Automation to build podcast RSS feeds from audio files stored in Google Drive. The current show (`shows/social-psychology`) regenerates `shows/social-psychology/feeds/rss.xml` automatically via GitHub Actions, and the structure is ready for additional shows later on.

## Repository layout
- `podcast-tools/gdrive_podcast_feed.py` – shared generator script used by every show.
- `shows/` – one directory per podcast. Each show keeps its own config, metadata, docs, and generated feeds (for example `shows/social-psychology/`).
  - `shows/intro-vt/` ships as scaffolding for the "Intro + VT Deep Dives - Hold 1 - 2024" series—copy the templates inside when you are ready to wire the feed up. GitHub Actions now runs each show via a build matrix, so once a new show directory follows the same structure and is referenced in the workflow matrix, it will publish automatically.
  - `shows/intro-vt-tss/` and `shows/social-psychology-tts/` provide text-to-speech variants that reuse the deep-dive auto spec and share the same automation flow.
- `requirements.txt` – Python dependencies needed locally and in CI.

### MIME type filtering
Each show config can optionally supply `"allowed_mime_types"` to control which Google Drive items should become feed entries. Values ending with `/` are treated as prefixes (for example `"audio/"`), while exact MIME types (such as `"video/mp4"`) match specific files. The default behaviour includes only audio files, so add types like `"video/mp4"` if you want lecture videos to appear in the feed without manual conversion.

### Automatic Drive transcoding
`podcast-tools/transcode_drive_media.py` converts matching Drive videos to audio before the feed build runs. Provide a `transcode` block in each show config to opt in:

```json
"transcode": {
  "enabled": true,
  "source_mime_types": [
    "video/mp4",
    "audio/wav",
    "audio/x-wav"
  ],
  "target_extension": "mp3",
  "target_mime_type": "audio/mpeg",
  "codec": "libmp3lame",
  "bitrate": "48k",
  "extra_ffmpeg_args": ["-ac", "1", "-ar", "22050"]
}
```

The workflow installs `ffmpeg`, downloads each video, transcodes it locally, and uploads the audio back into the original Drive file (updating its name, MIME type, and content). Because the conversion happens in place, no additional storage quota is required and the feed generator only ever sees audio assets.

For text-to-speech feeds we transcode large WAV uploads the same way—adding `audio/wav` / `audio/x-wav` (and similar variants) ensures anything exported straight from the TTS tool is compressed to listener-friendly MP3 before the RSS build. Long-form readings are further down-mixed to mono and 22.05 kHz at 48 kbps so every episode stays under Drive’s 100 MB virus-scan threshold while remaining perfectly intelligible.

### Automatic dating from the teaching schedule
Shows can point `auto_spec` at a JSON file that maps Drive folder labels to calendar weeks. The Socialpsykologi Deep Dives - Hold 1 - 2024 show ships with `shows/social-psychology/auto_spec.json`, generated from the teaching plan PDF. Each rule ties folder names like `W4 The Self` (anything that contains `w4`) to ISO week 39 of 2024 and sets a Monday 10:00 CET release, spacing additional recordings for that week by 120 minutes. Future recordings dropped into the matching `W*` folders automatically inherit the correct `published_at` timestamp without editing `episode_metadata.json`.

When an episode inherits its publish date from the auto spec (or otherwise lacks a manual title override), the feed generator also prepends the week label derived from the folder—`Week 7: …`, `Week 12: …`, etc.—so podcast apps display the curriculum order even when filenames in Drive stay short.

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

The repository ships with `podcast/config.json` and `podcast/episode_metadata.json` pre-populated for Socialpsykologi Deep Dives - Hold 1 - 2024—update the titles, artwork, contact email, and descriptions to match your own show before publishing.

## Configure GitHub Actions
1. Create two repository secrets:
   - `GOOGLE_SERVICE_ACCOUNT_JSON` – paste the entire JSON key exactly as downloaded (no extra quoting or base64).
   - `DRIVE_FOLDER_ID` – the folder ID from the Google Drive URL.
2. Edit `podcast/config.github.json` with your show metadata. Leave `service_account_file` untouched; the workflow writes the key to that path at runtime. Add a real `podcast/episode_metadata.json` if you want to control titles, descriptions, publish dates, durations, and artwork per episode.
3. (Optional) Commit your custom `podcast/episode_metadata.json`.

To kick off a build manually, go to **Actions → Generate Podcast Feed → Run workflow**. The job also runs every day at 06:00 UTC via cron.

## Drive-triggered rebuilds (Google Apps Script)
If you want the GitHub workflow to fire whenever fresh audio appears in Drive, add a lightweight Apps Script that polls the folder and calls the `Generate Podcast Feed` workflow via `workflow_dispatch`. The helper now supports multiple Drive roots via `CONFIG.drive.folderIds`, so list every show folder there (and re-run `initializeDriveChangeState()` whenever you add one) to keep all series in sync.

1. Visit [script.google.com](https://script.google.com/), create a new project, and paste the helper script below into `Code.gs`. Update the `CONFIG.github` block if you fork the repository or rename the workflow file.
2. In the left toolbar, open **Services** (puzzle icon) and enable the **Drive API** advanced service. If Apps Script prompts you to enable the API in Google Cloud, follow the link and flip it on there as well.
3. In **Project Settings → Script properties** add a property whose key matches `CONFIG.github.tokenProperty` (`GITHUB_PAT` by default) and set its value to a GitHub personal access token with the `repo` and `workflow` scopes.
4. Back in the editor, run `initializeDriveChangeState()` once to capture the current Drive snapshot and seed the manifest used for comparisons.
5. Run `checkDriveAndTrigger()` manually to accept the Drive + external API scopes and confirm the workflow dispatch.
6. Open the clock icon (**Triggers**) → **Add trigger**, select `checkDriveAndTrigger`, choose a time-driven interval (for example every 15 minutes), and save.

The repository keeps this helper at `apps-script/drive_change_trigger.gs` so you can copy/paste the latest version straight into Apps Script without hunting through the docs.

### Apps Script helper
The canonical automation script lives in `apps-script/drive_change_trigger.gs`. Copy it directly from the repository so you always grab the latest multi-folder logic (`CONFIG.drive.folderIds`, `configuredRootFolderIds()`, etc.). Key bits to double-check before deploying:
- `CONFIG.drive.folderIds` lists every Drive folder that should trigger a rebuild.
- `CONFIG.github.*` values still point at your fork/workflow.
- After updating `folderIds`, re-run `initializeDriveChangeState()` so the stored manifest includes the new structure.


### Using shared drives
- In your show config (`shows/.../config.json`), keep `shared_drive_id` set to the shared drive's ID and leave `include_items_from_all_drives` enabled so the generator can enumerate everything.
- Update the Apps Script helper by setting `CONFIG.drive.sharedDriveId` to the same ID; the change poller will stay scoped to that drive automatically.
- Grant the service account at least Viewer access on the shared drive itself (Sharing → Manage members). Sharing only a subfolder is not sufficient.
- The Drive helper always descends into nested folders, so week subdirectories are tracked automatically.
- Set `skip_permission_updates` to `true` in the show config if your service account cannot modify sharing; flip it back once access is restored so new uploads become public automatically.

The workflow (`.github/workflows/generate-feed.yml`) runs on a daily cron and on manual trigger (`workflow_dispatch`). A matrix build runs once per show and performs these steps:
- check out the repository and install dependencies;
- write the shared service-account JSON secret to `shows/<show>/service-account.json`;
- materialise a `config.runtime.json` per show (optionally overriding the Drive folder ID from GitHub Secrets);
- probe for Drive videos that need transcoding, run `transcode_drive_media.py` when required, and then execute `gdrive_podcast_feed.py` for that show;
- commit `shows/<show>/feeds/rss.xml` back to the default branch whenever it changes.

You can either bake Drive folder IDs directly into each `config.github.json` or supply encrypted secrets (for example `DRIVE_FOLDER_ID_SOCIAL_PSYCHOLOGY`). The workflow will prefer show-specific secrets, fall back to a shared `DRIVE_FOLDER_ID`, and finally use the value from the config file when no secret is present.

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
