# psyk-podcast · [RSS feed](https://raw.githubusercontent.com/ennuiweb/psyk-podcast/main/shows/social-psychology/feeds/rss.xml)

Automation to build podcast RSS feeds from audio files stored in Google Drive. The current show (`shows/social-psychology`) regenerates `shows/social-psychology/feeds/rss.xml` automatically via GitHub Actions, and the structure is ready for additional shows later on.

## Repository layout
- `podcast-tools/gdrive_podcast_feed.py` – shared generator script used by every show.
- `shows/` – one directory per podcast. Each show keeps its own config, metadata, docs, and generated feeds (for example `shows/social-psychology/`).
- `requirements.txt` – Python dependencies needed locally and in CI.

### MIME type filtering
Each show config can optionally supply `"allowed_mime_types"` to control which Google Drive items should become feed entries. Values ending with `/` are treated as prefixes (for example `"audio/"`), while exact MIME types (such as `"video/mp4"`) match specific files. The default behaviour includes only audio files, so add types like `"video/mp4"` if you want lecture videos to appear in the feed without manual conversion.

### Automatic Drive transcoding
`podcast-tools/transcode_drive_media.py` converts matching Drive videos to audio before the feed build runs. Provide a `transcode` block in each show config to opt in:

```json
"transcode": {
  "enabled": true,
  "source_mime_types": ["video/mp4"],
  "target_extension": "mp3",
  "target_mime_type": "audio/mpeg",
  "codec": "libmp3lame",
  "bitrate": "160k"
}
```

The workflow installs `ffmpeg`, downloads each video, transcodes it locally, and uploads the audio back into the original Drive file (updating its name, MIME type, and content). Because the conversion happens in place, no additional storage quota is required and the feed generator only ever sees audio assets.

### Automatic dating from the teaching schedule
Shows can point `auto_spec` at a JSON file that maps Drive folder labels to calendar weeks. The Socialpsykologi Deep Dives - Hold 1 - 2025 show ships with `shows/social-psychology/auto_spec.json`, generated from the teaching plan PDF. Each rule ties folder names like `W4 The Self` (anything that contains `w4`) to ISO week 39 of 2025 and sets a Monday 10:00 CET release, spacing additional recordings for that week by 120 minutes. Future recordings dropped into the matching `W*` folders automatically inherit the correct `published_at` timestamp without editing `episode_metadata.json`.

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

The repository ships with `podcast/config.json` and `podcast/episode_metadata.json` pre-populated for Socialpsykologi Deep Dives - Hold 1 - 2025—update the titles, artwork, contact email, and descriptions to match your own show before publishing.

## Configure GitHub Actions
1. Create two repository secrets:
   - `GOOGLE_SERVICE_ACCOUNT_JSON` – paste the entire JSON key exactly as downloaded (no extra quoting or base64).
   - `DRIVE_FOLDER_ID` – the folder ID from the Google Drive URL.
2. Edit `podcast/config.github.json` with your show metadata. Leave `service_account_file` untouched; the workflow writes the key to that path at runtime. Add a real `podcast/episode_metadata.json` if you want to control titles, descriptions, publish dates, durations, and artwork per episode.
3. (Optional) Commit your custom `podcast/episode_metadata.json`.

To kick off a build manually, go to **Actions → Generate Podcast Feed → Run workflow**. The job also runs every day at 06:00 UTC via cron.

## Drive-triggered rebuilds (Google Apps Script)
If you want the GitHub workflow to fire whenever fresh audio appears in Drive, add a lightweight Apps Script that polls the folder and calls the `Generate Podcast Feed` workflow via `workflow_dispatch`.

