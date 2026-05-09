# Personlighedspsykologi Danish Mirror Plan

This document is the tracked implementation plan for the queue-owned Danish
mirror of the `personlighedspsykologi` podcast surface.

Status: implementation complete, deployed, and draining on Hetzner
Last updated: 2026-05-09

## Scope

This rollout covers the Danish podcast mirror as a queue-owned, R2-backed,
feed-first show:

- new show slug: `personlighedspsykologi-da`
- Danish NotebookLM prompt/runtime configuration
- isolated queue output root and R2 prefix
- queue discovery, execution, publish, metadata rebuild, and downstream gating
- Danish RSS + inventory generation
- Hetzner queue runtime install for the new show

This rollout does not add Freudd portal parity as part of the initial mirror.
Portal sidecars remain explicitly disabled unless a later change introduces a
separate Danish Freudd subject contract.

## Objectives

- Reuse the existing `personlighedspsykologi` source and preprocessing
  substrate without duplicating subject-owned inputs unnecessarily.
- Publish a clean Danish RSS feed without leaking `[DA]` tags into public
  titles or descriptions.
- Prevent English and Danish queue jobs from sharing output roots or publish
  state implicitly.
- Replace remaining English-only queue assumptions with show-config-driven
  behavior where Danish rollout safety depends on it.
- Keep the implementation maintainable for future additional language mirrors.

## Architecture Decision

The Danish mirror is implemented as a separate show surface over the same
subject:

- shared subject substrate:
  `shows/personlighedspsykologi-en/auto_spec.json`,
  `shows/personlighedspsykologi-en/episode_metadata.json`,
  important text docs, and the existing generation scripts
- Danish show-local publication artifacts:
  `shows/personlighedspsykologi-da/*`
- Danish show-local runtime layer:
  `notebooklm-podcast-auto/personlighedspsykologi-da/*`

This keeps schedule and source identity aligned across mirrors while isolating
public feed outputs and queue runtime state.

## Progress

- [x] Create a dedicated tracked rollout document
- [x] Generalize queue adapters for mirror-specific prompt config and output root
- [x] Generalize queue metadata/downstream gating for non-portal Danish rollout
- [x] Fix feed language-tag normalization for `[DA]`
- [x] Add Danish show configs and runtime docs
- [x] Add tests for Danish adapter, metadata gating, publish isolation, and feed normalization
- [x] Run local verification
- [x] Commit and push
- [x] Deploy Hetzner queue runtime for `personlighedspsykologi-da`
- [x] Run post-deploy smoke checks

## Work Log

### 2026-05-09

- Created this living rollout plan and progress tracker.
- Confirmed the initial implementation scope remains feed-first and queue-owned.
- Confirmed the main risk clusters:
  English-only queue metadata assumptions, shared output-root risk, and
  incomplete `[DA]` normalization in the feed builder.
- Added a dedicated `personlighedspsykologi-da` queue adapter with isolated
  prompt config and output root.
- Added config-driven queue policy resolution so the Danish mirror can disable
  Spotify, Freudd sidecars, content-manifest rebuilds, and downstream portal
  deploys without more hardcoded English branches.
- Added a lightweight prompt-config inheritance layer so the Danish runtime can
  reuse the shared `personlighedspsykologi` prompt system while overriding only
  the language surface.
- Added the Danish show config and runtime wrapper folders plus an initial empty
  R2 media manifest.
- Expanded feed normalization so `[DA]` and `(DK)` tags are stripped from
  public titles/descriptions and cross-language lookup matching stays stable.
- Added regression tests for the Danish adapter, metadata gating, publish
  isolation, downstream gating, CLI JSON serialization, and DA feed-name
  normalization.
- Verified locally with:
  - targeted pytest suite: `137 passed`
  - `generate_week.py --dry-run` using the Danish prompt config and output root
  - queue `discover --enqueue` and `run-dry` for `personlighedspsykologi-da`
- Committed and pushed the rollout on `main` at
  `75a78e46c5132391c647af3006c9b8153e475355`
  (`feat: add danish personlighedspsykologi mirror` after rebase).
- Triggered `generate-feed.yml` on `main`; the workflow completed successfully.
- Deployed the updated repo on Hetzner under `/opt/podcasts`, installed the new
  `personlighedspsykologi-da` environment file, reloaded systemd units, enabled
  the new queue timer, and started the show service.
- Verified hosted runtime state:
  - `/opt/podcasts` is on commit `75a78e46c5132391c647af3006c9b8153e475355`
  - `podcasts-notebooklm-queue@personlighedspsykologi-da.timer` is active
  - the Danish queue report shows `22` jobs discovered and enqueued
  - the live service is running the expected Danish
    `generate_week.py` and `generate_podcast.py` commands against
    `notebooklm-podcast-auto/personlighedspsykologi-da/output`
  - `run-dry` on-host resolves the Danish prompt config and strict DA output
    root correctly
- Discovered and fixed an existing queue runtime weakness during smoke testing:
  shared NotebookLM profile exhaustion and source-ingestion stalls could leave
  older jobs in `failed_retryable`, which then caused `serve-show` to stop on a
  mixed blocked+timed backlog.
- Added a queue-level self-heal path so stale retryable failures are converted
  back into `retry_scheduled` automatically, and added explicit retry
  classification for `Sources not ready after waiting`.

## Deployment Verification Notes

- The first live queue drain entered `generating` state immediately after
  deployment and is processing `W08L1` through the Danish NotebookLM wrapper.
- The queue service remains `activating` during the long-running drain by
  design; the timer is registered for subsequent runs and the active process
  tree matches the intended DA show commands.
- No Freudd downstream deploy target is registered for the Danish mirror, which
  is the intended phase-1 behavior for a feed-only mirror.
- Because the Danish rollout surfaced shared-profile contention with the English
  queue, the implementation now hardens the shared queue service itself instead
  of relying on manual requeues or timer retries.
