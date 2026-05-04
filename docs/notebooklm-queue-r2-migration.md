# NotebookLM Queue And R2 Migration Plan

## Scope

This document is the canonical implementation plan for the combined migration of:

- NotebookLM generation orchestration to a server-owned queue on Hetzner
- published audio storage from Google Drive to Cloudflare R2 or equivalent object storage

It is the control document for architecture, migration order, cutover policy, operational guardrails, and acceptance criteria across:

- NotebookLM automation
- podcast feed publication
- quiz/manifest sidecars
- Freudd downstream refresh and deploy behavior

External tracker:

- Google Sheets: <https://docs.google.com/spreadsheets/d/1accYHFiBP2CQIBUBNnLAeEm3ScdKlQwRRviYsEzF6ZM/edit>

## Executive Review

The current plan is directionally correct, but the original version was not yet safe enough for implementation without avoidable operational risk.

What the original plan got right:

- queue migration and storage migration are one program, not two
- `personal` is the right pilot
- `bioneuro` should migrate before `personlighedspsykologi-en`
- one canonical writer per migrated show is mandatory
- queue state must be durable and resumable

What was missing and is now explicit in this plan:

- the exact source-of-truth boundaries across queue state, object storage, git metadata, and downstream Freudd artifacts
- a formal queue state machine with retry, blocked, and dead-letter states
- a transaction model for publish, including what is atomic and what is only compensatable
- a cutover contract that prevents GitHub Actions and Hetzner from becoming dual writers
- rollback and recovery playbooks
- an operations model for secrets, timers, locks, logs, and alerting
- a subject-specific strategy for `personlighedspsykologi-en` rollout state

## Why This Is One Program

These changes should be implemented as one program, not two separate projects.

- Building a Hetzner queue around Drive preserves the weakest part of the current system: desktop- and Drive-dependent publication.
- Migrating storage without a queue preserves the other weak part: no durable server-owned generation state machine.
- Doing both together creates one clean cutover to the target architecture instead of two overlapping migrations.

## Target Architecture

### Control Plane

- Hetzner owns generation orchestration, retries, locks, and durable queue state.
- The queue runs as a server-managed `systemd` service plus timer.
- NotebookLM auth runs from server-managed state, not local desktop profile files.

### Data Plane

- Audio for migrated shows is published to object storage via `storage.provider = "r2"`.
- Git remains the source of truth for generated metadata artifacts:
  - `episode_inventory.json`
  - `quiz_links.json`
  - `spotify_map.json`
  - `content_manifest.json`
  - `feeds/rss.xml`
- Freudd production deploy remains on the DigitalOcean host until explicitly changed.

### Ownership Model

- GitHub Actions remains deploy/reconcile infrastructure for migrated shows.
- Hetzner becomes the canonical producer for generation and publish outputs for migrated shows.
- GitHub Actions may validate or deploy migrated shows, but it must not independently regenerate their outputs.

## Non-Goals

- no attempt to automate manual slide mapping
- no attempt to automate hand-authored reading summaries or lecture summaries
- no attempt to move Freudd hosting from DigitalOcean as part of this program
- no attempt to migrate every show at once
- no attempt to rewrite the existing NotebookLM generation logic when wrappers will suffice

## Design Principles

- Prefer composition over replacement. Reuse `generate_week.py`, `download_week.py`, feed generation, quiz sync, Spotify sync, and manifest rebuild rather than reimplementing them.
- Make every step idempotent or compensatable.
- Publish only from validated artifacts.
- Make manual prerequisites visible as first-class queue states, not hidden operator knowledge.
- Keep one canonical home for every piece of state.
- Design for interruption, restart, and partial failure from the start.

## Architectural Invariants

These are non-negotiable.

1. One canonical writer per migrated show.
2. Episode identity must remain stable across migration.
3. Queue state lives outside git and survives process restarts.
4. Publish decisions are derived from a single job snapshot, not from mixed-time reads across multiple systems.
5. Feed, quiz, Spotify map, and manifest outputs for one publish run must all derive from the same validated artifact set.
6. Validation failure blocks publish.
7. Manual blockers must be represented explicitly in state.
8. Rollback must not require reconstructing state from logs alone.

