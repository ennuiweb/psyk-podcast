/**
 * Polls the Drive change log for the podcast folder and triggers the
 * ennuiweb/psyk-podcast GitHub Actions workflow via workflow_dispatch
 * whenever a tracked file is added, removed, renamed, moved, or updated.
 *
 * Before first run:
 * 1. Update CONFIG as needed.
 * 2. In Extensions → Apps Script → Services, enable the Drive API advanced service
 *    (and enable the API in Google Cloud if prompted).
 * 3. In Project Settings → Script properties, add CONFIG.github.tokenProperty
 *    (default: GITHUB_PAT) with a PAT that carries repo + workflow scopes.
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

  let pageToken = currentToken;
  let latestStartToken = currentToken;
  let changesApplied = false;
  const folderCache = new Map();

  do {
    const response = Drive.Changes.list(buildChangeQuery(pageToken));
    const changes = response.changes || [];

    changes.forEach((change) => {
      const fileId = change.fileId;
      const file = change.file;
      const wasKnownFile = knownFileIds.has(fileId);
      const wasKnownFolder = knownFolderIds.has(fileId);
      const isRemoval = change.removed || (file && file.trashed);

      if (isRemoval) {
        if (wasKnownFile) {
          knownFileIds.delete(fileId);
          changesApplied = true;
        }
        if (wasKnownFolder && fileId !== CONFIG.drive.folderId) {
          knownFolderIds.delete(fileId);
          changesApplied = true;
        }
        return;
      }

      if (!file) return;

      if (file.mimeType === 'application/vnd.google-apps.folder') {
        const insideTree = isWithinWatchedTree(file.parents || [], knownFolderIds, folderCache);
        if (insideTree && !knownFolderIds.has(fileId)) {
          knownFolderIds.add(fileId);
          changesApplied = true;
        } else if (!insideTree && knownFolderIds.delete(fileId)) {
          changesApplied = true;
        }
        return;
      }

      if (!matchesMimeType(file.mimeType)) {
        if (wasKnownFile) {
          knownFileIds.delete(fileId);
          changesApplied = true;
        }
        return;
      }

      const insideTree = isWithinWatchedTree(file.parents || [], knownFolderIds, folderCache);
      if (insideTree) {
        if (!wasKnownFile) knownFileIds.add(fileId);
        changesApplied = true;
      } else if (wasKnownFile) {
        knownFileIds.delete(fileId);
        changesApplied = true;
      }
    });

    pageToken = response.nextPageToken || null;
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
    fields: 'nextPageToken,newStartPageToken,changes(fileId,removed,file(id,mimeType,parents,trashed)))',
  };

  if (CONFIG.drive.sharedDriveId) {
    query.driveId = CONFIG.drive.sharedDriveId;
    query.corpora = 'drive';
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
      if (item.mimeType !== 'application/vnd.google-apps.folder' && matchesMimeType(item.mimeType)) {
        fileIds.add(item.id);
      }
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
    if (parentId === CONFIG.drive.folderId || knownFolderIds.has(parentId)) {
      return true;
    }
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