1. Visit [script.google.com](https://script.google.com/), create a new project, and paste the helper script below into `Code.gs`. Update the `CONFIG.github` block if you fork the repository or rename the workflow file.
2. In the left toolbar, open **Services** (puzzle icon) and enable the **Drive API** advanced service. If Apps Script prompts you to enable the API in Google Cloud, follow the link and flip it on there as well.
3. In **Project Settings → Script properties** add a property whose key matches `CONFIG.github.tokenProperty` (`GITHUB_PAT` by default) and set its value to a GitHub personal access token with the `repo` and `workflow` scopes.
4. Back in the editor, run `initializeDriveChangeState()` once to capture the current Drive snapshot and seed the change log token.
5. Run `checkDriveAndTrigger()` manually to accept the Drive + external API scopes and confirm the workflow dispatch.
6. Open the clock icon (**Triggers**) → **Add trigger**, select `checkDriveAndTrigger`, choose a time-driven interval (for example every 15 minutes), and save.

The repository keeps this helper at `apps-script/drive_change_trigger.gs` so you can copy/paste the latest version straight into Apps Script without hunting through the docs.

### Apps Script helper
```javascript
/**
 * Polls the Drive change log for the podcast folder and triggers the
 * ennuiweb/psyk-podcast GitHub Actions workflow via workflow_dispatch
 * whenever a tracked file is added, removed, renamed, moved, or updated.
 */
const CONFIG = {
  drive: {
    folderId: '1uPt6bHjivcD9z-Tw6Q2xbIld3bmH_WyI',
    includeSubfolders: true,
    mimePrefixes: ['audio/'], // Set to [] to react to every file type.
    sharedDriveId: null,      // Leave null for shared folders in "My Drive".
  },
  github: {
    owner: 'ennuiweb',
    repo: 'psyk-podcast',
    workflowFile: 'generate-feed.yml',
    ref: 'main',
    inputs: {},
    tokenProperty: 'GITHUB_PAT',
  },
  state: {
    pageTokenKey: 'DRIVE_CHANGES_PAGE_TOKEN',
    fileIdsKey: 'KNOWN_DRIVE_FILE_IDS',
    folderIdsKey: 'KNOWN_DRIVE_FOLDER_IDS',
  },
};

function checkDriveAndTrigger() {
  const props = PropertiesService.getScriptProperties();
  const currentToken = props.getProperty(CONFIG.state.pageTokenKey);
  if (!currentToken) {
    throw new Error('Run initializeDriveChangeState() before scheduling triggers.');
  }

  const knownFileIds = new Set(JSON.parse(props.getProperty(CONFIG.state.fileIdsKey) || '[]'));
  const knownFolderIds = new Set(JSON.parse(props.getProperty(CONFIG.state.folderIdsKey) || '[]'));
  knownFolderIds.add(CONFIG.drive.folderId);

  let changesApplied = false;
  let pageToken = currentToken;
  let latestStartToken = currentToken;
  const folderAncestryCache = new Map();

  do {
    const response = Drive.Changes.list(buildChangeQuery(pageToken));
    const changes = response.changes || [];

    changes.forEach((change) => {
      const fileId = change.fileId;
      const file = change.file;
      const wasKnown = knownFileIds.has(fileId);
      const wasFolder = knownFolderIds.has(fileId);
      const isRemoval = change.removed || (file && file.trashed);

      if (isRemoval) {
        if (wasKnown) {
          knownFileIds.delete(fileId);
          changesApplied = true;
        }
        if (wasFolder && fileId !== CONFIG.drive.folderId) {
          knownFolderIds.delete(fileId);
          changesApplied = true;
        }
        return;
      }

      if (!file) return;

      const isFolder = file.mimeType === 'application/vnd.google-apps.folder';
      const isInside = isWithinWatchedTree(file.parents || [], knownFolderIds, folderAncestryCache);

      if (isFolder) {
        if (isInside) {
          if (!knownFolderIds.has(fileId)) {
            knownFolderIds.add(fileId);
            changesApplied = true;
          }
        } else if (knownFolderIds.delete(fileId)) {
          changesApplied = true;
        }
        return;
      }

      if (!matchesMimeType(file.mimeType)) {
        if (wasKnown) {
          knownFileIds.delete(fileId);
          changesApplied = true;
        }
        return;
      }

      if (isInside) {
        if (!wasKnown) {
          knownFileIds.add(fileId);
        }
        changesApplied = true;
      } else if (wasKnown) {
        knownFileIds.delete(fileId);
        changesApplied = true;
      }
    });

    pageToken = response.nextPageToken;
    if (!pageToken && response.newStartPageToken) {
      latestStartToken = response.newStartPageToken;
    }
  } while (pageToken);

  props.setProperty(CONFIG.state.pageTokenKey, latestStartToken);
  props.setProperty(CONFIG.state.fileIdsKey, JSON.stringify([...knownFileIds]));
  props.setProperty(CONFIG.state.folderIdsKey, JSON.stringify([...knownFolderIds]));

  if (changesApplied) {
    triggerGithubWorkflow();
  }
}

function initializeDriveChangeState() {
  const props = PropertiesService.getScriptProperties();
  const startToken = Drive.Changes.getStartPageToken(buildStartTokenQuery()).startPageToken;
  const snapshot = snapshotCurrentTree();

  props.setProperties({
    [CONFIG.state.pageTokenKey]: startToken,
    [CONFIG.state.fileIdsKey]: JSON.stringify(snapshot.fileIds),
    [CONFIG.state.folderIdsKey]: JSON.stringify(snapshot.folderIds),
  }, true);
}

function buildChangeQuery(pageToken) {
  const query = {
    pageToken,
    includeRemoved: true,
    includeItemsFromAllDrives: true,
    supportsAllDrives: true,
    spaces: 'drive',
    pageSize: 100,
    fields: 'nextPageToken,newStartPageToken,changes(fileId,removed,file(id,name,mimeType,parents,trashed)))',
  };

  if (CONFIG.drive.sharedDriveId) {
    query.driveId = CONFIG.drive.sharedDriveId;
    query.corpora = 'drive';
  } else {
    query.restrictToMyDrive = true;
  }

  return query;
}

function buildStartTokenQuery() {
  const query = { supportsAllDrives: true };
  if (CONFIG.drive.sharedDriveId) {
    query.driveId = CONFIG.drive.sharedDriveId;
  }
  return query;
}

function snapshotCurrentTree() {
  const folderIds = new Set([CONFIG.drive.folderId]);
  const fileIds = new Set();

  if (CONFIG.drive.includeSubfolders) {
    const queue = [CONFIG.drive.folderId];
    while (queue.length) {
      const head = queue.shift();
      listChildren(head).forEach((item) => {
        if (item.mimeType === 'application/vnd.google-apps.folder') {
          if (!folderIds.has(item.id)) {
            folderIds.add(item.id);
            queue.push(item.id);
          }
        } else if (matchesMimeType(item.mimeType)) {
          fileIds.add(item.id);
        }
      });
    }
  } else {
    listChildren(CONFIG.drive.folderId).forEach((item) => {
      if (item.mimeType === 'application/vnd.google-apps.folder') return;
      if (matchesMimeType(item.mimeType)) fileIds.add(item.id);
    });
  }

  return {
    folderIds: [...folderIds],
    fileIds: [...fileIds],
  };
}

function listChildren(parentId) {
  const items = [];
  let pageToken;
  do {
    const request = {
      q: `'${parentId}' in parents and trashed = false`,
      includeItemsFromAllDrives: true,
      supportsAllDrives: true,
      pageSize: 100,
      fields: 'files(id,mimeType),nextPageToken',
      pageToken,
    };

    if (CONFIG.drive.sharedDriveId) {
      request.driveId = CONFIG.drive.sharedDriveId;
      request.corpora = 'drive';
    }

    const response = Drive.Files.list(request);
    (response.files || []).forEach((item) => items.push(item));
    pageToken = response.nextPageToken;
  } while (pageToken);

  return items;
}

function matchesMimeType(mimeType) {
  const prefixes = CONFIG.drive.mimePrefixes || [];
  if (!prefixes.length) return true;
  return prefixes.some((prefix) => {
    if (prefix.endsWith('/')) return mimeType.startsWith(prefix);
    return mimeType === prefix;
  });
}

function isWithinWatchedTree(parentIds, knownFolderIds, cache) {
  for (const parentId of parentIds) {
    if (parentId === CONFIG.drive.folderId) return true;
    if (knownFolderIds.has(parentId)) return true;
    if (cache.has(parentId)) {
      if (cache.get(parentId)) {
        knownFolderIds.add(parentId);
        return true;
      }
      continue;
    }

    const parent = Drive.Files.get(parentId, {
      fields: 'id,mimeType,parents',
      supportsAllDrives: true,
    });

    const isFolder = parent.mimeType === 'application/vnd.google-apps.folder';
    const result = isFolder && parent.parents
      ? isWithinWatchedTree(parent.parents, knownFolderIds, cache)
      : false;

    cache.set(parentId, result);
    if (result) {
      knownFolderIds.add(parentId);
      return true;
    }
  }
  return false;
}

function triggerGithubWorkflow() {
  const token = PropertiesService.getScriptProperties()
    .getProperty(CONFIG.github.tokenProperty);
  if (!token) throw new Error('GitHub token missing; add script property.');

  const url = `https://api.github.com/repos/${CONFIG.github.owner}/${CONFIG.github.repo}`
    + `/actions/workflows/${CONFIG.github.workflowFile}/dispatches`;

  const payload = {
    ref: CONFIG.github.ref,
    inputs: CONFIG.github.inputs || {},
  };

  const response = UrlFetchApp.fetch(url, {
    method: 'post',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'User-Agent': 'AppsScript-GH-Trigger',
    },
    muteHttpExceptions: false,
    contentType: 'application/json',
    payload: JSON.stringify(payload),
  });

  if (response.getResponseCode() !== 204) {
    throw new Error(`GitHub dispatch failed: ${response.getContentText()}`);
  }
}
```

Adjust the script if you run the workflow from a different branch or need to pass `workflow_dispatch` inputs—set them inside `CONFIG.github.inputs`.

The helper stores its Drive state in script properties (`CONFIG.state.*`) so it can detect renames, moves, deletions, and permission flips as well as new uploads. Re-run `initializeDriveChangeState()` if you swap to a new Drive folder or manually clear the stored properties. Set `CONFIG.drive.mimePrefixes` to `[]` when you want to trigger on every file type instead of only audio.


### Using shared drives
- In your show config (`shows/.../config.json`), keep `shared_drive_id` set to the shared drive's ID and leave `include_items_from_all_drives` enabled so the generator can enumerate everything.
- Update the Apps Script helper by setting `CONFIG.drive.sharedDriveId` to the same ID; the change poller will stay scoped to that drive automatically.
- Grant the service account at least Viewer access on the shared drive itself (Sharing → Manage members). Sharing only a subfolder is not sufficient.
- Leave `CONFIG.drive.includeSubfolders` enabled when you expect nested week folders—the helper will walk them and track newly created subfolders.
- Set `skip_permission_updates` to `true` in the show config if your service account cannot modify sharing; flip it back once access is restored so new uploads become public automatically.

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
