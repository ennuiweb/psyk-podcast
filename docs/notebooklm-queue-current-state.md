# NotebookLM Queue Current State

Last updated: 2026-05-23

This document is the current-state checkpoint for the Hetzner-owned NotebookLM queue + R2 migration program. It is intentionally separate from the canonical migration plan in [notebooklm-queue-r2-migration.md](notebooklm-queue-r2-migration.md).

Use this file for:

- what has actually shipped
- what is verified
- what is still missing before full autonomous Hetzner ownership
- the current boundary between queue-owned publication and legacy workflow publication

## Implemented

The following queue milestones are implemented on `main`:

- `722cb93` - hardened the canonical migration plan
- `0c44a3c` - queue core
- `ce1db7f` - discovery + dry-run planning
- `0d51f31` - real generate/download execution
- `2ce0606` - publish-bundle preparation
- `2092b46` - NotebookLM notebook-capacity recovery by deleting the oldest owned notebook and retrying once
- `cf75a59` - NotebookLM notebook-capacity recovery recognizes `notebooklm-py`'s newer `NotebookLimitError` wrapper as well as the legacy raw `CREATE_NOTEBOOK` `RPCError`; queue retry classification also recognizes notebook-limit text without relying on stderr RPC noise. Hosted smoke on 2026-05-23 verified W12L1 recovered from a `499/500` notebook-limit failure by deleting the oldest safe owned `default` notebook, retrying once, creating the target notebook, and moving the queue job to `waiting_for_artifact`.
- `42548ae` - bounded notebook reclaim is available as a queue-owned maintenance primitive with dry-run-first manual CLI, persisted reports, and optional auth/cooldown recovery integration for `refresh-profiles`. Hosted smoke on 2026-05-23 verified dry-run and apply paths; `default` reclaimed 24 safe old notebooks total and `g2a_geminiaiadvanced_kimngan12795` reclaimed 25, leaving both auth-fresh profiles with 25 free notebook slots. The Hetzner profile-refresh env now enables `NOTEBOOKLM_PROFILE_REFRESH_RECLAIM_ON_RECOVERY=1` with apply mode and a 25-slot target/max for future recoveries.
- 2026-05-23 auth-hardening update - profile state classification is now shared across generation, download, capacity inspection, and refresh. Profile refresh uses keepalive plus a real NotebookLM list probe before repairing auth-stale state, skips unrecovered stale profiles until storage changes or an operator forces a check, and treats expired validation as an automatic wait for the refresh timer instead of a manual failure. The Hetzner profile sync helper is now bundle-only by default and requires explicit profile uploads for reauth storage, with remote backups and newer-file overwrite protection.
- `a5b2748` - R2 object upload for approved queue bundles
- `ad01a4f` - repo metadata rebuild from uploaded objects
- `532ac58` - queue-owned quiz sync plus allowlisted repo publication
- `9ef94cf` - queue-owned downstream completion and workflow-grade repo publish hardening
- current working tree after `9ef94cf` - `generate-feed.yml` now respects `publication.owner`, so queue-owned shows can skip the legacy writer path entirely

## Current queue capabilities

`notebooklm_queue/` and `scripts/notebooklm_queue.py` now support:

- durable queue storage outside git
- show-scoped locking
- deterministic lecture-scoped job identity
- adapter-based discovery for:
  - `bioneuro`
  - `personlighedspsykologi-en`
- dry-run execution planning
- real generate/download execution with persisted run manifests
- local publish-bundle validation with durable publish manifests
- deterministic R2 object upload for media artifacts
- post-upload verification via `head_object`
- repo-side R2 media manifest refresh
- queue-owned `quiz_links.json` refresh for supported Freudd-backed shows
- repo metadata rebuild from uploaded objects:
  - RSS
  - `episode_inventory.json`
  - `spotify_map.json` for supported shows
  - `content_manifest.json` for Freudd-backed shows
- allowlisted repo publication for supported shows:
  - tracked-dirtiness guard outside the generated-file allowlist
  - show-scoped generated-file commit
  - rebase against `origin/main` with allowlisted conflict recovery
  - push to `main`
  - persisted repo commit SHA in queue job artifacts
- downstream completion for supported shows:
  - waits for expected push-triggered workflows such as `deploy-freudd-portal.yml`
  - records downstream run ids and URLs in queue job artifacts
  - marks jobs `completed` only after downstream success or no-op completion
- `personlighedspsykologi-en` queue hardening now also covers:
  - strict manual-summary coverage validation before feed generation
  - queue-owned `sync_regeneration_registry.py` execution as part of repo metadata rebuild
  - fail-closed registry/inventory validation after feed generation
  - fail-closed slide-brief coverage audit instead of warn-only queue output
- safe fresh-store discovery:
  - discovery now skips lecture keys that already exist in the configured `episode_inventory.json` by default
  - this prevents a new Hetzner queue store from automatically re-enqueueing the full historical `bioneuro` catalog
  - manual backfill still remains available via the explicit discovery override
