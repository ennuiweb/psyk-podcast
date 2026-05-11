# Personlighedspsykologi Danish Mirror Plan

This document is the tracked implementation plan for the queue-owned Danish
mirror of the `personlighedspsykologi` podcast surface.

Status: implementation complete, deployed, queue self-heal live on Hetzner, and bilingual RSS links active
Last updated: 2026-05-11

## Scope

This rollout covers the Danish podcast mirror as a queue-owned, R2-backed,
feed-first show:

- new show slug: `personlighedspsykologi-da`
- Danish NotebookLM prompt/runtime configuration
- isolated queue output root and R2 prefix
- queue discovery, execution, publish, metadata rebuild, and downstream gating
- Danish RSS + inventory generation
- bilingual RSS description links between Danish and English counterpart episodes
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
- Link Danish and English counterparts in episode descriptions without
  hand-maintained per-episode URL maps.

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
- cross-language link layer:
  `feed.alternate_episode_links` in each show config reads the counterpart
  `episode_inventory.json` and `spotify_map.json`

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
- [x] Add bilingual episode links in Danish and English RSS descriptions
- [x] Add scheduled Spotify-map-triggered refresh for bilingual links

## Work Log

### 2026-05-09

- Created this living rollout plan and progress tracker.
- Confirmed the initial implementation scope remains feed-first and queue-owned.
- Confirmed the main risk clusters:
  English-only queue metadata assumptions, shared output-root risk, and
  incomplete `[DA]` normalization in the feed builder.
- Added a dedicated `personlighedspsykologi-da` queue adapter with isolated
  prompt config and output root.
- Added config-driven queue policy resolution so the Danish mirror can control
  Spotify sync, Freudd sidecars, content-manifest rebuilds, and downstream
  portal deploys without more hardcoded English branches.
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
- Deployed the repair follow-up on Hetzner at
  `03a0dc0af599ecf3210cdbbc91cbda917587ac76`
  (`fix: recover stale queue retries`).
- Verified post-fix live queue state:
  - `personlighedspsykologi-en` no longer has blocking `failed_retryable`
    backlog; it is back to timed work only (`downloading`, `waiting_for_artifact`,
    `retry_scheduled`)
  - `personlighedspsykologi-da` is running on the repaired queue code and has
    resumed active generation with the remaining backlog split between
    `generating`, `queued`, and `retry_scheduled`

### 2026-05-11

- Added `feed.alternate_episode_links` to both
  `personlighedspsykologi-en` and `personlighedspsykologi-da`.
- English feed descriptions now append `Dansk version: <url>` when a Danish
  counterpart exists.
- Danish feed descriptions now append `Engelsk version: <url>` when an English
  counterpart exists.
- Matching uses the same source filename identity across languages while
  ignoring language tags such as `[EN]`, `[DA]`, and `[DK]`.
- Exact short/long counterpart matches are preferred. If a language has only the
  other reading length published, short and long reading variants can fall back
  to each other. TTS, slides, and weekly overview identities do not use this
  fallback.
- Counterpart Spotify URLs are preferred; counterpart R2 audio URLs are used as
  a fallback until Spotify ingestion creates an episode URL.
- Added the `refresh-bilingual-links` job to `sync-spotify-map.yml` so both
  feeds are rebuilt after scheduled or manual Spotify-map syncs.
- Verified the pushed RSS files on `main`:
  - Danish feed: `17/17` current episodes have `Engelsk version` links
  - English feed: `15/157` current episodes have `Dansk version` links, matching
    the currently published Danish counterpart set
- Deployed commit `77d14b5cbc9adf3482536c0b09a82ba382748a95` on Hetzner.
- Verified local tests: `249 passed`.
- Verified GitHub Actions:
  - `sync-spotify-map.yml` succeeded, including `refresh-bilingual-links`
  - `generate-feed.yml` succeeded for cross-show validation

## Deployment Verification Notes

- The first live queue drain entered `generating` state immediately after
  deployment and is processing `W08L1` through the Danish NotebookLM wrapper.
- The queue service remains `activating` during the long-running drain by
  design; the timer is registered for subsequent runs and the active process
  tree matches the intended DA show commands.
- No Freudd downstream deploy target is registered for the Danish mirror, which
  is the intended phase-1 behavior for a feed-only mirror.
- Bilingual links live in RSS descriptions only. They do not create a separate
  Freudd Danish subject or cross-subject Freudd navigation contract.
- Because the Danish rollout surfaced shared-profile contention with the English
  queue, the implementation now hardens the shared queue service itself instead
  of relying on manual requeues or timer retries.
- Current live server state after the repair deploy:
  - `/opt/podcasts` is on `03a0dc0af599ecf3210cdbbc91cbda917587ac76`
  - `podcasts-notebooklm-queue@personlighedspsykologi-en.service` is active and
    progressing through download/retry windows
  - `podcasts-notebooklm-queue@personlighedspsykologi-da.service` is active and
    running the Danish generation queue
