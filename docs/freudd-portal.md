# Freudd Portal

## Scope

This file is the repo-level index for Freudd. It intentionally avoids duplicating the full portal contract that already lives under `freudd_portal/`.

Naming note:

- `Freudd Portal` is the canonical name for the student-facing web layer.
- `Freudd Learning System` is the larger ecosystem that also includes the
  content engine, generation queue, preprocessing, and public podcast
  distribution surfaces downstream of the portal.

## Canonical docs

Primary entrypoints:

- [../freudd_portal/README.md](../freudd_portal/README.md) - routes, data model, subject contracts, env vars, and runtime notes.
- [../freudd_portal/docs/deploy-and-smoke.md](../freudd_portal/docs/deploy-and-smoke.md) - canonical deploy and smoke runbook.
- [../freudd_portal/docs/non-technical-overview.md](../freudd_portal/docs/non-technical-overview.md) - product-level overview.
- [../freudd_portal/docs/design-guidelines.md](../freudd_portal/docs/design-guidelines.md) - UI and interaction guidance.
- [freudd-portal-ui-audit.md](freudd-portal-ui-audit.md) - combined UI audit and tracker for fixed versus remaining portal interface work.

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
- `/subjects/bioneuro/cards/biologisk-psykologi-og-neuropsykologi` -> `200`
- `/subjects/personlighedspsykologi/cards/notebooklm-fuld-matrix-personlighedspsykologi` -> `200`

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
- optional subject flashcard registries and artifacts such as
  `shows/bioneuro/flashcards/decks.json`

Those generated files are refreshed by the feed and subject automation workflows, not manually inside the Django app.

## Flashcard Practice Contract

Flashcard practice is separate from scored Freudd quizzes. Subject-local
`shows/<subject>/flashcards/decks.json` registries expose generated deck JSON
through `/subjects/<subject_slug>/cards/<deck_slug>` and the
`/api/flashcards/<subject_slug>/<deck_slug>` API family. Logged-in users persist
self-ratings in `FlashcardReview` and written self-check answers in
`FlashcardUserAnswer`; anonymous preview users can practise cards but do not
persist ratings or written answers. The practice UI supports all cards or one
derived topic category, then `Alle`/`Ubesvarede`/`Besvarede` filters inside that
scope. Cards may include optional `Baggrund` HTML, shown collapsed after the
answer. Learner-facing flashcard text must not expose internal generation
provenance such as matrix/source/substrate labels, source-note IDs, student
notes, or local paths. The public flashcard API omits internal artifact metadata
such as `source_file` and `generated_at`; those stay in committed generation
artifacts only. Subject-page topic chips link directly into the same practice
page with a `?category=<category_slug>` deep link.

Migration note:

- The queue + object-storage migration program is tracked in [notebooklm-queue-r2-migration.md](notebooklm-queue-r2-migration.md). Freudd remains downstream of those generated artifacts; this program does not change Freudd hosting or move production deploy off DigitalOcean.

## Related docs

- [../AGENTS.md](../AGENTS.md)
- [README.md](README.md)
- [feed-automation.md](feed-automation.md)
- [notebooklm-automation.md](notebooklm-automation.md)