- pilot-safe config binding:
  - discovery can hash against an alternate show config with `--show-config`
  - publish manifests pin the selected show-config path
  - upload, metadata rebuild, and repo push reuse the manifest-bound config instead of silently falling back to the live `config.github.json`
  - Freudd sidecars and feed artifacts now also follow that selected config, so a non-live `bioneuro` pilot can publish into `shows/bioneuro/pilot/**` without overwriting the live Drive-backed artifacts
  - `shows/bioneuro/config.r2-pilot.template.json` now provides the safe non-live pilot shape; it still requires a real `storage.public_base_url` before use

## Current state-machine boundary

Successful jobs can now advance through:

- `awaiting_publish`
- `approved_for_publish`
- `objects_uploaded`
- `committing_repo_artifacts`
- `repo_pushed`
- `completed`

That means the queue currently owns:

- generation
- download
- local artifact validation
- object upload
- quiz-link refresh
- repo metadata regeneration
- allowlisted repo commit/push
- downstream synchronization for existing push-triggered Freudd deploys

The queue runtime now also has a concrete Hetzner packaging layer:

- `drain-show` provides the single-cycle primitive and `serve-show` now provides the quota-aware remote worker entrypoint
- `serve-show` now keeps draining while timed backlog (`retry_scheduled` or `waiting_for_artifact`) still exists, even if explicit blocked jobs are also present; it exits cleanly with `blocked_backlog_remaining` only when explicit blocked backlog is all that remains, exits cleanly with `service_timeout_reached` when the remaining wait window would overrun the configured worker budget, and still fails closed on invalid retry timestamps or generic `failed_retryable` backlog instead of hot-looping
- queue-owned NotebookLM execution now checks profile capacity before claiming generation jobs and uses a global `notebooklm-capacity` queue lock so concurrent show timers cannot generate against the same profile pool in parallel
- profile freshness is now a queue-owned maintenance concern: `refresh-profiles` validates configured profile storage through `notebooklm-py`, repairs `auth_stale` profile-state markers only after successful validation, preserves active rate-limit cooldowns, writes reports under `<storage-root>/profile-refresh/`, and uses the same global `notebooklm-capacity` lock as generation
- templated `systemd` service and timer artifacts now exist under `notebooklm_queue/deploy/systemd/`
- profile-refresh `systemd` service and timer artifacts now exist under `notebooklm_queue/deploy/systemd/`
- the Hetzner runtime/env/install runbook now exists in [notebooklm-queue-operations.md](notebooklm-queue-operations.md)

## Verified in this session

Local verification completed:

- Notebook-capacity tests passed after the reclaim-on-create-notebook fix
- queue publish tests passed after R2 upload implementation
- queue metadata tests passed after repo rebuild implementation
- full `tests/notebooklm_queue` suite passed after the latest repo-publish hardening and downstream sync work
- full `tests/notebooklm_queue` suite passed after the profile-refresh implementation (`133 passed`)

Hosted verification completed on 2026-05-23:

- `/opt/podcasts` fast-forwarded to the profile-refresh implementation on `main`
- `podcasts-notebooklm-profile-refresh.service` and `.timer` installed and daemon-reloaded
- `/etc/podcasts/notebooklm-queue/profile-refresh.env` installed for the shared hosted profile set
- manual `refresh-profiles --force` run produced a durable report under `/var/lib/podcasts/notebooklm-queue/profile-refresh/`
- systemd service smoke completed successfully and wrote a second report
- latest hosted profile-refresh outcome: `g2a_geminiaiadvanced_kimngan12795` refreshed successfully; the ten older profiles failed validation with Google sign-in redirects and still require real reauth
- timer enabled; next scheduled profile-refresh runs will keep currently valid and newly reauthed profiles warm, while preserving rate-limit cooldowns

## Profile Reauth Checkpoints

Use this section to compare how long browser storage-state auth survives after the keepalive/probe hardening.

- 2026-05-23T19:20:19Z: `oskarhoegsgaard` was reauthed locally and passed local `notebooklm list --json`; the uploaded file checksum matched the Hetzner copy, but hosted `refresh-profiles --force` at 2026-05-23T19:23:17Z still failed with a Google sign-in redirect, so the hosted queue kept this profile `auth_stale`.
- 2026-05-23T19:22:58Z: `tjekdepotadmin` was reauthed locally and passed local `notebooklm list --json`; after explicit safe sync to Hetzner, hosted `refresh-profiles --force` at 2026-05-23T19:23:17Z passed keepalive plus `notebooklm list --json` probe and repaired the profile to `usable`.
- 2026-05-23T19:23:20Z hosted capacity after the reauth attempt: `usable=3` (`default`, `stanhawkservices`, `tjekdepotadmin`), `cooldown=3`, `auth_stale=3`.
- 2026-05-24T07:36:11Z: `oskarhoegsgaard`, `vedeloskar`, and `g2a_geminiaiadvanced_kimngan12795` were reinitialized locally, each passed a local `notebooklm --storage <profile-file> list --json` probe, were synced explicitly to Hetzner, and passed hosted `refresh-profiles --force --actor operator-reauth` keepalive plus probe. Hosted capacity at 2026-05-24T07:36:29Z showed these three profiles `usable`; the other six configured profiles were in rate-limit cooldown, with no `auth_stale` profiles remaining.

