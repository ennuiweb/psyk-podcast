# Personlighedspsykologi Danish Mirror Plan

This document is the tracked implementation plan for the queue-owned Danish
mirror of the `personlighedspsykologi` podcast surface.

Status: implementation complete locally; deploy in progress
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
- [ ] Commit and push
- [ ] Deploy Hetzner queue runtime for `personlighedspsykologi-da`
- [ ] Run post-deploy smoke checks

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
