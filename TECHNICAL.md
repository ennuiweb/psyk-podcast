# psyk-podcast

This file is the compact technical index for the repo. Detailed operational docs now live under [docs/](docs/README.md) so the root stays maintainable.

## What this repo contains

- `shows/<show-slug>/` - feed configs, metadata, docs, and generated RSS for each show.
- `podcast-tools/` - shared feed-generation and Drive helper scripts.
- `notebooklm-podcast-auto/` - subject-oriented NotebookLM automation and the tracked `notebooklm-py` submodule.
- `freudd_portal/` - Django portal for auth, quizzes, subject content, and gamification.

## Start here

- [docs/feed-automation.md](docs/feed-automation.md) - feed pipeline, GitHub Actions, Apps Script triggers, and feed hosting.
- [docs/notebooklm-automation.md](docs/notebooklm-automation.md) - NotebookLM subject wrappers, mirrors, and output conventions.
- [docs/freudd-portal.md](docs/freudd-portal.md) - repo-level Freudd integration notes and canonical portal docs.
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
