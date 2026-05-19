# Bioneuro Anki Flashcards Integration Plan

Status: implemented, deployed, and production-smoke checked
Created: 2026-05-19

## Progress Log

- 2026-05-19: Implementation started. Initial scope remains a separate
  `flashcards` feature, with Bioneuro Anki cards as the first deck and no quiz
  progress/scoreboard integration.
- 2026-05-19: Added the deterministic Anki importer and generated the Bioneuro
  flashcard artifact from `collection.anki21b`. The generated deck has 661
  unique cards, no empty fronts/backs, and repeat imports compare byte-for-byte.
- 2026-05-19: Added the first portal implementation slice: flashcard registry
  loading, dedicated practice/content/review routes, `FlashcardReview`
  persistence, a quiz-adjacent practice template, and a Bioneuro subject-page
  entry point. Focused flashcard tests pass.
- 2026-05-19: Added a runtime reading-key fallback regression fix exposed by
  the broader subject-detail tests. Direct manifest rebuilds still report a
  missing canonical reading key, while the portal loader can use the configured
  fallback path for learner-facing pages.
- 2026-05-19: Verification passed locally: Django migrations applied,
  `manage.py check` passed, Python compile checks passed, generated flashcard
  artifact re-imported byte-for-byte, `git diff --check` passed, and 214
  relevant Freudd tests passed across flashcards, portal, and content services.
- 2026-05-19: Added non-scheduler navigation features for anki-kort: `Alle`,
  `Ubesvarede`, and `Besvarede` filters, live filter counts, current-card
  answered state, and subject-page progress phrased as `kort besvaret`.
- 2026-05-19: Added deterministic topic derivation for the imported Anki cards
  and replaced the broad deck title on the subject page with a compact category
  preview and category card counts.
- 2026-05-19: Opened the anki-kort practice page and read API for anonymous
  preview use. Anonymous learners can work through cards in browser state, with
  a bottom-page warning that progress is not saved unless they log in.
- 2026-05-19: Refined the anki-kort practice UI: metadata is consolidated,
  `Ikke vurderet endnu`/`Vurderet: ...` replaces the old card-state wording,
  learners can optionally open a local `Skriv svar` self-check field before
  revealing the official answer, rating controls are visually separated by
  semantic difficulty, and the anonymous preview warning is quiet inline text
  rather than a prominent info box.
- 2026-05-19: Added topic-scope practice and persisted written self-check
  answers. Learners can practise all cards or a single derived topic category;
  logged-in users' `Skriv svar` text is saved separately from
  `FlashcardReview`, while anonymous preview answers remain browser-only.

## Goal

Integrate the Bioneuro Anki deck into Freudd as learner-facing card practice
while preserving the meaning and invariants of the existing Freudd quiz system.

Initial source deck:

- Local file: `Biologisk-psykologi-og-Neuropsykologi.apkg`
- Observed contents: 661 Basic Anki cards, one default deck, no tags, no media
- Card shape: `Front` question plus `Back` answer/explanation HTML

## Core Product Decision

Treat Anki cards as a first-class Freudd learning artifact named `flashcards`.
Do not convert them into normal Freudd quizzes.

The existing quiz system has semantics that do not fit open-recall cards:

- strict 8-character quiz ids
- multiple-choice `answerOptions`
- `QuizProgress`
- per-question timer and cooldown
- score, XP, quiz history, and scoreboard behavior
- generated `quiz_links.json` and lecture-content manifest linkage

Flashcards should reuse the visual language of the quiz view where useful, but
must not participate in quiz scoring, cooldowns, leaderboard rows, or
quiz-driven lecture completion.

## Non-goals For MVP

- No attempt to implement a complete Anki scheduling clone.
- No scoreboard, speed bonus, XP, or quiz history integration.
- No automatic lecture/chapter mapping unless reliable source metadata exists.
- No direct rendering of unsanitized Anki HTML.
- No hard dependency on the original `.apkg` being present at runtime.

## Target User Experience

