# Flashcard Review Implementation Plan

Created: 2026-05-26

## Purpose

This plan turns the flashcard architecture into an executable review workflow.
It covers the work from the current state through a finished, documented
quality comparison and promotion recommendation.

The goal is to decide what to do with:

- the canonical matrix deck
- the first NotebookLM variants deck
- the independent NotebookLM variants deck
- the 259 full all-cluster NotebookLM candidates

The goal is not to maximize card count. The goal is to improve Freudd practice
quality, coverage, wording, and oral-exam usefulness while keeping the result
maintainable.

## Current State

Committed learner-facing decks:

- `eksamensmatrix-personlighedspsykologi`: 152 cards
- `notebooklm-varianter-personlighedspsykologi`: 79 cards
- `notebooklm-uafhaengige-varianter-personlighedspsykologi`: 74 cards

Local candidate pool:

- run ID: `full-matrix-20260526-notebooklm-independent`
- candidates: 259 normalized NotebookLM cards
- status totals: 176 `candidate`, 58 `needs_review`, 25 `auto_rejected`

Active architecture:

- `shows/personlighedspsykologi-en/docs/flashcard-architecture-and-review-plan.md`

Implementation status, 2026-05-26:

- Phases 0-4 are implemented.
- Deterministic comparison script:
  `scripts/compare_personlighedspsykologi_flashcard_pools.py`
- Pool-level Gemini review script:
  `scripts/review_personlighedspsykologi_flashcard_pool_with_gemini.py`
- Supporting module:
  `notebooklm_queue/personlighedspsykologi_flashcard_review.py`
- Focused tests:
  `tests/test_personlighedspsykologi_flashcard_review.py`
- Local generated report:
  `notebooklm-podcast-auto/personlighedspsykologi/flashcard_lab/reports/flashcard-pool-review-20260526/flashcard-pool-comparison.md`
- Local generated Gemini review:
  `notebooklm-podcast-auto/personlighedspsykologi/flashcard_lab/reports/flashcard-pool-review-20260526/gemini_review/flashcard-pool.gemini-review.md`
- Committed final summary:
  `shows/personlighedspsykologi-en/docs/flashcard-review-final-report-20260526.md`

Outcome:

- deterministic report normalized 564 cards across the three committed decks
  and the 259 full-run NotebookLM candidates
- deterministic unknown rate was 0.0427, so Gemini was allowed
- Gemini reviewed the bounded 80-card shortlist in one call
- Gemini rejected all 80 shortlisted NotebookLM candidates
- no promotion or deck mutation is recommended from this review

## Technical Fellow Critique

The previous plan had the right direction, but it needed tighter operational
contracts before implementation.

Main issues:

- Generated report ownership was under-specified. `flashcard_lab/runs/*` is
  ignored today, but `flashcard_lab/reports/` is not yet guaranteed ignored.
- The full NotebookLM candidate pool is local generated material. Any review
  script must fail clearly if the run is missing instead of silently reviewing
  only committed decks.
- The classifier could create false precision if it forces ambiguous cards
  into a topic or family. `unknown` and confidence metadata must be first-class
  outputs.
- A single duplicate score is not enough. The report must distinguish exact
  duplicates, near duplicates, same-slot collisions, and useful alternative
  wording.
- Gemini review can become too large or too shallow if the shortlist is not
  bounded. The plan needs an explicit shortlist budget and fallback.
- Promotion strategy must not be a side effect of the review script. Review,
  LLM judgment, and deck mutation need separate artifacts and separate commands.
- The final result needs a reproducible manifest of input paths, hashes, counts,
  tool versions, thresholds, and model names so future sessions can understand
  what was actually reviewed.

The final plan below addresses those issues by adding a preflight phase,
explicit stop gates, report ownership rules, bounded LLM input, and promotion
separation.

## Final Deliverables

The review is finished when these deliverables exist:

1. deterministic comparison script
2. generated JSON comparison report
3. generated Markdown review report
4. curated candidate subset for Gemini review
5. single-call Gemini review artifact, if the deterministic report justifies it
6. final promotion recommendation doc
7. one optional promotion artifact or deck update, only if review supports it

The review may legitimately finish with "do not promote more cards yet" if the
report shows insufficient added value.

## Final Operating Principles

