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
- `Source Intelligence Layer` - the raw-source preprocessing subsystem, currently centered on `source_catalog.json` and future lecture/course semantic artifacts.
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