On `/subjects/bioneuro`, the learner sees a compact `anki-kort` entry point
for the imported deck. Opening it starts a focused practice flow:

1. choose `Alle`, `Ubesvarede`, or `Besvarede`
2. optionally scope the session to all cards or one derived topic category
3. show card front plus `Ikke vurderet endnu` or `Vurderet: <rating>` state
4. learner optionally opens `Skriv svar` and writes a self-check answer
5. learner clicks `Vis svar`
6. show sanitized answer/explanation
7. learner self-rates: `Igen`, `Svaert`, `Godt`, `Let`
8. update the answered state and advance within the active scope/filter

For authenticated users, the `Skriv svar` field is persisted as private
open-recall history in `FlashcardUserAnswer`. It is separate from
`FlashcardReview`, does not affect quiz progress, and can be cleared by saving an
empty answer. Anonymous preview users keep written answers only in browser state.

The experience should feel native to Freudd and visually related to the quiz
view, but the language should clearly say card practice, not quiz.

## Phase 1: Deterministic Import Pipeline

Add an importer script that converts `.apkg` into a checked, deterministic JSON
artifact.

Proposed paths:

- script: `scripts/import_anki_flashcards.py`
- registry: `shows/bioneuro/flashcards/decks.json`
- deck artifact:
  `shows/bioneuro/flashcards/biologisk-psykologi-og-neuropsykologi.json`
- optional source storage, only if licensing/storage policy allows:
  `shows/bioneuro/flashcards/source/Biologisk-psykologi-og-Neuropsykologi.apkg`

Artifact root fields:

- `version`
- `subject_slug`
- `deck_slug`
- `title`
- `source_file`
- `source_sha256`
- `generated_at`
- `card_count`
- `categories`
- `cards`

Card fields:

- `card_id`
- `front_text`
- `back_html_sanitized`
- `back_text`
- `source_note_id`
- `source_card_id`
- `source_ord`
- `tags`
- `category_slug`
- `category_title`

Card id rule:

- Prefer a stable id based on Anki `card_id` plus `source_note_id`.
- Include a normalized-content hash in the artifact for drift detection.
- If a later import lacks stable source ids, fall back to a hash of normalized
  `front_text + back_text`, and document that progress migration may be needed.

Importer requirements:

- Read compressed `collection.anki21b` when present.
- Fall back to `collection.anki2` only if it contains the real cards, not Anki's
  compatibility placeholder.
- Produce stable ordering.
- Emit deterministic JSON formatting.
- Fail closed when expected Anki tables or fields are missing.
- Print summary: deck count, note count, card count, skipped rows, output path.

## Phase 2: HTML Safety And Content Hygiene

Sanitize all Anki `Back` HTML before it reaches the browser.

Allowed examples:

- `p`, `div`, `span`, `strong`, `em`, `b`, `i`, `u`
- `br`, `ul`, `ol`, `li`
- `sub`, `sup`, `code`

Disallowed:

- `script`, `style`, `iframe`, `object`, `embed`
- event handlers such as `onclick`
- inline JavaScript URLs
- external media embeds
- arbitrary inline styles unless a narrow allowlist is deliberately chosen

The importer should also store `back_text` so search, previews, tests, and
future export/scheduling logic do not need to parse HTML.

## Phase 3: Deck Registry

Add `shows/bioneuro/flashcards/decks.json` as the subject-local deck registry.

Suggested shape:

```json
{
  "version": 1,
  "subject_slug": "bioneuro",
  "decks": [
    {
      "deck_slug": "biologisk-psykologi-og-neuropsykologi",
      "title": "Biologisk psykologi og neuropsykologi",
      "description": "Imported Anki cards for Bioneuro.",
      "artifact_path": "shows/bioneuro/flashcards/biologisk-psykologi-og-neuropsykologi.json",
      "card_count": 661,
      "enabled": true
    }
  ]
}
```

The registry avoids hardcoding one deck in the view layer and leaves room for
future Bioneuro or cross-subject card decks.

## Phase 4: Backend Service Layer

