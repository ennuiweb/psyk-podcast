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
  `notebooklm-podcast-auto/personlighedspsykologi/flashcard_lab/reports/<run-id>/flashcard-pool-comparison.json`
- Markdown report under:
  `notebooklm-podcast-auto/personlighedspsykologi/flashcard_lab/reports/<run-id>/flashcard-pool-comparison.md`

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

Quality threshold for Phase 1:

- classifier behavior is deterministic and tested
- unknowns are explicit, not silently forced into wrong categories
- every input card appears exactly once in the normalized report
- report can be regenerated without changing committed learner-facing decks

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

## Phase 3: User Review Checkpoint

Before calling Gemini, review the deterministic report with Oskar.

Decision needed:

- run Gemini on the recommended shortlist as-is
- adjust shortlist rules
- stop and revise taxonomy/classification
- skip Gemini and do manual promotion decisions

This is a real checkpoint because Gemini input size and review framing affect
the final card strategy.

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

## Phase 6: Optional Promotion Implementation

Only do this phase if Phase 5 recommends promotion.

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
./.venv/bin/python scripts/compare_personlighedspsykologi_flashcard_pools.py --run-id <review-run-id>
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

Implement Phase 1 and Phase 2 together. Stop before Gemini with a Markdown
report and shortlist so Oskar can inspect the review framing.
