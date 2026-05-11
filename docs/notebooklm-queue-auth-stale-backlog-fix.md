# NotebookLM Queue Auth-Stale Backlog Fix

Last updated: 2026-05-11

This note documents the fix for the queue stall where one stale-auth lecture
could stop the rest of a show's timed backlog from draining.

## Problem

During the `personlighedspsykologi-en` prompt-version rollout, the queue had
ample time to continue processing, but the live worker still stalled. The
immediate trigger was an auth-stale lecture (`W12L1`) that remained in
`failed_retryable` after repeated NotebookLM auth failures on the remaining
usable profiles.

The real defect was not just upstream NotebookLM auth:

- execution and alerting used different error classification logic
- auth-stale failures were left in the ambiguous `failed_retryable` state
- `serve-show` treated mixed blocked + timed backlog as a fatal stop condition
- the CLI returned a nonzero exit code for that condition, so `systemd`
  recorded the worker as failed instead of letting timed backlog continue

That meant one bad lecture could stall unrelated `retry_scheduled` and
`waiting_for_artifact` jobs for the same show.

## Fix Design

The durable fix is to make failure handling explicit and shared:

1. Use one shared failure classifier for queue execution and alerts.
2. Represent stale NotebookLM auth as its own blocked state:
   `blocked_auth_stale`.
3. Keep timed retries (`retry_scheduled`) separate from operator-owned
   blockers.
4. Let `serve-show` continue draining timed backlog even when blocked jobs are
   present.
5. Exit cleanly with `blocked_backlog_remaining` only when blocked jobs are the
   sole remaining work.

## Implemented Changes

- Added `notebooklm_queue/failure_modes.py` as the shared source of truth for:
  - auth-stale detection
  - rate-limit detection
  - profile-cooldown detection
  - transient NotebookLM RPC/source-ingestion detection
- Added `STATE_BLOCKED_AUTH_STALE` to
  `notebooklm_queue/constants.py`.
- Updated `notebooklm_queue/execution.py` so:
  - new auth-stale failures finalize to `blocked_auth_stale`
  - legacy `failed_retryable` auth jobs are repaired into
    `blocked_auth_stale`
  - timed retry classes still become `retry_scheduled`
- Updated `notebooklm_queue/alerts.py` to use the same shared classifier as
  execution, so alerts and runtime state cannot drift.
- Updated `notebooklm_queue/orchestrator.py` so mixed blocked + timed backlog
  no longer stops the whole worker.
- Updated `notebooklm_queue/cli.py` so `serve-show` returns success for
  `blocked_backlog_remaining` and reserves nonzero exit codes for actual queue
  orchestration failures.

## Operator Contract

Expected behavior after this fix:

- If NotebookLM quota, cooldown, or transient RPC issues occur, the job moves
  to `retry_scheduled` and the worker keeps waiting/draining automatically.
- If NotebookLM auth is stale, the affected lecture moves to
  `blocked_auth_stale`.
- While any timed backlog still exists, `serve-show` keeps draining it.
- When only blocked backlog remains, `serve-show` exits with
  `blocked_backlog_remaining` and a zero process exit code.

Required operator action for `blocked_auth_stale`:

1. Reauthenticate the affected NotebookLM profile(s) on the host.
2. Re-sync the profile bundle if the host uses the workstation-managed bundle.
3. Requeue or retry the blocked lecture after auth is healthy again.

## Validation

Local verification completed on 2026-05-11:

- targeted queue regression slice: `38 passed`
- full `tests/notebooklm_queue` suite: `101 passed`

Coverage added/updated for:

- auth-stale execution finalization
- repair of legacy `failed_retryable` auth jobs
- mixed blocked + timed backlog behavior in `serve-show`
- CLI success semantics for `blocked_backlog_remaining`