## Dead Letter Checkpoint

As of 2026-05-23, the visible `personlighedspsykologi-da` dead-letter backlog is superseded queue history, not active work to resume blindly:

- 43 total `dead_letter` records.
- 22 records are for obsolete Danish config hash `55f02f15a2c7b8a6`, superseded by queue hash `87f3a51dce5b5cf4`.
- 21 records were stale previous-config Danish queue records retired after the current config cohort `e75314af2745ddb6` was enqueued.
- Decision: do not reschedule these records as-is, and do not disable the dead-letter feature. A future cleanup can split this into a clearer `superseded` or `cancelled_superseded` terminal state, leaving `dead_letter` for genuine failures.
- 2026-05-24 cleanup: the 43 `personlighedspsykologi-da` dead-letter records were removed from the live `jobs/` store and indexes because they polluted queue totals. Audit copies were preserved under `/var/lib/podcasts/notebooklm-queue/maintenance/dead-letter-cleanup-20260524T203407Z/` and the existing `dead-letter/` archive.

Required repo workflows completed successfully for the latest queue commits:

- `a5b2748` -> Actions run `25183786210`
- `ad01a4f` -> Actions run `25212535606`
- `532ac58` -> Actions run `25213172226`
- `9ef94cf` -> Actions run `25214094593`
- `609539b` -> Actions run `25338719821`
- `0e08d0d` -> Actions run `25339098796`
- `0b0d41c` -> Actions run `25325562747`

GitHub Actions baseline:

- the repo workflows that still use shared GitHub JavaScript actions are now upgraded to `actions/checkout@v6` and `actions/setup-python@v6`
- this removes the previous Node 20 deprecation warning from the active `generate-feed.yml` path

## Live production state

`bioneuro` is now the first live cut-over show.

As of 2026-05-03:

- `shows/bioneuro/config.github.json` resolves to:
  - `storage.provider = "r2"`
  - `publication.owner = "queue"`
- the full `29`-episode `bioneuro` back-catalog has been uploaded to Cloudflare R2 and recorded in `shows/bioneuro/media_manifest.r2.json`
- a live queue-owned publication completed end to end for `W13L1`
- the queue pushed live `bioneuro` feed-side artifacts in commit `7318b443888d509ea6b891e3c6a7d44e96f7f525`
- downstream Freudd deploy completed successfully in Actions run `25289331905`
- the current live public enclosure base is the temporary bucket hostname:
  - `https://pub-fe942499398a478c8a8f432207051244.r2.dev`

Current active show ownership is now mixed:

- `bioneuro`: live, R2-backed, queue-owned
- `berlingske`: legacy workflow
- `intro-vt`: live, R2-backed, legacy workflow; feed regeneration now reads the checked-in R2 manifest directly
- `personal`: live, R2-backed, legacy workflow; ingest now runs through the resumable local-to-R2 publisher, which backfills missing manifest checksums and transcodes configured `.m4a` / `.wav` sources to MP3 before upload
- `personlighedspsykologi-en`: live, R2-backed, queue-owned
  - queue metadata hardening is in place for manual summaries, regeneration registry sync, and slide-brief blocking
  - the Hetzner queue runtime is now installed and verified; the first `systemd` drain completed successfully as a no-op because discovery correctly skipped already-published lecture keys
- `personlighedspsykologi-da`: R2-backed and queue-configured, but generation is paused on Hetzner as of 2026-05-24T20:37Z; `podcasts-notebooklm-queue@personlighedspsykologi-da.timer` is disabled and the service is inactive. Existing queue records remain in place.
- `social-psychology`: live, R2-backed, legacy workflow; feed regeneration now reads the checked-in R2 manifest directly

Operational boundary:

- all active audio-publishing shows are now live on `storage.provider = "r2"`
- Drive source ingest is now retired for the active publication surface
- `berlingske` remains outside that statement because it is paused and not part of the active publication surface

## Immediate missing steps before full autonomous ownership

1. Replace the temporary `r2.dev` public base URL with the intended production audio domain.
2. Observe one or more normal `personlighedspsykologi-en` queue-owned publish cycles on the live R2-backed config.
3. Decide whether paused legacy shows should keep any remaining Drive-only tooling or whether those code paths can be archived.

## Recommended reading order

- [notebooklm-queue-r2-migration.md](notebooklm-queue-r2-migration.md) - canonical long-term plan and backlog
- [notebooklm-automation.md](notebooklm-automation.md) - subsystem layout and CLI entrypoints
- [feed-automation.md](feed-automation.md) - current feed pipeline and provider model