- Treat committed decks as learner-facing artifacts and full-run NotebookLM
  candidates as local review material.
- Make each stage reproducible from explicit inputs and hashes.
- Prefer explicit `unknown` over confident but wrong classification.
- Separate diagnosis from judgment, and judgment from promotion.
- Stop before Gemini if deterministic classification or candidate coverage is
  not trustworthy.
- Stop before promotion unless a decision artifact clearly supports a concrete
  deck strategy.
- Keep generated reports local; commit only scripts, tests, docs, and final
  summarized decisions.

## Phase 0: Preflight And Workspace Contract

Before writing comparison code, establish the review workspace contract.

Required checks:

- verify all three committed deck files exist and validate as Freudd decks
- verify the full-run candidate directory exists for
  `full-matrix-20260526-notebooklm-independent`
- verify all five expected candidate JSON files are present
- verify candidate counts match the recorded total of 259
- verify `flashcard_lab/reports/` is ignored, or add a local `.gitignore`
  entry before generating reports
- record input file SHA-256 hashes in the comparison report manifest
- record the code version, thresholds, and review run ID

Recommended review run ID:

- `flashcard-pool-review-20260526`

Failure behavior:

- missing local candidates: fail with a clear message and instructions to
  regenerate or restore the run
- unexpected counts: fail unless `--allow-count-drift` is explicitly passed
- non-ignored report path: fail unless `--allow-unignored-report-output` is
  explicitly passed
- invalid deck schema: fail before producing any report

## Phase 1: Deterministic Comparison Tool

Add:

- `scripts/compare_personlighedspsykologi_flashcard_pools.py`
- supporting module if needed:
  `notebooklm_queue/personlighedspsykologi_flashcard_review.py`

Inputs:

- canonical matrix deck JSON
- both committed NotebookLM variant deck JSONs
- full-run candidate JSON files
- exam theory matrix JSON
- flashcard architecture constants embedded in code or loaded from a compact
  local config

Outputs:

- JSON report under:
  `notebooklm-podcast-auto/personlighedspsykologi/flashcard_lab/reports/<review-run-id>/flashcard-pool-comparison.json`
- Markdown report under:
  `notebooklm-podcast-auto/personlighedspsykologi/flashcard_lab/reports/<review-run-id>/flashcard-pool-comparison.md`

Report artifacts should be local/generated and gitignored unless a final
summary is deliberately committed.

Implementation requirements:

- normalize deck cards and candidate cards into one internal card shape
- preserve source identity: matrix deck, first variants deck, independent
  variants deck, or full NotebookLM candidate cluster
- infer matrix theory IDs from explicit tags when available, then fallback to
  deterministic keyword matching
- assign `theory_topic` using the architecture plan
- assign `review_family` using deterministic rules from front/back/category
  keywords
- compute front/back character counts and simple overlong flags
- run existing safety pattern checks for names, paths, and provenance leaks
- compute nearest-card duplicate scores across all pools
- mark exact/near duplicates and "same slot" collisions
- summarize coverage by `theory_topic x review_family`
- include `classification_confidence` and `classification_evidence` for topic
  and family assignment
- preserve both raw source category and normalized review family
- keep auto-rejected NotebookLM candidates in the report, but exclude them from
  promotion shortlist by default

Quality threshold for Phase 1:

- classifier behavior is deterministic and tested
- unknowns are explicit, not silently forced into wrong categories
- every input card appears exactly once in the normalized report
- report can be regenerated without changing committed learner-facing decks
- deterministic report includes a manifest with input hashes and total counts
- at least one fixture test covers each review family and each source pool

Stop gate:

- If more than 20 percent of non-auto-rejected cards classify as `unknown`, do
  not proceed to Gemini. Improve classifier rules or taxonomy first.
- If committed deck cards are not all classified into at least a theory topic
  and a family, do not proceed to promotion planning.

## Phase 2: Coverage And Gap Report

Extend the deterministic report so it answers:

- Which `theory_topic x review_family` cells are empty?
- Which cells are overloaded?
- Which topics are underrepresented relative to the architecture targets?
- Which families are overrepresented by NotebookLM variants?
- Which cards are likely duplicates of existing matrix-deck cards?
- Which NotebookLM candidates appear to fill real gaps?
- Which cards have wording or length risks?