## Current Reality And Constraints

The codebase already has most of the building blocks, but they do not yet compose into a server-owned publish system.

- `generate_week.py` already supports non-blocking generation, resume via request logs, tagging, and profile rotation.
- `generate_podcast.py` already supports multi-profile auth and `NOTEBOOKLM_AUTH_JSON`.
- `podcast-tools/storage_backends.py` already supports both Drive and R2 publication models.
- `spotify_transcripts/store.py` already demonstrates the right queue/store patterns: atomic writes, resumable state, and manifest separation.
- `.github/workflows/generate-feed.yml` still assumes for non-Drive quiz sync that quiz JSON exists in a local repo output tree on the runner.
- `rollout_week.py` still encodes Drive-mount publication and legacy rollout assumptions for `personlighedspsykologi-en`.

This means the migration is not a greenfield build. It is a control-plane replacement and a publication-path replacement around existing generation logic.

## Sources Of Truth

Each class of state must have a single owner.

| State | Canonical owner | Notes |
|---|---|---|
| Queue/job lifecycle | Hetzner queue store | Outside git, atomic JSON writes, per-show locks |
| Raw generated audio before publish | Hetzner workspace | Ephemeral or retained per retention policy |
| Published audio objects | R2 | Stable keys for migrated shows |
| Podcast metadata and feed artifacts | Git repo | Commit only validated generated files |
| Quiz files served to Freudd | Droplet filesystem | Produced from queue publish flow |
| Freudd runtime content | DigitalOcean deploy | Rebuilt from git artifacts and quiz files |
| `personlighedspsykologi-en` rollout state | `regeneration_registry.json` in git | Must stay aligned with published inventory |

## Show Ownership States

Each show must be in one of these program states:

- `legacy_drive`: GitHub workflow remains canonical writer
- `pilot_migrating`: Hetzner queue is running in shadow or controlled mode
- `queue_owned`: Hetzner is canonical writer; GitHub workflow may validate/deploy only
- `retired`: show no longer participates in this migration program

The ownership state must be explicit in show config or an equivalent central registry. It cannot remain implicit in tribal knowledge or environment-specific behavior.

## Queue Model

### Job Identity

Jobs are lecture-scoped, not file-scoped.

Canonical job identity:

- `show_slug`
- `subject_slug`
- `lecture_key`
- `content_types`
- `config_hash`
- optional `campaign` or rollout tag where needed

This is the correct granularity because the existing generation scripts already think in lecture/week-level batches.

### Queue Storage

Queue state should live outside git, for example:

- `/var/lib/podcasts/notebooklm-queue/`

Recommended layout:

- `jobs/<show>/<job-id>.json`
- `indexes/<show>.json`
- `runs/<timestamp>-<show>-<job-id>.json`
- `locks/<show>.lock`
- `artifacts/<show>/<job-id>/`
- `dead-letter/<show>/<job-id>.json`

Implementation rules:

- atomic writes only
- durable timestamps in UTC
- append-only run history
- no silent in-place mutation that destroys failure context

### Queue State Machine

Each job should move through explicit states.

Discovery and eligibility:

- `discovered`
- `blocked_manual_prereq`
- `blocked_config_error`
- `queued`

Execution:

- `generating`
- `generated`
- `downloading`
- `downloaded`
- `validating_generated_artifacts`

Publish preparation:

- `awaiting_publish`
- `uploading_objects`
- `objects_uploaded`
- `rebuilding_metadata`
- `validating_publish_bundle`

Publication and downstream sync:

- `committing_repo_artifacts`
- `repo_pushed`
- `syncing_downstream`
- `completed`

Failure and control:

- `retry_scheduled`
- `failed_retryable`
- `failed_terminal`
- `dead_letter`
- `cancelled`

Each transition must record:

- `state`
- `transitioned_at`
- `attempt_count`
- `last_error`
- `next_retry_at`
- `operator_notes` where applicable

