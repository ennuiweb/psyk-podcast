# NotebookLM Queue Current State

Last updated: 2026-05-03

This document is the current-state checkpoint for the Hetzner-owned NotebookLM queue + R2 migration program. It is intentionally separate from the canonical migration plan in [notebooklm-queue-r2-migration.md](notebooklm-queue-r2-migration.md).

Use this file for:

- what has actually shipped
- what is verified
- what is still missing before full autonomous Hetzner ownership
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

The queue does not yet own:

- Hetzner `systemd` deployment and timer ownership

## Verified in this session

Local verification completed:

- Notebook-capacity tests passed after the reclaim-on-create-notebook fix
- queue publish tests passed after R2 upload implementation
- queue metadata tests passed after repo rebuild implementation
- full `tests/notebooklm_queue` suite passed after the latest repo-publish hardening and downstream sync work

Required repo workflows completed successfully for the latest queue commits:

- `a5b2748` -> Actions run `25183786210`
- `ad01a4f` -> Actions run `25212535606`
- `532ac58` -> Actions run `25213172226`
- `9ef94cf` -> Actions run `25214094593`

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
- `intro-vt`: legacy workflow
- `personal`: legacy workflow
- `personlighedspsykologi-en`: legacy workflow
- `social-psychology`: legacy workflow

## Immediate missing steps before full autonomous ownership

1. Replace the temporary `r2.dev` public base URL with the intended production audio domain.
2. Add Hetzner runtime ownership:
   - `systemd` service
   - timer
   - env/secrets contract
   - failure reporting
3. Decide the next migration target after `bioneuro`:
   - `personal` for lower-risk storage migration
   - `personlighedspsykologi-en` for the next full queue-owned show

## Recommended reading order

- [notebooklm-queue-r2-migration.md](notebooklm-queue-r2-migration.md) - canonical long-term plan and backlog
- [notebooklm-automation.md](notebooklm-automation.md) - subsystem layout and CLI entrypoints
- [feed-automation.md](feed-automation.md) - current feed pipeline and provider model