Add a dedicated flashcard service module rather than expanding the already broad
quiz services module.

Proposed module:

- `freudd_portal/quizzes/flashcard_services.py`

Responsibilities:

- resolve a subject's deck registry
- validate deck slugs and artifact paths
- load and cache deck artifacts
- expose deck summary, card list, and card lookup helpers
- return clean domain errors for missing or malformed decks
- never mutate quiz artifacts or quiz progress

This service should use subject path resolution patterns where useful, but it
should remain independent from `quiz_links.json`.

## Phase 5: Routes And Views

Add dedicated routes:

- `GET /subjects/<subject_slug>/cards/<deck_slug>`
- `GET /api/flashcards/<subject_slug>/<deck_slug>`
- `POST /api/flashcards/<subject_slug>/<deck_slug>/answer`
- `POST /api/flashcards/<subject_slug>/<deck_slug>/review`

Route behavior:

- Unknown subject: 404.
- Unknown or disabled deck: 404.
- Malformed deck artifact: 500 with a logged server error, not partial UI.
- Anonymous read access is allowed for the practice page and card payload in
  preview mode. In-page preview ratings are not persisted.
- The optional `Skriv svar` answer is persisted only for authenticated users via
  the answer API. Anonymous preview drafts stay in browser state.
- Review POST accepts `answer_text` as a convenience so a rating click can flush
  the current written answer and rating together, but the written answer remains
  separate from `FlashcardReview`.
- Review POST requires authentication for persisted progress.

Template:

- `freudd_portal/templates/quizzes/flashcard_practice.html`

The template may share CSS conventions with the quiz wrapper, but must not load
or submit quiz state APIs.

## Phase 6: Progress Model

Add separate persisted card progress.

Models:

- `FlashcardReview`
- `FlashcardUserAnswer`

Fields:

- `user`
- `subject_slug`
- `deck_slug`
- `card_id`
- `rating`: `again | hard | good | easy`
- `review_count`
- `last_reviewed_at`
- `next_review_at`, nullable for MVP
- `created_at`
- `updated_at`

Constraint:

- unique `(user, subject_slug, deck_slug, card_id)`

Indexes:

- `(user, subject_slug, deck_slug)`
- `(user, next_review_at)`
- `(subject_slug, deck_slug, card_id)`

`FlashcardUserAnswer` fields:

- `user`
- `subject_slug`
- `deck_slug`
- `card_id`
- `answer_text`
- `created_at`
- `updated_at`

`FlashcardUserAnswer` uses the same unique key as `FlashcardReview`:
`(user, subject_slug, deck_slug, card_id)`. Saving an empty answer deletes the
row, and answer rows do not count as reviewed cards.

MVP review semantics:

- `again`: user did not know the card
- `hard`: user barely knew it
- `good`: user knew it
- `easy`: user knew it confidently

The first implementation can use these ratings only for progress summaries and
ordering. `next_review_at` exists to support spaced repetition later without
another schema change.

## Phase 7: Practice Ordering

MVP ordering should be predictable and simple:

- unauthenticated: deck order, with optional local shuffle in browser state
- authenticated: prioritize unseen cards, then cards rated `again`, then older
  reviewed cards

Avoid complex scheduling until there is real usage feedback. The data model
should allow a later scheduler to be introduced behind the same API.

## Phase 8: Subject Page Integration

Add a separate `anki-kort` section or compact module to the Bioneuro subject
page.

Show:

- derived topic categories and card counts
- card count
- user's reviewed count and confidence summary when logged in
- CTA: `Oev kort`

Do not place the deck inside `Quiz for alle kilder`. The learner should not
confuse self-rated cards with scored quizzes.

## Phase 9: Tests

Importer tests:

- extracts 661 cards from the current `.apkg`
- output is deterministic across repeated runs
- compatibility placeholder in `collection.anki2` is not mistaken for the deck
- unsupported/malformed Anki package fails clearly

Sanitizer tests:

- strips scripts and event handlers
- strips JavaScript URLs
- preserves allowed formatting
- produces non-empty `back_text`