## Publish Transaction Model

Object storage, git, and remote quiz sync do not support one global atomic transaction. The design must therefore use a staged publish with compensating controls.

### Publish Order

1. Acquire the show lock.
2. Load the exact job snapshot to publish.
3. Validate local generated artifacts before any external side effects.
4. Upload audio objects to final deterministic R2 keys.
5. Verify object existence, size, checksum when available, and public URL construction.
6. Rebuild metadata locally from the uploaded object set:
   - inventory
   - feed
   - quiz links
   - Spotify map
   - content manifest
7. Run publish validation over the complete bundle.
8. Commit and push only allowlisted generated files.
9. Sync quiz JSON to the droplet.
10. Trigger downstream reconcile or deploy behavior as required.
11. Mark the job completed and persist a run manifest with every produced artifact reference.

### Why Upload Happens Before Git Push

Feed metadata must not reference objects that do not exist yet. Upload-first is therefore the safer direction.

The tradeoff is that objects may exist in R2 before git metadata is pushed. That is acceptable because:

- orphaned objects are safer than broken feed references
- objects can be reconciled and garbage-collected later
- git remains the visibility boundary for feed consumers

### Publish Validation Gates

Publish must stop if any of these fail:

- missing or zero-byte audio object
- object key mismatch
- invalid public URL template
- GUID drift for an existing logical episode
- inventory/feed mismatch
- quiz sync generation mismatch
- manifest with zero quiz assets where quiz assets are expected
- unresolved `personlighedspsykologi-en` rollout inconsistency

## Object-Key And Identity Strategy

Stable identity matters more than storage convenience.

Rules:

- object keys must be deterministic and derived from canonical episode identity, not ad hoc local filenames alone
- once a logical episode key is published, its public URL should not change unless there is a deliberate migration with preserved identity metadata
- `stable_guid` must be preserved for migrated episodes
- rewrites that produce new audio for the same logical episode must update the object content, not create a new public identity unless the product decision is intentionally “new episode”

Recommended key shape:

- `<show-slug>/<lecture-key>/<episode-key>.mp3`

If a show needs stronger immutability during rollout:

- publish by stable logical key
- store content hash and generation hash in metadata or manifest, not the public URL

## Git Commit Boundary

Only generated artifacts that belong to the current show may be committed by the queue publish step.

Allowlisted artifact classes:

- `shows/<show>/feeds/rss.xml`
- `shows/<show>/episode_inventory.json`
- `shows/<show>/quiz_links.json`
- `shows/<show>/spotify_map.json`
- `shows/<show>/content_manifest.json`
- `shows/<show>/regeneration_registry.json` when explicitly required by that show

The queue must not commit unrelated local modifications. It must fail closed if the worktree is unexpectedly dirty in overlapping paths.

## Workflow Ownership And Cutover Contract

Cutover must be explicit and reversible.

### Before Cutover

- GitHub Actions remains the canonical writer.
- Hetzner may run discovery, dry runs, or shadow generation.
- No publish to canonical R2 keys or git metadata for that show.

### During Cutover

- Freeze the show's writer ownership.
- Disable or skip the show's generation path in `generate-feed.yml`.
- Run one controlled queue-owned publish.
- Validate the resulting feed, metadata, quiz links, and Freudd downstream state.

### After Cutover

- Hetzner is the only canonical writer for that show.
- GitHub Actions may:
  - validate generated artifacts
  - deploy downstream
  - rebuild derived artifacts only if explicitly delegated from the queue-owned publish path
- GitHub Actions must not independently regenerate queue-owned show outputs from source media.

## Secrets And Auth Model

NotebookLM automation on a server is only viable if auth is explicit and recoverable.

Required secret classes:

- NotebookLM auth state
- R2 credentials
- git push credentials
- DigitalOcean SSH key for quiz sync and Freudd operations where needed
- Spotify API credentials

Rules:

