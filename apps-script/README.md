# Apps Script Sync

Use `push_drive_trigger.sh` to push `drive_change_trigger.gs` + `appsscript.json` with `clasp`.
The current helper retries transient Drive API failures like `Internal Error` and `Empty response` before it lets the trigger fail.

## Setup

1. Install `clasp` (`npm install -g @google/clasp`) or use `npx @google/clasp`.
2. Run `clasp login`.
3. Copy `.clasp.json.example` to `.clasp.json` and set `scriptId`.

## Commands

- One-shot push: `apps-script/push_drive_trigger.sh`
- Watch mode: `apps-script/push_drive_trigger.sh --watch`

## Environment Variables

- `APPS_SCRIPT_PUSH_MODE`
  - `best-effort` (default): warns and exits `0` on missing local setup/tooling/push errors.
  - `required`: exits non-zero for those failures.
  - `off`: skip push and exit `0`.
- `APPS_SCRIPT_CLASP_JSON`
  - Optional explicit path to a `.clasp.json` project file.
  - Relative paths are resolved from the current working directory.

When run inside a git worktree, the script searches for `.clasp.json` in this order:
1. `APPS_SCRIPT_CLASP_JSON` (if set)
2. current worktree `apps-script/.clasp.json`
3. shared main-checkout `apps-script/.clasp.json` resolved via `git rev-parse --git-common-dir`