Service tests:

- loads enabled deck from registry
- rejects unknown subject/deck
- rejects path traversal in artifact paths
- rejects artifact subject/deck mismatch
- caches cleanly and can be invalidated in tests

View/API tests:

- practice page renders with deck metadata
- practice page exposes the topic-scope selector
- flashcard API returns cards without unsafe HTML
- answer POST requires authentication
- answer POST creates, updates, clears `FlashcardUserAnswer`, and does not mark
  the card reviewed
- review POST requires authentication
- review POST creates then updates `FlashcardReview`
- review POST can flush a written answer without coupling it to quiz progress
- invalid rating is rejected
- subject page shows the Bioneuro deck link

Regression tests:

- quiz history remains sourced from `QuizProgress`
- leaderboard ignores flashcard reviews
- quiz completion totals do not include flashcards
- existing Bioneuro quiz links still load

## Phase 10: Documentation

Update docs when implementation lands:

- `freudd_portal/README.md`: add flashcard routes, model, and product contract
- `freudd_portal/docs/non-technical-overview.md`: describe card practice
- `docs/freudd-portal.md`: add repo-level integration note if useful
- this plan: mark completed phases or replace with final architecture notes

If the deck source file is committed, document why the binary source is allowed
to live in the repo. If it is not committed, document where the canonical source
deck lives and keep the `source_sha256` in the generated artifact.

## Phase 11: Deployment And Smoke Checks

Because this is Freudd portal work, the implementation is complete only after
deployment succeeds.

Before deploy:

- run importer
- run formatter/lint if touched files require it
- run `makemigrations` and `migrate` locally as appropriate
- run focused Django tests for flashcards, subject detail, quiz history, and
  leaderboard
- verify generated artifacts are committed intentionally

Deploy:

- commit and push to `origin/main`
- deploy `freudd-portal` using the repo runbook
- run migrations on production
- restart `freudd-portal.service`

Smoke checks:

- `/accounts/login` returns 200
- `/settings` redirects or renders as expected
- `/subjects/bioneuro` renders
- `/subjects/bioneuro/cards/<deck_slug>` renders
- authenticated answer POST persists one written answer without marking a review
- authenticated review POST persists one review
- quiz route `/q/<known-bioneuro-quiz-id>.html` still works

## Rollout Strategy

Recommended implementation order:

1. Importer, sanitizer, generated artifact, and deck registry.
2. Flashcard service layer and tests.
3. Read-only card practice page and API.
4. Progress model, migration, and review API.
5. Subject page integration and user progress summary.
6. Docs, deploy, and smoke checks.

This order keeps the highest-risk seams isolated:

- conversion risk is handled before UI work
- rendering safety is handled before browser exposure
- persistence is added only after the read path works
- subject integration happens after the standalone practice flow is stable

## Failure Modes To Design For

- Deck file missing in production.
- Deck artifact malformed after manual edit.
- Card ids change after re-import.
- Unsafe Anki HTML slips into source data.
- Browser local state references deleted cards.
- Large deck payload makes first load slow.
- User reviews a card while deck has been updated.
- Future lecture mapping creates duplicate or orphaned cards.

Mitigations:

- validate artifacts at import time and service load time
- keep stable card ids and source hashes
- sanitize HTML before commit-time artifact generation
- make API tolerant of unknown local card ids
- paginate or chunk API responses if 661 cards is too heavy in practice
- keep review rows keyed by stable `card_id`, not deck position
- add migration tooling if a future re-import changes ids

## Acceptance Criteria

The feature is ready when:

- Bioneuro has a visible card-practice entry point.
- All 661 imported cards can be practiced in Freudd.
- No card content renders unsafe HTML.
- Logged-in users can store self-rated progress.
- Logged-in users can store and clear written self-check answers.
- Learners can practise all cards or a single topic category.
- Flashcard progress is separate from quiz progress.
- Quiz history, quiz completion, XP, cooldowns, and scoreboard remain unchanged.
- The implementation is documented, tested, deployed, and smoke checked.