- secrets live in operator-managed server env or secret store, not in repo files
- queue runs must fail with a specific auth-health state, not a generic crash
- auth expiration must be detected proactively where possible
- a manual auth refresh runbook must exist before the first unattended deployment

Recommended env model:

- `NOTEBOOKLM_AUTH_JSON` or server-managed `NOTEBOOKLM_HOME`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `SPOTIFY_CLIENT_ID`
- `SPOTIFY_CLIENT_SECRET`
- git credential mechanism appropriate for non-interactive push

## Manual Prerequisites

Some content is intentionally manual. The queue must model this rather than pretending full automation exists.

Examples:

- slide mapping missing
- summary text not yet authored
- lecture blocked for editorial review
- rollout candidate requires judgment before activation

Required queue states:

- `blocked_manual_prereq`
- `awaiting_review`
- `approved_for_publish`
- `rejected_manual_review`

Each blocked job must point to the exact missing prerequisite, not only a generic blocked label.

## Observability And Operations

### Runtime Model

- one `systemd` service for the queue runner
- one `systemd` timer for periodic execution
- persistent journal logs
- one lock per show plus one optional global scheduler lock

### Required Operational Outputs

- per-run structured log
- per-job run manifest
- queue summary command suitable for SSH use
- dead-letter listing
- recent-failure summary

### Alerts

At minimum, alert on:

- repeated NotebookLM auth failure
- repeated rate-limit exhaustion beyond policy threshold
- publish validation failure
- git push failure after retries
- quiz sync failure
- dead-letter job creation

## Recovery And Rollback

Rollback must be defined before the first cutover.

### Failure Classes

- generation failure before any publish side effect
- object upload succeeded, metadata push failed
- metadata push succeeded, downstream sync failed
- rollout registry updated inconsistently with published inventory

### Required Recovery Paths

1. Retry from the last durable queue state without regenerating unnecessary work.
2. Rebuild metadata from the last verified uploaded object set.
3. Re-run downstream sync without re-uploading audio.
4. Reconcile orphaned R2 objects that were uploaded before a failed git push.
5. Restore the previous feed and metadata commit if a bad publish escaped validation.

### Rollback Rules

- rollback is by git commit for metadata
- rollback is by queue reconciliation for server state
- rollback does not immediately delete R2 objects unless they are confirmed orphaned and not referenced by any committed inventory
- `personlighedspsykologi-en` rollback must preserve or restore consistent `regeneration_registry.json` state together with inventory

## Show-Specific Strategy

### `personal`

Role:

- low-risk storage migration

Current status:

- live on `storage.provider = "r2"`
- remains `publication.owner = "legacy_workflow"`
- uses a resumable local-to-R2 publisher for ongoing ingest

Success criteria:

- feed identity preserved after storage cutover
- deterministic object keys and stable feed identity
- no Drive watcher or Drive source ingest remains in the live publication path

### `bioneuro`

Role:

- first real production subject migration

Additional requirements:

- quiz sync must be part of queue publish
- Spotify map must remain coherent
- manifest rebuild must remain in lockstep with inventory
- GitHub Actions must stop being a competing writer

Success criteria:

- standard lecture flow runs unattended under queue ownership
- downstream Freudd content is correct after publish

### `personlighedspsykologi-en`

Role:

- final migration target due to highest coupling

Special constraints:

- `regeneration_registry.json` is part of the product contract, not just an internal log
- legacy `rollout_week.py` behavior must be decomposed into queue-owned states rather than carried forward as-is
- Drive-mount assumptions must be eliminated

Required state alignment:

- `episode_inventory.json`
- `regeneration_registry.json`
- published R2 objects
- quiz links
- content manifest

Recommended rollout model:

- keep `sync_regeneration_registry.py` as the canonical registry synchronizer
- move activation and publication transitions into explicit queue steps
- require validation that `active_variant`, inventory identity, and published object set agree before final commit

Current shipped hardening:

- queue metadata rebuild now runs strict manual-summary coverage validation before feed generation
- queue metadata rebuild now runs `sync_regeneration_registry.py` before feed generation for this show
- queue metadata rebuild now runs strict registry/inventory validation after feed generation
- queue metadata rebuild now treats slide-brief coverage failures as blocked manual prerequisites instead of warn-only queue output
- live `publication.owner` is now `queue`

