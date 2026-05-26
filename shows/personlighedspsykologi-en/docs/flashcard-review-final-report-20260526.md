# Flashcard Review Final Report 2026-05-26

## Scope

This review compared the current Freudd personlighedspsykologi flashcard
surface against the full all-cluster NotebookLM candidate regeneration.

Reviewed pools:

- canonical matrix deck: `eksamensmatrix-personlighedspsykologi` (152 cards)
- first NotebookLM variants deck: `notebooklm-varianter-personlighedspsykologi`
  (79 cards)
- independent NotebookLM variants deck:
  `notebooklm-uafhaengige-varianter-personlighedspsykologi` (74 cards)
- full all-cluster NotebookLM run:
  `full-matrix-20260526-notebooklm-independent` (259 candidates)

Generated reports are local review outputs and intentionally gitignored:

- deterministic report:
  `notebooklm-podcast-auto/personlighedspsykologi/flashcard_lab/reports/flashcard-pool-review-20260526/flashcard-pool-comparison.md`
- Gemini review:
  `notebooklm-podcast-auto/personlighedspsykologi/flashcard_lab/reports/flashcard-pool-review-20260526/gemini_review/flashcard-pool.gemini-review.md`

## Implementation

Committed review tooling:

- `scripts/compare_personlighedspsykologi_flashcard_pools.py`
- `scripts/review_personlighedspsykologi_flashcard_pool_with_gemini.py`
- `notebooklm_queue/personlighedspsykologi_flashcard_review.py`
- `tests/test_personlighedspsykologi_flashcard_review.py`

The deterministic comparison normalizes all pools into one card shape, classifies
cards by theory topic and review family, computes duplicate pressure, summarizes
coverage, and builds a bounded NotebookLM shortlist for LLM review. The Gemini
script reviews that shortlist in one structured call and validates exact card
coverage before writing an advisory artifact.

## Deterministic Findings

Normalized card count: 564.

Source counts:

- canonical matrix deck: 152
- first NotebookLM variants deck: 79
- independent NotebookLM variants deck: 74
- full NotebookLM candidates: 259

Stop gates:

- unknown non-auto-rejected rate: 0.0427
- unknown-rate threshold: 0.20
- Gemini blocked: false
- committed unclassified cards: 13

Duplicate pressure:

- exact/front-match duplicates: 2
- near duplicates: 33
- same-slot collisions: 69

The deterministic report allowed Gemini review, but it also warned that
classification on some committed cards should be improved before any future
promotion planning.

## Gemini Review

Model: `gemini-3.1-pro-preview`

Prompt: `personlighedspsykologi-gemini-flashcard-pool-review-v1`

Input: one bounded 80-card shortlist from the full NotebookLM candidate pool.

Validated decision counts:

- promote: 0
- promote after edit: 0
- merge with existing: 0
- reject: 80
- defer: 0

Gemini judged 9 rejected cards as cases where the existing card was better and
71 as cases where neither candidate nor existing-nearest relation justified a
promotion. Confidence was high for 52 rejections and medium for 28.

Average Gemini scores across the rejected shortlist:

- coverage: 3.66
- exam usefulness: 2.73
- precision: 3.45
- wording: 3.05
- duplicate risk: 2.36

The Gemini summary text called the full NotebookLM candidate pool the "best
pool", but the validated per-card decisions rejected every shortlisted
candidate. Treat the per-card decision counts as authoritative for promotion.

## Deck Strategy Decision

Do not promote cards from the full all-cluster NotebookLM candidate pool into
Freudd right now.

Recommended current deck strategy:

- keep `eksamensmatrix-personlighedspsykologi` as the main deck
- keep both existing NotebookLM variant decks unchanged for now
- do not merge the new full-run NotebookLM candidates into any visible deck
- do not mutate learner-facing cards until a separate promotion artifact exists

The existing Freudd/manual matrix deck is the best current learner-facing base.
The full NotebookLM candidate pool did not produce enough net-new, precise,
exam-useful cards to justify deck growth.

## What This Means For NotebookLM

The five notebook clusters were useful enough to generate broad coverage, but
the output contract still overproduced basic, generic, or redundant cards. If
NotebookLM is used again for flashcards, the next process should ask for fewer
cards with stricter source-faithful constraints:

- fewer broad definition cards
- more mechanism-level cards tied to a specific theory row
- more oral-exam contrast cards only where a contrast is not already covered
- explicit instruction to avoid generic "exam trap" cards
- explicit self-rejection criteria for cards that merely restate the matrix
- a smaller candidate target per cluster

## Remaining Work

Next useful product decision:

- decide whether the two existing NotebookLM variant decks should remain visible
  in Freudd, be hidden/archive decks, or be replaced later by one small curated
  supplement

Next useful technical improvement:

- improve classification of the 13 committed cards that remained unclassified
  before any future automated promotion planning

No Freudd deck deploy is needed from this review itself because no learner-facing
deck artifact changed.
