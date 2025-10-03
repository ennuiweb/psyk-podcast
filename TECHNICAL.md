# psyk-podcast · [RSS feed](https://raw.githubusercontent.com/ennuiweb/psyk-podcast/main/shows/social-psychology/feeds/rss.xml)

Automation to build podcast RSS feeds from audio files stored in Google Drive. The current show (`shows/social-psychology`) regenerates `shows/social-psychology/feeds/rss.xml` automatically via GitHub Actions, and the structure is ready for additional shows later on.

## Repository layout
- `podcast-tools/gdrive_podcast_feed.py` – shared generator script used by every show.
- `shows/` – one directory per podcast. Each show keeps its own config, metadata, docs, and generated feeds (for example `shows/social-psychology/`).
  - `shows/intro-vt/` ships as scaffolding for the "Intro + VT" series—copy the templates inside when you are ready to wire the feed up.
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
4. Back in the editor, run `initializeDriveChangeState()` once to capture the current Drive snapshot and seed the manifest used for comparisons.
5. Run `checkDriveAndTrigger()` manually to accept the Drive + external API scopes and confirm the workflow dispatch.
6. Open the clock icon (**Triggers**) → **Add trigger**, select `checkDriveAndTrigger`, choose a time-driven interval (for example every 15 minutes), and save.

The repository keeps this helper at `apps-script/drive_change_trigger.gs` so you can copy/paste the latest version straight into Apps Script without hunting through the docs.