## Implementation Phases

### Phase 0 - Architecture Freeze

Deliverables:

- this canonical plan
- external tracker
- explicit show ownership model
- decision on queue storage root and secrets approach

Exit criteria:

- all invariants accepted
- pilot show confirmed
- no new Drive-specific assumptions introduced

### Phase 1 - Queue Core

Deliverables:

- `notebooklm_queue/` package
- queue store with atomic writes
- per-show lock handling
- job discovery and report commands
- dry-run execution path

Exit criteria:

- interruption-safe resume works
- queue transitions are tested
- SSH-friendly reporting exists

Current implementation status, 2026-04-29:

- queue-core foundation has been implemented in `notebooklm_queue/` and `scripts/notebooklm_queue.py`
- current coverage includes deterministic job identity, atomic JSON storage, show/global indexes, lock handling, state transitions, claim/retry/reconcile operations, adapter-based discovery, dry-run execution planning, real generate/download execution, publish-bundle preparation, durable run/publish manifests, and focused unit tests
- current discovery adapters cover `bioneuro` and `personlighedspsykologi-en`
- successful execution now advances to `awaiting_publish`, `prepare-publish` can validate local generated artifacts and move a job to `approved_for_publish`, `upload-r2` can upload approved media artifacts to deterministic R2 object keys and move a job to `objects_uploaded`, and `rebuild-metadata` can now regenerate repo-side RSS/inventory plus show-specific sidecars before moving the job to `committing_repo_artifacts`; commit/push, downstream sync, and Hetzner service deployment still remain pending

### Phase 2 - Publication Subsystem

Deliverables:

- deterministic R2 object-key logic
- upload verification
- allowlisted git commit path
- publish validation bundle
- orphan reconciliation tooling

Exit criteria:

- metadata can be rebuilt from uploaded object state
- GUID continuity tests pass
- publish failure leaves recoverable state

### Phase 3 - Storage Cutover For `personal`

Deliverables:

- `personal` moved to `storage.provider = "r2"`
- resumable local-to-R2 publish helper
- successful legacy-workflow feed rebuild from the R2 manifest

Exit criteria:

- feed and inventory are correct
- GUID continuity is preserved
- live publication no longer depends on the Drive watcher

### Phase 4 - Production Cutover For `bioneuro`

Deliverables:

- queue-owned `bioneuro` publish
- integrated quiz sync, Spotify sync, and manifest rebuild
- GitHub workflow no longer regenerates `bioneuro` independently

Exit criteria:

- unattended standard lecture flow succeeds
- Freudd downstream state is correct
- failure alerts and recovery playbooks are proven

### Phase 5 - Production Cutover For `personlighedspsykologi-en`

Deliverables:

- queue-owned rollout-safe publish path
- explicit manual blocker states
- registry/inventory/object-set consistency validation

Exit criteria:

- standard lectures are queue-owned
- manual exceptions surface as explicit states
- A/B rollout integrity is preserved

### Phase 6 - Legacy Drive Retirement For Migrated Shows

Deliverables:

- cleanup of obsolete Drive/App Script assumptions for migrated shows
- workflow and secret cleanup
- docs updated to steady-state architecture

Exit criteria:

- migrated shows have no active Drive publication dependency
- remaining Drive support is clearly legacy-only

## Backlog

Status legend:

- `planned`
- `active`
- `blocked`
- `done`

### Workstream A - Queue Core

