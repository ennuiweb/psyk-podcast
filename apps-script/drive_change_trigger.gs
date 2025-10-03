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