Markdown report sections:

1. Executive summary
2. Pool counts
3. Coverage grid
4. Missing cells
5. Overcrowded cells
6. Duplicate clusters
7. Wording/length risks
8. Candidate shortlist for LLM review
9. Recommendations before Gemini

The shortlist should be conservative. Prefer cards that:

- are not auto-rejected
- fill missing or weak coverage cells
- have low duplicate score against existing decks
- have clear Danish wording
- support oral-exam comparison, traps, or concept mechanisms

Shortlist budget:

- default maximum: 80 cards
- hard maximum for one Gemini call: 120 cards
- per-cell cap: normally 3 cards per `theory_topic x review_family`
- per-topic cap: normally 18 cards per topic

If the deterministic shortlist exceeds the default maximum, rank by:

1. fills missing coverage cell
2. low duplicate score against committed decks
3. high exam-use family: `teori-sammenligning`, `akse-sammenligning`,
   `eksamenstrap`, `begrebsmekanisme`, `svar-konstruktion`
4. non-overlong front/back
5. fewer safety or shape warnings

Stop gate:

- If the report shows that NotebookLM candidates mostly duplicate existing
  coverage, stop with a "no Gemini needed" recommendation.
- If important gaps are in committed matrix rows rather than NotebookLM
  candidate quality, recommend deterministic matrix-deck improvements instead
  of Gemini candidate review.

## Phase 3: User Review Checkpoint

Before calling Gemini, review the deterministic report with Oskar.

2026-05-26 execution note: Oskar explicitly approved continuing end to end with
the single-call Gemini review if safe. The deterministic stop gates passed, so
the checkpoint was satisfied by the active session instruction rather than a
separate pause.

Decision needed:

- run Gemini on the recommended shortlist as-is
- adjust shortlist rules
- stop and revise taxonomy/classification
- skip Gemini and do manual promotion decisions

This is a real checkpoint because Gemini input size and review framing affect
the final card strategy.

Checkpoint packet:

- Markdown report path
- total pool counts
- unknown-classification rate
- duplicate summary
- shortlist size and selection rules
- proposed Gemini prompt/bundle path, if any
- explicit recommendation: proceed, revise, or stop

## Phase 4: Single-Call Gemini Review

Add or reuse a script to create one compact Gemini bundle.

Likely script:

- extend `scripts/review_personlighedspsykologi_notebooklm_flashcards_with_gemini.py`, or
- add `scripts/review_personlighedspsykologi_flashcard_pool_with_gemini.py`

Input bundle should contain:

- architecture/rubric summary
- deterministic report summary
- candidate shortlist
- nearest existing card for each shortlisted candidate
- relevant compact matrix rows
- requested structured decision schema

Gemini output schema:

- `card_key`
- `decision`: `promote`, `promote_after_edit`, `merge_with_existing`,
  `keep_as_reference`, `reject`
- `reason`
- `suggested_front`
- `suggested_back`
- `target_deck_strategy`
- `theory_topic`
- `review_family`
- `risk_flags`

Guardrails:

- no raw student-note extracts
- no local file paths in the prompt except repo-relative artifact identifiers
- no learner-facing promotion directly from Gemini
- reject invented claims that are not supported by matrix context
- include "nearest committed card" for every candidate so Gemini cannot judge
  quality without duplicate context
- include "coverage cell" for every candidate so Gemini can judge added value
- validate Gemini response count and IDs exactly against the bundle before
  writing the review artifact

Fallback:

- If the shortlist cannot fit in one high-quality Gemini call, split into
  topic-bounded bundles and record that the single-call preference was
  superseded by size constraints.
- If Gemini output fails schema validation, preserve the bundle and failed
  response locally, but do not promote anything.

## Phase 5: Promotion Strategy Decision

Use the deterministic report plus Gemini review to choose one path:

1. patch canonical matrix deck wording while keeping stable card IDs
2. build a new curated best-of exam-practice deck
3. merge selected cards into an existing variants deck
4. keep decks as-is and record "no further promotion"
5. hide or de-emphasize weaker variant decks in Freudd, if they add confusion

The default should be conservative:

- keep canonical deck as the main deck
- promote only clear gap-filling cards
- avoid multiple parallel NotebookLM decks if they confuse practice

2026-05-26 decision:

