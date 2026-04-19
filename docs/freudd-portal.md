# Freudd Portal

## Scope

This file is the repo-level index for Freudd. It intentionally avoids duplicating the full portal contract that already lives under `freudd_portal/`.

## Canonical docs

Primary entrypoints:

- [../freudd_portal/README.md](../freudd_portal/README.md) - routes, data model, subject contracts, env vars, and runtime notes.
- [../freudd_portal/docs/deploy-and-smoke.md](../freudd_portal/docs/deploy-and-smoke.md) - canonical deploy and smoke runbook.
- [../freudd_portal/docs/non-technical-overview.md](../freudd_portal/docs/non-technical-overview.md) - product-level overview.
- [../freudd_portal/docs/design-guidelines.md](../freudd_portal/docs/design-guidelines.md) - UI and interaction guidance.

## Repo-level integration notes

Freudd lives in:

- `freudd_portal/`

Current canonical dashboard route:

- `/settings`

Legacy route:

- `/progress` -> permanent redirect to `/settings`

Current anonymous smoke expectation:

- `/accounts/login` -> `200`
- `/settings` -> `302`
- `/progress` -> `301`

Repo policy for portal changes:

- deploy after implementation
- if models change, run `makemigrations` and `migrate`
- use the remote deploy runbook in `AGENTS.md` and `freudd_portal/docs/deploy-and-smoke.md`

## Cross-repo dependencies used by the portal

- `shows/personlighedspsykologi-en/quiz_links.json`
- `shows/personlighedspsykologi-en/content_manifest.json`
- `shows/personlighedspsykologi-en/spotify_map.json`
- `shows/personlighedspsykologi-en/reading_download_exclusions.json`
- matching subject artifacts for `bioneuro`

Those generated files are refreshed by the feed and subject automation workflows, not manually inside the Django app.

## Related docs

- [../AGENTS.md](../AGENTS.md)
- [README.md](README.md)
- [feed-automation.md](feed-automation.md)
- [notebooklm-automation.md](notebooklm-automation.md)
