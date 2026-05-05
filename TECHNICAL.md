# psyk-podcast

This file is the compact technical index for the repo. Detailed operational docs now live under [docs/](docs/README.md) so the root stays maintainable.

## What this repo contains

- `shows/<show-slug>/` - feed configs, metadata, docs, and generated RSS for each show.
- `podcast-tools/` - shared feed-generation and Drive helper scripts.
- `notebooklm-podcast-auto/` - subject-oriented NotebookLM automation and the tracked `notebooklm-py` submodule.
- `notebooklm_queue/` - durable queue/store primitives and CLI for the Hetzner-owned NotebookLM migration path.
- `freudd_portal/` - Django portal for auth, quizzes, subject content, and gamification.
- `spotify_transcripts/` - local-first Spotify transcript downloader and normalizer for mapped show episodes.

## Naming

Use this vocabulary when referring to the system:

- `Freudd Learning System` - the whole repo-level ecosystem: portal, content generation, queueing, publication, and public podcast surfaces.
- `Freudd Portal` - the student-facing `freudd.dk` web layer in `freudd_portal/`.
- `Freudd Content Engine` - the course-material engine whose purpose is to create the best possible conditions for high-quality learning material, across source preprocessing, course framing, prompt construction, generation workflows, and show metadata/artifacts.
- `Freudd Generation Queue` - the Hetzner-owned queue/orchestration runtime in `notebooklm_queue/`.
- `Source Intelligence Layer` - the raw-source preprocessing subsystem, now centered on `source_catalog.json`, `lecture_bundles/`, `course_glossary.json`, `course_theory_map.json`, and related weighting/staleness artifacts.
- `Course Context Layer` - the deterministic course/lecture framing compiler in `notebooklm_queue/course_context.py`.
- `Prompt Assembly Layer` - the shared prompt construction layer in `notebooklm_queue/prompting.py`.
- `Distribution Layer` - feed, manifest, Spotify, and publication outputs.
- `Freudd Podcast Network` - the public podcast surfaces exposed through RSS, Spotify, and podcast apps.

## Start here

- [docs/feed-automation.md](docs/feed-automation.md) - feed pipeline, GitHub Actions, Apps Script triggers, and feed hosting.
- [docs/freudd-learning-system-architecture.md](docs/freudd-learning-system-architecture.md) - system-wide architecture map, maturity assessment, and recommended next moves.
- [docs/notebooklm-automation.md](docs/notebooklm-automation.md) - NotebookLM subject wrappers, mirrors, and output conventions.
- [docs/notebooklm-queue-operations.md](docs/notebooklm-queue-operations.md) - Hetzner queue runtime install and operations runbook.
- [docs/notebooklm-queue-r2-migration.md](docs/notebooklm-queue-r2-migration.md) - cross-cutting implementation plan for the Hetzner queue and R2/object-storage migration.
- [docs/notebooklm-queue-current-state.md](docs/notebooklm-queue-current-state.md) - current shipped state of the queue + R2 migration work.
- [docs/freudd-portal.md](docs/freudd-portal.md) - repo-level Freudd integration notes and canonical portal docs.
- [docs/spotify-transcripts.md](docs/spotify-transcripts.md) - Spotify transcript auth, artifact model, and sync flow.
- [freudd_portal/README.md](freudd_portal/README.md) - full Freudd product and runtime contract.
- [AGENTS.md](AGENTS.md) - repo-local execution and deploy policy.

## Intelligence Principle

The `Freudd Content Engine` should be understood as a decomposed substitute for
a hypothetical model that could reason over an entire course in one pass.

That means the system needs:

- bottom-up flow from source files into lecture and course artifacts
- top-down flow from course arc and theory structure back into local selection
- sideways flow across lectures, concepts, and theories

This is a deliberate design principle, not accidental complexity. The engine
should approximate whole-course reasoning through explicit intermediate
artifacts, not by collapsing everything into opaque prompt text.

Current direction:

- The main `personlighedspsykologi` maturity task is course preprocessing, not
  more prompt tuning.
- The recursive substrate layer is now implemented as code: source
  cards -> lecture substrates -> course synthesis -> downward lecture revision
  -> compact podcast substrates.
- Python should orchestrate, cache, validate, and write artifacts; Gemini 3.1
  Pro should do most semantic interpretation; NotebookLM prompts should consume
  only compact selected substrate.
- The concrete code plan for testing readiness is tracked in
  `shows/personlighedspsykologi-en/docs/preprocessing-system.md` and summarized
  in `docs/notebooklm-automation.md`.

Operational note:

- For `personlighedspsykologi`, the canonical local rebuild entrypoint for the
  full `Source Intelligence Layer` is
  `./.venv/bin/python scripts/build_personlighedspsykologi_source_intelligence.py`.
- For the Gemini-derived recursive layer, the canonical local entrypoint is
  `./.venv/bin/python scripts/build_personlighedspsykologi_recursive_source_intelligence.py`.
  First test batch: `--lectures W05L1,W06L1`; full run: `--all`.
- Source cards and lecture substrates upload the actual source PDFs to Gemini
  by default. The lecture-pass escape hatch is
  `--no-raw-lecture-source-uploads`.
- Recursive artifact validation and progress tracking lives in
  `shows/personlighedspsykologi-en/source_intelligence/index.json`, rebuilt by
  `./.venv/bin/python scripts/check_personlighedspsykologi_recursive_artifacts.py --allow-partial`.
- Runtime status as of 2026-05-05: the Gemini key is available from the local
  secret store and `--preflight-only` succeeds for `gemini-3.1-pro-preview`.
  Real recursive LLM artifacts have not been generated yet; the next step is
  the first live `W05L1,W06L1` batch and quality review.
- The course-specific interpretation policy for that layer lives in
  `shows/personlighedspsykologi-en/source_intelligence_policy.json` and is the
  canonical place to tune how `grundbog`, lecture slides, seminar slides, and
  exercise slides should count inside preprocessing.

## Current operational truths

- Feed output lives at `shows/<show-slug>/feeds/rss.xml`.
- GitHub Actions feed generation is driven by `.github/workflows/generate-feed.yml`.
- Freudd uses `/settings` as the canonical dashboard route.
- `/progress` is legacy and permanently redirects to `/settings`.
- Freudd smoke expectation for anonymous requests is:
  - `/accounts/login` -> `200`
  - `/settings` -> `302`
  - `/progress` -> `301`

## Maintenance rule

If a topic grows beyond a short repo-level summary, move the detail into `docs/` or the local docs folder for the owning subsystem instead of expanding this file again.