| ID | Status | Item | Notes |
|---|---|---|---|
| A1 | done | Create `notebooklm_queue` module skeleton | Implemented as the queue-core foundation package. |
| A2 | done | Implement queue store with atomic JSON writes | Built with show/global indexes and durable job payloads. |
| A3 | done | Add per-show lock handling | Implemented via advisory file locks. |
| A4 | done | Define lecture-scoped job identity | Implemented with deterministic `show + subject + lecture + content_types + config_hash + campaign` hashing. |
| A5 | done | Implement explicit job state machine | State vocabulary and transition history are in the queue core. |
| A6 | done | Add queue report and inspect CLI | `enqueue`, `list`, `inspect`, `report`, `transition`, `claim-next`, `retry-ready`, and `reconcile` are implemented. |
| A7 | done | Add adapter-based discovery and dry-run plan commands | `discover` and `run-dry` are implemented for supported NotebookLM subjects. |

### Workstream B - NotebookLM Execution

| ID | Status | Item | Notes |
|---|---|---|---|
| B1 | done | Wrap `generate_week.py` from the queue | Implemented through adapter-driven execution service and `run-once`. |
| B2 | done | Wrap `download_week.py` from the queue | Implemented through adapter-driven execution service and `run-once`. |
| B3 | planned | Move auth to server-managed env/state | Prefer `NOTEBOOKLM_AUTH_JSON` or `NOTEBOOKLM_HOME`. |
| B4 | planned | Define profile-rotation policy for server runs | Reuse existing rotation support. |
| B5 | planned | Add auth/quota health checks | Surface as explicit queue states. |

### Workstream C - Publish And R2

| ID | Status | Item | Notes |
|---|---|---|---|
| C1 | planned | Define stable object-key layout | Stable public identity is mandatory. |
| C2 | planned | Implement upload verification | Validate size, existence, and checksum where possible. |
| C3 | active | Add publish-bundle validation | Local generated-artifact validation and durable publish manifests now exist via `prepare-publish`; `upload-r2` now covers deterministic object upload plus repo-side media manifest refresh, `rebuild-metadata` now regenerates queue-owned quiz links plus repo-side feed/inventory sidecars and show-specific metadata, `push-repo` now commits and pushes allowlisted generated artifacts with queue-favoring rebase conflict recovery, and `sync-downstream` now waits for expected post-push workflows. Queue-owned show gating and cutover still remain. |
| C4 | planned | Add orphaned-object reconciliation tooling | Needed for upload-before-push failure cases. |

### Workstream D - Metadata And Downstream Sync

| ID | Status | Item | Notes |
|---|---|---|---|
| D1 | planned | Rebuild inventory and feed from uploaded objects | Queue publish owns this for migrated shows. |
| D2 | done | Integrate `sync_quiz_links.py` in publish flow | Queue metadata rebuild now refreshes `quiz_links.json` before RSS/inventory sidecars for supported shows. |
| D3 | done | Integrate Spotify map sync | `rebuild-metadata` now refreshes Spotify maps for supported shows before repo publication. |
| D4 | done | Integrate content manifest rebuild | `rebuild-metadata` now rebuilds Freudd content manifests for supported shows before repo publication. |
| D5 | done | Define generated-file commit allowlist | `push-repo` now stages and commits only the active show's generated artifacts and fails closed on unexpected tracked repo dirtiness. |
| D6 | done | Observe expected downstream deploy workflows | `sync-downstream` now waits for expected push-triggered workflows such as `deploy-freudd-portal.yml` and marks jobs `completed` only after success. |

### Workstream E - Cutover And Ownership

| ID | Status | Item | Notes |
|---|---|---|---|
| E1 | done | Add explicit show ownership state | `publication.owner` now exists in show configs with `legacy_workflow` as the default writer. |
| E2 | done | Update `generate-feed.yml` for queue-owned shows | The workflow now resolves `publication.owner` and skips the legacy writer path for queue-owned shows. |
| E3 | planned | Add cutover checklist and rollback checklist | Must be run per show. |
| E4 | done | Add `systemd` units and runbook | `drain-show`, checked-in `systemd` artifacts, and `docs/notebooklm-queue-operations.md` now define the Hetzner runtime shape; server install remains an operational rollout step. |

### Workstream F - Subject Migration