- do not promote any cards from the full all-cluster NotebookLM candidate pool
  yet
- keep the canonical matrix deck as the main Freudd deck
- keep the two existing NotebookLM variant decks as separate historical/review
  outputs for now
- prefer improving the deterministic matrix deck and source-faithful card
  prompts before generating another candidate pool

Decision artifact:

- write a committed Markdown decision summary before any deck mutation
- include counts for promote, edit, merge, keep-as-reference, and reject
- include the chosen deck strategy and rejected alternatives
- include unresolved risks and remaining gaps

## Phase 6: Optional Promotion Implementation

Only do this phase if Phase 5 recommends promotion.

2026-05-26 execution note: skipped. The validated Gemini review rejected all
shortlisted candidates, so there is no supported deck mutation in this phase.

Implementation requirements:

- write a compact committed promotion-decisions artifact
- generate or patch the target deck deterministically
- keep source hashes and card counts in the artifact
- update `shows/personlighedspsykologi-en/flashcards/decks.json` only if deck
  visibility changes
- update artifact ownership and invariants
- add or extend Freudd service tests for the affected deck
- run artifact invariant checks and Freudd tests
- deploy and smoke-check Freudd

Promotion safety rules:

- canonical matrix card IDs must remain stable unless a card's conceptual
  identity changes
- do not overwrite the existing NotebookLM variants decks without an explicit
  replacement decision
- do not publish raw Gemini wording without deterministic validation and
  learner-facing safety checks
- if deck visibility changes, smoke-check all visible decks after deploy

## Phase 7: Final Review Summary

Commit a final summary to docs, probably in:

- `shows/personlighedspsykologi-en/docs/flashcard-review-final-report.md`, or
- a dated section in this plan if the outcome is small

The summary should include:

- what was reviewed
- deterministic report path
- Gemini model and artifact path, if used
- final deck strategy
- cards promoted/rejected/merged
- remaining gaps
- recommended future regeneration, if any

The final summary must also state:

- whether the current NotebookLM cluster design was sufficient
- whether future regeneration should use revised source-faithful clusters
- whether Freudd should keep one main deck or multiple visible decks
- what should happen to the two existing NotebookLM variant decks

## Test Plan

Minimum tests:

- deterministic classifier unit tests
- report shape/unit tests
- duplicate scoring smoke test
- safety warning tests
- CLI dry-run test using small fixtures

Full local verification before commit:

```bash
./.venv/bin/python -m pytest tests/test_personlighedspsykologi_flashcard_review.py
./.venv/bin/python -m py_compile scripts/compare_personlighedspsykologi_flashcard_pools.py
./.venv/bin/python scripts/compare_personlighedspsykologi_flashcard_pools.py --review-run-id <review-run-id>
```

If promotion happens, also run:

```bash
./.venv/bin/python scripts/check_personlighedspsykologi_artifact_invariants.py
cd freudd_portal && ../.venv/bin/python manage.py test quizzes.tests.test_flashcards.PersonlighedspsykologiMatrixFlashcardArtifactTests
```

## Risks And Mitigations

Risk: deterministic classification mislabels nuanced cards.
Mitigation: keep `unknown` explicit and report uncertain cards separately.

Risk: NotebookLM variants inflate `personbegreb` coverage while leaving method
or comparison gaps.
Mitigation: judge by `theory_topic x review_family`, not raw card count.

Risk: Gemini chooses polished but redundant cards.
Mitigation: provide nearest existing card and coverage gap context in the
bundle.

Risk: too many decks make Freudd practice confusing.
Mitigation: decide deck strategy only after report; prefer one canonical main
deck plus a small curated supplement.

Risk: student-note provenance leaks into learner-facing cards.
Mitigation: safety checks before report, before Gemini, and before promotion.

Risk: generated local reports become stale but look authoritative.
Mitigation: keep generated reports ignored; commit only final summarized
decisions and reproducible scripts.

## Recommended Next Action

Use the final review summary as the basis for the next product decision:

- keep the current Freudd decks unchanged for now
- decide whether the two NotebookLM variant decks should remain visible,
  become hidden/archive decks, or be replaced later by a small curated
  supplement
- if more cards are still desired, revise the NotebookLM output contract toward
  fewer, deeper, source-faithful exam cards before another regeneration