### Apps Script helper
```javascript
/**
 * Polls Google Drive for changes inside the podcast folder and dispatches
 * the ennuiweb/psyk-podcast GitHub Actions workflow when files are added,
 * removed, renamed, moved, or otherwise updated.
 *
 * Before first run:
 * 1. Update CONFIG as needed.
 * 2. In Extensions → Apps Script → Services, enable the Drive API advanced service
 *    (enable the API in Google Cloud if prompted).
 * 3. In Project Settings → Script properties, store CONFIG.github.tokenProperty
 *    (default: GITHUB_PAT) with a PAT that has repo + workflow scopes.
 * 4. Run initializeDriveChangeState() once to capture the current Drive snapshot.
 * 5. Run checkDriveAndTrigger() manually to grant scopes.
 * 6. Create a time-driven trigger for checkDriveAndTrigger().
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
    snapshotKey: 'DRIVE_TREE_SNAPSHOT',
  },
};

const FOLDER_MIME = 'application/vnd.google-apps.folder';

function checkDriveAndTrigger() {
  const props = PropertiesService.getScriptProperties();
  const rawSnapshot = props.getProperty(CONFIG.state.snapshotKey);
  if (!rawSnapshot) {
    throw new Error('Run initializeDriveChangeState() before scheduling triggers.');
  }

  const previousSnapshot = JSON.parse(rawSnapshot);
  const currentSnapshot = snapshotCurrentTree();

  const diff = detectChanges(previousSnapshot, currentSnapshot);

  props.setProperty(CONFIG.state.snapshotKey, JSON.stringify(currentSnapshot));

  if (diff.hasChanges) {
    logDriveDiff(diff);
    triggerGithubWorkflow();
  } else {
    console.log('No Drive changes detected; skipping workflow dispatch.');
  }
}

function initializeDriveChangeState() {
  const snapshot = snapshotCurrentTree();
  PropertiesService.getScriptProperties().setProperty(
    CONFIG.state.snapshotKey,
    JSON.stringify(snapshot),
  );
}

function detectChanges(previous, current) {
  const prevSnapshot = previous || { folders: {}, files: {} };
  const currSnapshot = current || { folders: {}, files: {} };

  const folderChanges = diffRecordSets(prevSnapshot.folders || {}, currSnapshot.folders || {});
  const fileChanges = diffRecordSets(prevSnapshot.files || {}, currSnapshot.files || {});

  const hasChanges = hasAnyChanges(folderChanges) || hasAnyChanges(fileChanges);

  return {
    hasChanges,
    folders: folderChanges,
    files: fileChanges,
  };
}

function metadataEqual(a, b) {
  if (a.name !== b.name) return false;
  if (a.mimeType !== b.mimeType) return false;
  if (a.modifiedTime !== b.modifiedTime) return false;
  if (a.parents.length !== b.parents.length) return false;
  for (let i = 0; i < a.parents.length; i++) {
    if (a.parents[i] !== b.parents[i]) return false;
  }
  return true;
}

function diffRecordSets(previous, current) {
  const added = [];
  const removed = [];
  const updated = [];

  Object.keys(current).forEach((id) => {
    const currMeta = current[id];
    const prevMeta = previous[id];
    if (!prevMeta) {
      added.push(currMeta);
    } else if (!metadataEqual(prevMeta, currMeta)) {
      updated.push({ before: prevMeta, after: currMeta });
    }
  });

  Object.keys(previous).forEach((id) => {
    if (!current[id]) {
      removed.push(previous[id]);
    }
  });

  return { added, removed, updated };
}

function hasAnyChanges(group) {
  return Boolean(group.added.length || group.removed.length || group.updated.length);
}

function logDriveDiff(diff) {
  logChangeGroup('Folder', diff.folders);
  logChangeGroup('File', diff.files);
}

function logChangeGroup(label, group) {
  group.added.forEach((meta) => {
    console.log(`[${label} Added] ${meta.name} (${meta.id}) parents=${formatParents(meta.parents)}`);
  });

  group.removed.forEach((meta) => {
    console.log(`[${label} Removed] ${meta.name} (${meta.id}) parents=${formatParents(meta.parents)}`);
  });

  group.updated.forEach(({ before, after }) => {
    const deltas = describeMetadataDelta(before, after);
    console.log(`[${label} Updated] ${after.name} (${after.id}): ${deltas.join('; ')}`);
  });
}

function describeMetadataDelta(before, after) {
  const changes = [];
  if (before.name !== after.name) {
    changes.push(`name '${before.name}' → '${after.name}'`);
  }
  if (before.mimeType !== after.mimeType) {
    changes.push(`mime '${before.mimeType}' → '${after.mimeType}'`);
  }
  if (before.modifiedTime !== after.modifiedTime) {
    changes.push(`modified ${before.modifiedTime} → ${after.modifiedTime}`);
  }
  if (!arraysEqual(before.parents, after.parents)) {
    changes.push(`parents '${formatParents(before.parents)}' → '${formatParents(after.parents)}'`);
  }
  return changes.length ? changes : ['metadata changed'];
}

function arraysEqual(a, b) {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

function formatParents(parents) {
  const list = Array.isArray(parents) && parents.length ? parents : ['—'];
  return list.join(', ');
}

function snapshotCurrentTree() {
  const folders = {};
  const files = {};
  const seenFolderIds = new Set();
  const queue = [];

  const rootMeta = getFileMetadata(CONFIG.drive.folderId);
  folders[rootMeta.id] = rootMeta;
  seenFolderIds.add(rootMeta.id);
  queue.push(rootMeta.id);

  while (queue.length) {
    const parentId = queue.shift();
    const children = listChildren(parentId);

    children.forEach((item) => {
      if (item.mimeType === FOLDER_MIME) {
        if (!seenFolderIds.has(item.id)) {
          folders[item.id] = item;
          seenFolderIds.add(item.id);
          if (CONFIG.drive.includeSubfolders) {
            queue.push(item.id);
          }
        } else if (!metadataEqual(folders[item.id], item)) {
          folders[item.id] = item;
        }
        return;
      }

      if (!matchesMimeType(item.mimeType)) return;
      files[item.id] = item;
    });
  }

  return {
    folders,
    files,
  };
}

function listChildren(parentId) {
  const items = [];
  let pageToken;
  do {
    const params = {
      q: `'${parentId}' in parents and trashed = false`,
      fields: 'files(id,name,mimeType,parents,modifiedTime),nextPageToken',
      pageSize: 100,
      pageToken,
    };

    if (CONFIG.drive.sharedDriveId) {
      params.includeItemsFromAllDrives = true;
      params.supportsAllDrives = true;
      params.driveId = CONFIG.drive.sharedDriveId;
      params.corpora = 'drive';
    }

    const response = Drive.Files.list(params);
    (response.files || []).forEach((item) => {
      item.parents = normaliseParents(item.parents);
      items.push(item);
    });
    pageToken = response.nextPageToken;
  } while (pageToken);

  return items;
}

function getFileMetadata(fileId) {
  const params = {
    fields: 'id,name,mimeType,parents,modifiedTime',
    supportsAllDrives: Boolean(CONFIG.drive.sharedDriveId),
  };
  const file = Drive.Files.get(fileId, params);
  file.parents = normaliseParents(file.parents);
  return file;
}

function normaliseParents(parents) {
  const list = parents ? parents.slice() : [];
  list.sort();
  return list;
}

function matchesMimeType(mimeType) {
  const prefixes = CONFIG.drive.mimePrefixes || [];
  if (!prefixes.length) return true;
  return prefixes.some((prefix) => {
    if (prefix.endsWith('/')) return mimeType.startsWith(prefix);
    return mimeType === prefix;
  });
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

The helper keeps a manifest (`CONFIG.state.snapshotKey`) of every tracked folder and audio file. Each run re-snapshots the Drive tree, compares metadata (name, parents, MIME type, modified time), logs the diff, and fires the workflow when anything differs—covering moves, renames, deletions, or new uploads. Re-run `initializeDriveChangeState()` if you swap to a new Drive folder or manually clear the stored properties. Set `CONFIG.drive.mimePrefixes` to `[]` when you want every file type to trigger a rebuild instead of only audio.
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