| ID | Status | Item | Notes |
|---|---|---|---|
| F1 | done | Migrate `personal` storage to R2 | `personal` is now live on `storage.provider = "r2"`, remains `publication.owner = "legacy_workflow"`, and now uses a resumable local-to-R2 publisher instead of Drive ingest. |
| F2 | done | Migrate `bioneuro` | `bioneuro` is now live, `storage.provider = "r2"`, and `publication.owner = "queue"`. |
| F3 | done | Migrate `personlighedspsykologi-en` | `personlighedspsykologi-en` is now live on `storage.provider = "r2"` and `publication.owner = "queue"`. The checked-in R2 manifest is the canonical published-audio inventory, and preserved Drive IDs remain compatibility metadata only for regeneration validation. |
| F4 | done | Migrate `intro-vt` storage to R2 | `intro-vt` is now live on `storage.provider = "r2"` under `publication.owner = "legacy_workflow"`, with the checked-in R2 manifest as the canonical feed source and RSS-based GUID fallback for continuity because the show does not keep a committed `episode_inventory.json`. |
| F5 | done | Migrate `social-psychology` storage to R2 | `social-psychology` is now live on `storage.provider = "r2"` under `publication.owner = "legacy_workflow"`, with the checked-in R2 manifest as the canonical feed source and RSS-based GUID fallback for continuity because the show does not keep a committed `episode_inventory.json`. |

### Workstream G - Validation And Tests

| ID | Status | Item | Notes |
|---|---|---|---|
| G1 | active | Add queue tests for state transitions | Store, discovery, execution, and publish-bundle tests are in place; upload/push recovery cases still remain. |
| G2 | planned | Add R2 GUID continuity tests | Existing inventory and manifest fixtures. |
| G3 | planned | Add publish transaction tests | Upload-before-push and push-failure recovery cases. |
| G4 | planned | Add show cutover smoke scripts | Run on server and in CI where appropriate. |
| G5 | planned | Normalize test invocation docs | Current repo has some environment-sensitive entrypoints. |

## Acceptance Checklist

Before any show is declared migrated, all of the following must be true:

- canonical writer ownership is explicit
- queue resume works after interruption
- publish validation gates are enforced
- feed identity remains stable
- R2 object keys are deterministic
- git commit scope is allowlisted and conflict-safe
- downstream quiz and manifest state is correct
- alerting exists for repeated failure modes
- rollback steps were exercised at least once for that class of show

## Key Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Dual-writer race between Hetzner and GitHub Actions | Inconsistent feed and sidecar outputs | Enforce explicit per-show writer ownership and workflow gating. |
| Object-key instability during migration | Podcast clients treat old episodes as new | Stable object keys plus `stable_guid` preservation. |
| NotebookLM auth expiration on server | Queue stalls unattended | Auth-health checks, explicit failure state, manual refresh runbook. |
| Hidden manual prerequisites | Queue appears flaky when work is actually blocked | First-class blocked and review states. |
| Metadata references objects not yet published | Broken feed enclosures | Upload and verify before metadata commit. |
| Metadata push fails after upload | Orphaned R2 objects and inconsistent state | Rebuildable publish bundle plus orphan reconciliation tooling. |
| `personlighedspsykologi-en` rollout drift | Registry and inventory diverge | Treat registry as part of publish contract and validate alignment. |

## Decisions To Preserve

- `personal` is now the low-risk R2 storage migration example, not the first queue-owned cutover.
- `bioneuro` migrates before `personlighedspsykologi-en`.
- active published audio is now off Drive across the non-paused show surface; remaining Drive dependence is source-side or paused-feed legacy only.
- queue rollout and storage migration are one integrated program.
- Freudd production deploy remains on DigitalOcean for this program.
- upload-to-R2 precedes metadata commit because broken feed references are worse than temporary orphaned objects.

## Documentation Update Rules

- Update this file whenever scope, phase order, ownership boundaries, invariants, or migration status changes.
- Update `docs/README.md` and `TECHNICAL.md` if this file moves or its role changes.
- Update `docs/notebooklm-automation.md` and `docs/feed-automation.md` when implementation changes the operational steady state.
- Update repo-local memory when phase ownership, cutover status, or steady-state operations materially change.
