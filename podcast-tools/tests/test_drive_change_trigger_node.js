const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const SCRIPT_PATH = path.join(__dirname, '..', '..', 'apps-script', 'drive_change_trigger.gs');
const SCRIPT_SOURCE = fs.readFileSync(SCRIPT_PATH, 'utf8');

function loadHarness(overrides = {}) {
  const sleeps = [];
  const warnings = [];

  const sandbox = {
    console: {
      log() {},
      warn(message) {
        warnings.push(message);
      },
    },
    Drive: {
      Files: {
        list: overrides.list || (() => ({ items: [], nextPageToken: null })),
        get: overrides.get || ((fileId) => ({
          id: fileId,
          title: 'Root',
          mimeType: 'application/vnd.google-apps.folder',
          parents: [],
          modifiedDate: '2026-01-01T00:00:00.000Z',
        })),
      },
    },
    PropertiesService: {
      getScriptProperties() {
        return {
          getProperty() {
            return null;
          },
          setProperty() {},
        };
      },
    },
    UrlFetchApp: {
      fetch() {
        return {
          getResponseCode() {
            return 204;
          },
          getContentText() {
            return '';
          },
        };
      },
    },
    Utilities: {
      sleep(ms) {
        sleeps.push(ms);
      },
    },
    Math: Object.assign(Object.create(Math), { random: () => 0 }),
    JSON,
    Set,
    Array,
    String,
    Number,
    Boolean,
    Error,
    Date,
  };

  const context = vm.createContext(sandbox);
  new vm.Script(SCRIPT_SOURCE, { filename: 'drive_change_trigger.gs' }).runInContext(context);
  return { context, sleeps, warnings };
}

test('marks known transient Drive API failures as retryable', () => {
  const { context } = loadHarness();

  assert.equal(
    context.isRetryableDriveError(
      new Error('Exception: API call to drive.files.list failed with error: Empty response'),
    ),
    true,
  );
  assert.equal(
    context.isRetryableDriveError(
      new Error('GoogleJsonResponseException: API call to drive.files.list failed with error: Internal Error'),
    ),
    true,
  );
  assert.equal(
    context.isRetryableDriveError(
      new Error('GoogleJsonResponseException: API call to drive.files.list failed with error: File not found'),
    ),
    false,
  );
});

test('listChildren retries transient Drive failures and succeeds', () => {
  let attempts = 0;
  const { context, sleeps, warnings } = loadHarness({
    list() {
      attempts += 1;
      if (attempts < 3) {
        throw new Error(
          'GoogleJsonResponseException: API call to drive.files.list failed with error: Internal Error',
        );
      }
      return {
        items: [
          {
            id: 'file-1',
            title: 'Episode 1',
            mimeType: 'audio/mpeg',
            parents: [{ id: 'folder-123' }],
            modifiedDate: '2026-01-01T00:00:00.000Z',
          },
        ],
        nextPageToken: null,
      };
    },
  });

  new vm.Script('CONFIG.drive.apiMaxAttempts = 4;').runInContext(context);
  const children = JSON.parse(JSON.stringify(context.listChildren('folder-123')));

  assert.equal(attempts, 3);
  assert.deepEqual(sleeps, [1000, 2000]);
  assert.equal(warnings.length, 2);
  assert.deepEqual(children, [
    {
      id: 'file-1',
      name: 'Episode 1',
      mimeType: 'audio/mpeg',
      parents: ['folder-123'],
      modifiedTime: '2026-01-01T00:00:00.000Z',
      title: 'Episode 1',
      modifiedDate: '2026-01-01T00:00:00.000Z',
    },
  ]);
});

test('listChildren does not retry non-transient Drive failures', () => {
  let attempts = 0;
  const { context, sleeps } = loadHarness({
    list() {
      attempts += 1;
      throw new Error(
        'GoogleJsonResponseException: API call to drive.files.list failed with error: File not found',
      );
    },
  });

  assert.throws(
    () => context.listChildren('folder-404'),
    /Drive\.Files\.list for folder folder-404 failed after 1 attempt\(s\): .*File not found/,
  );
  assert.equal(attempts, 1);
  assert.deepEqual(sleeps, []);
});

test('checkDriveAndTrigger skips unavailable roots without creating false removals', () => {
  let storedSnapshot;
  const dispatched = [];
  const { context, warnings } = loadHarness({
    get(fileId) {
      if (fileId === '1hZDV24e4V4ygo_Ye30zzRwInkgIyfgzi') {
        throw new Error(
          'GoogleJsonResponseException: API call to drive.files.get failed with error: File not found: 1hZDV24e4V4ygo_Ye30zzRwInkgIyfgzi',
        );
      }
      return {
        id: fileId,
        title: `Root ${fileId}`,
        mimeType: 'application/vnd.google-apps.folder',
        parents: [],
        modifiedDate: '2026-01-01T00:00:00.000Z',
      };
    },
  });
  new vm.Script(
    "CONFIG.drive.folderIds = ['1hZDV24e4V4ygo_Ye30zzRwInkgIyfgzi'];",
  ).runInContext(context);

  const previousSnapshot = {
    folders: {
      '1hZDV24e4V4ygo_Ye30zzRwInkgIyfgzi': {
        id: '1hZDV24e4V4ygo_Ye30zzRwInkgIyfgzi',
        name: 'bioneuro',
        mimeType: 'application/vnd.google-apps.folder',
        parents: [],
        modifiedTime: '2026-01-01T00:00:00.000Z',
      },
    },
    files: {
      'episode-1': {
        id: 'episode-1',
        name: 'Episode 1.mp3',
        mimeType: 'audio/mpeg',
        parents: ['1hZDV24e4V4ygo_Ye30zzRwInkgIyfgzi'],
        modifiedTime: '2026-01-01T00:00:00.000Z',
      },
    },
  };

  context.PropertiesService.getScriptProperties = () => ({
    getProperty() {
      return JSON.stringify(previousSnapshot);
    },
    setProperty(key, value) {
      storedSnapshot = { key, value: JSON.parse(value) };
    },
  });

  context.UrlFetchApp.fetch = () => {
    dispatched.push(true);
    return {
      getResponseCode() {
        return 204;
      },
      getContentText() {
        return '';
      },
    };
  };

  context.checkDriveAndTrigger();

  assert.equal(dispatched.length, 0);
  assert.ok(storedSnapshot);
  assert.equal(storedSnapshot.key, 'DRIVE_TREE_SNAPSHOT');
  assert.deepEqual(storedSnapshot.value.unavailableRootIds, ['1hZDV24e4V4ygo_Ye30zzRwInkgIyfgzi']);
  assert.equal(
    warnings.some((message) => message.includes('[Drive Root Skipped] 1hZDV24e4V4ygo_Ye30zzRwInkgIyfgzi')),
    true,
  );
});
