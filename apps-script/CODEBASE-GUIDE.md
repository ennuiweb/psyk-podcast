# Apps Script Codebase Guide
This guide is for coding LLMs working in `apps-script/`.
This is a very small subsystem.
It is operational glue, not a core runtime branch.

## 1. Business purpose
This directory contains a Google Apps Script used to poll Drive folders and trigger a GitHub Actions workflow when files change.

Historically, this supported Drive-backed publication workflows.
Today, the active show surface has retired that trigger path, but the code still exists for legacy or future reactivation.

## 2. Directory structure
Important files:
- `README.md`
- `drive_change_trigger.gs`

That is effectively the whole subsystem.

## 3. Operational status
The current config intentionally keeps the active folder list empty.
This means the script is effectively dormant unless explicitly re-enabled.

Snippet:
```javascript
// apps-script/drive_change_trigger.gs
folderIds: [
  // Drive-triggered publication is retired for the active show surface.
  // Leave this empty unless a legacy Drive-backed show is explicitly re-enabled.
],
```

This comment is real policy, not decorative commentary.

## 4. What the script actually does
Source: `apps-script/drive_change_trigger.gs`

Core responsibilities:
- read configured root folder IDs
- snapshot Drive tree state
- diff old and new snapshots
- if changed, dispatch GitHub workflow
- persist the new snapshot in script properties

## 5. Important functions
Key functions to inspect:
- `configuredRootFolderIds()`
- `checkDriveAndTrigger()`
- `initializeDriveChangeState()`
- `detectChanges(...)`
- `snapshotCurrentTree()`
- `triggerGithubWorkflow()`

These are the real control flow.

## 6. Why this subsystem still matters
Even though it is retired for active shows, it documents an important legacy integration contract:
- Drive tree polling
- GitHub workflow dispatch
- script property state
- shared-drive edge handling

If a user wants to revive Drive-triggered publication, this is where that behavior lives.

## 7. README role
Source: `apps-script/README.md`

This README explains:
- `clasp` usage
- script push workflow
- supporting shell helpers
- deployment expectations

Because the subsystem is so small, the README is part of the runtime context.

## 8. Non-idiomatic traits
- state is stored in Apps Script properties
- diffing is custom tree snapshot logic
- GitHub workflow dispatch is direct API glue
- configuration is embedded in the script itself

This is acceptable for the scale of this subsystem, but it means there is no abstraction layer to hide mistakes.

## 9. Safe change strategy
When changing this subsystem:
1. confirm whether the trigger path is actually intended to be active
2. preserve snapshot compatibility unless resetting state is acceptable
3. test folder diff logic mentally for add/remove/rename/move cases
4. remember that dormant code still needs clear operator behavior

If you are unsure where to start, start with `README.md`, then `drive_change_trigger.gs`.

