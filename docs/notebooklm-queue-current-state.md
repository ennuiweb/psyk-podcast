# NotebookLM Queue Current State

Last updated: 2026-05-01

This document is the current-state checkpoint for the Hetzner-owned NotebookLM queue + R2 migration program. It is intentionally separate from the canonical migration plan in [notebooklm-queue-r2-migration.md](notebooklm-queue-r2-migration.md).

Use this file for:

- what has actually shipped
- what is verified
- what is still missing before production cutover
- the current boundary between queue-owned publication and legacy Drive-owned publication

## Implemented

The following queue milestones are implemented on `main`:

- `722cb93` - hardened the canonical migration plan
- `0c44a3c` - queue core
- `ce1db7f` - discovery + dry-run planning
- `0d51f31` - real generate/download execution
- `2ce0606` - publish-bundle preparation
- `2092b46` - NotebookLM notebook-capacity recovery by deleting the oldest owned notebook and retrying once
- `a5b2748` - R2 object upload for approved queue bundles
- `ad01a4f` - repo metadata rebuild from uploaded objects
- current working tree after `ad01a4f` - queue-owned quiz sync is wired into metadata rebuild before RSS regeneration, and `push-repo` now commits and pushes allowlisted generated artifacts

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
  - rebase against `origin/main`
  - push to `main`
  - persisted repo commit SHA in queue job artifacts

## Current state-machine boundary

Successful jobs can now advance through:

- `awaiting_publish`
- `approved_for_publish`
- `objects_uploaded`
- `committing_repo_artifacts`
- `repo_pushed`

That means the queue currently owns:

- generation
- download
- local artifact validation
- object upload
- quiz-link refresh
- repo metadata regeneration
- allowlisted repo commit/push

The queue does not yet own:

- downstream sync / final publish orchestration
- Hetzner `systemd` deployment and timer ownership

## Verified in this session

Local verification completed:

- Notebook-capacity tests passed after the reclaim-on-create-notebook fix
- queue publish tests passed after R2 upload implementation
- queue metadata tests passed after repo rebuild implementation
- full `tests/notebooklm_queue` suite passed after the latest quiz-sync and repo-publish work

Required repo workflows completed successfully for the latest queue commits:

- `a5b2748` -> Actions run `25183786210`
- `ad01a4f` -> Actions run `25212535606`

## Still true about live production

No active show has been cut over to R2 yet.

As of 2026-05-01, all active `shows/*/config.github.json` files still resolve to `storage.provider = "drive"`:

- `berlingske`
- `bioneuro`
- `intro-vt`
- `personal`
- `personlighedspsykologi-en`
- `social-psychology`

So current production ownership is still:

- live feeds: Drive-backed
- migration path: queue + R2 capable, but not yet cut over

## Immediate missing steps before a real cutover

1. Decide and validate the production public audio URL/domain for R2-backed enclosures.
2. Add downstream completion orchestration after `repo_pushed`.
3. Migrate one low-risk show first, still planned as `personal`.
4. Remove dual-writer risk for any migrated show by ensuring GitHub Actions no longer independently regenerates that show’s artifacts.
5. Add Hetzner runtime ownership:
   - `systemd` service
   - timer
   - env/secrets contract
   - failure reporting

## Recommended reading order

- [notebooklm-queue-r2-migration.md](notebooklm-queue-r2-migration.md) - canonical long-term plan and backlog
- [notebooklm-automation.md](notebooklm-automation.md) - subsystem layout and CLI entrypoints
- [feed-automation.md](feed-automation.md) - current feed pipeline and provider model
