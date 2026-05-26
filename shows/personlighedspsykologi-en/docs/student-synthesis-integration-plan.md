# Student Synthesis Integration Plan

Created: 2026-05-24

## Implementation Progress

### 2026-05-24: Phase 1 Build Started

Status: complete.

Scope for this pass:

- create a first-class `exam_theory_matrix.json` artifact for the student
  synthesis layer
- keep the original student notes outside the repo and store only provenance,
  hashes, extraction metadata, and normalized synthesis
- validate every theory row against current course artifacts before marking it
  course-grounded
- add tests for schema validation, stale/unsafe output prevention, and
  deterministic artifact construction

Current implementation decision: the first version will remain separate from
`course_context.py`, printouts, Freudd routes, and podcast prompts. It becomes
an auditable artifact first; downstream use comes only after the matrix itself
is validated.

### 2026-05-24: Builder Scaffold Added

Status: complete.

Added implementation targets:

- `notebooklm_queue/personlighedspsykologi_student_synthesis.py`
- `scripts/build_personlighedspsykologi_exam_theory_matrix.py`

The builder is designed to produce two artifacts:

- `student_synthesis/source_notes_index.json`
- `student_synthesis/exam_theory_matrix.json`

Safety decisions now encoded in the implementation:

- original student files stay outside the repository
- PDF/DOCX extraction is used only for metadata, keyword coverage, and
  provenance in this first deterministic pass
- generated rows must pass schema validation before writing
- validated rows must retain current-course grounding pointers
- raw extracted table text is rejected from normalized matrix fields

### 2026-05-24: First Matrix Artifact Generated

Status: complete.

Generated artifacts:

- `shows/personlighedspsykologi-en/student_synthesis/source_notes_index.json`
- `shows/personlighedspsykologi-en/student_synthesis/exam_theory_matrix.json`

Current generated state:

- indexed source notes: 2
- matrix rows: 13
- validated rows: 13
- DOCX embedded media detected: 2

The DOCX embedded media are recorded with
`embedded_media_review_status: needs_review`. The current matrix does not rely
on those images as unseen evidence; they are a review flag for a later pass.

### 2026-05-24: Validation And Invariants Added

Status: verified.

Added verification coverage:

- unit tests for source-note indexing and matrix validation
- duplicate `theory_id` rejection
- missing orientation-point rejection
- rejection of `validated` rows without representative course sources
- deterministic enrichment test for concept nodes and distinctions
- artifact-invariant checks for the generated source-note index and matrix

The new files are also registered in `artifact_ownership.json`, with the seed
marked as manual curation and the generated files marked as derived.

Verification run:

- `./.venv/bin/python -m pytest tests/test_personlighedspsykologi_student_synthesis.py tests/test_source_intelligence_schemas.py tests/test_build_personlighedspsykologi_semantic_artifacts.py tests/test_build_personlighedspsykologi_source_weighting.py`
- `./.venv/bin/python scripts/check_personlighedspsykologi_artifact_invariants.py`
- `./.venv/bin/python scripts/build_personlighedspsykologi_exam_theory_matrix.py --validate-only`
- `./.venv/bin/python -m py_compile notebooklm_queue/personlighedspsykologi_student_synthesis.py scripts/build_personlighedspsykologi_exam_theory_matrix.py scripts/check_personlighedspsykologi_artifact_invariants.py`

### 2026-05-24: Phase 1 Complete

Status: complete.

Phase 1 is finished when the goal is interpreted as building the first concrete
student-synthesis artifact. The current result is an auditable, validated
matrix artifact, not yet a learner-facing PDF, Freudd route, printout input, or
podcast prompt input.

The next implementation phase should use
`student_synthesis/exam_theory_matrix.json` to generate a master comparison
sheet or W12L1-focused theory-comparison output.

### 2026-05-25: Phase 2 QA Rubric Complete

Status: complete.

Scope for this pass:

- use `student_synthesis/exam_theory_matrix.json` as a deterministic semantic
  QA rubric for generated printout artifacts
- keep normal printout generation unchanged
- write QA reports into the existing `printout_review` evaluation workspace
- add an explicit opt-in validation hook so matrix QA can fail CI/review checks
  only when requested
- test row selection, scoring, report shape, and CLI failure thresholds

Design decision: the matrix is used for evaluation first, not as prompt input.
This preserves the existing authority boundary: generated printouts remain
source-grounded, while the matrix checks exam usefulness, comparison coverage,
orientation-point framing, and likely-misunderstanding prevention.

Implementation shape:

- `notebooklm_queue/personlighedspsykologi_printout_matrix_qa.py` evaluates
  schema-v3 reading printout JSON against relevant matrix rows.
- `scripts/evaluate_personlighedspsykologi_printout_matrix_qa.py` writes local
  JSON/Markdown rubric reports into
  `notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/rubric_reports/`.
- `scripts/validate_personlighedspsykologi_printout_integration.py --matrix-qa`
  adds the same check as an opt-in integration gate.
- Rubric report directories are generated QA artifacts and ignored by git except
  for the containing `.gitkeep`.

The gate is intentionally thresholded. The current canonical corpus contains
older printouts that can score below the stricter default because they predate
the student-synthesis matrix and do not always expose exam-bridge comparison
signals. That is useful signal, not a migration blocker.

Local verification result on 2026-05-25:

- `--all-canonical --dry-run`: 38 sources, average score 80, 25 pass, 13 warn,
  0 fail.
- `validate_personlighedspsykologi_printout_integration.py --matrix-qa
  --matrix-qa-fail-below 50 --min-canonical-bundles 20`: ok.
- Generated local report bundle:
  `rubric_reports/2026-05-canonical-matrix-qa/`.

### 2026-05-25: Expanded Source-Note Intake Started

Status: complete.

Scope for this pass:

- move student-note intake out of hardcoded Python defaults and into a
  committed source-note registry
- index the eight additional notes from Karla/Jaque with extraction metadata,
  hashes, likely target theory rows, and media-review flags
- generate a promotion-review artifact before changing matrix content
- selectively promote only compact exam-useful deltas into
  `exam_theory_matrix.seed.json`
- keep large notes such as poststructuralism and trait theory under
  `selective_enrichment`, not as raw matrix prose
- rerun the matrix build, invariant checks, printout matrix QA, commit, push,
  and deploy

Design decision: indexing a note is not the same as promoting it into the
matrix. The registry records source availability and intended use; the
promotion review records why a note should or should not affect rows; the seed
contains only normalized, curated, exam-facing changes.

Implementation shape:

- `student_synthesis/source_notes.registry.json` is now the canonical intake
  registry for student notes.
- `student_synthesis/source_notes_index.json` indexes 10 notes with hashes,
  extraction methods, expected theory rows, media counts, and extraction-risk
  flags.
- `student_synthesis/source_note_promotion_review.json` records the note-level
  promotion decision before the matrix output is considered.
- `exam_theory_matrix.seed.json` now references all promoted note IDs but only
  adds compact selective deltas to affected rows.

Current generated intake summary:

- indexed notes: 10
- notes with embedded media: 4
- embedded media files detected: 18
- matrix policies: 1 primary basis, 4 secondary basis, 5 selective enrichment
- matrix rows remain: 13
- validated matrix rows remain: 13

Verification result on 2026-05-25:

- `py_compile` passed for the student-synthesis module, matrix builder, and
  artifact invariant checker.
- Targeted pytest suite passed: 19 tests.
- `build_personlighedspsykologi_exam_theory_matrix.py --validate-only`: ok.
- `check_personlighedspsykologi_artifact_invariants.py`: ok.
- Printout matrix QA remains stable: 38 sources, average score 80, 25 pass,
  13 warn, 0 fail.

### 2026-05-25: Freudd Flashcard Plan Finalized

Status: complete.

The learner-facing flashcard implementation is a deterministic Freudd deck
generated from
`student_synthesis/exam_theory_matrix.json`.

Technical decision:

- use the existing file-backed Freudd flashcard system
- add `shows/personlighedspsykologi-en/flashcards/decks.json`
- add one generated deck artifact under
  `shows/personlighedspsykologi-en/flashcards/`
- do not add a new database model, Freudd route, or NotebookLM-dependent
  generation path for the first version

Reasoning:

- Freudd already discovers subject flashcard decks from subject-local
  `flashcards/decks.json` registries
- the existing flashcard service validates deck slug, subject slug, artifact
  path, card count, category metadata, and card shape
- anonymous preview and logged-in review/progress already work
- the matrix is already structured, validated, and small enough for a
  deterministic generator
- NotebookLM would add useful phrasing variation later, but it would blur
  provenance and reproducibility if used as the first source of truth

Implemented deck:

- subject slug: `personlighedspsykologi`
- deck slug: `eksamensmatrix-personlighedspsykologi`
- title: `Eksamensmatrix: personlighedspsykologi`
- source file: `student_synthesis/exam_theory_matrix.json`
- category groups:
  - `Orienteringspunkter`
  - `Personbegreb`
  - `Metode og evidens`
  - `Styrker og begrænsninger`
  - `Sammenligninger`
  - `Eksamenstraps`

Implemented card families:

- orientation cards: place each validated row on essence/context,
  determination, agency, and historicity
- model cards: ask what kind of person, personality, or subjectivity each
  theory assumes
- method cards: ask what evidence or method the theory trusts
- affordance cards: ask what each theory makes visible and what it tends to
  hide
- comparison cards: ask the high-value contrast or extension relation recorded
  in `comparison_targets`
- misunderstanding cards: ask for correction of likely exam traps

Card-count target:

- minimum: one usable card per validated matrix row
- preferred first version: roughly 100-140 cards
- hard cap for v1: 160 cards

The cap is intentional. The deck should support oral-exam retrieval and
comparison, not become a second textbook.

Implemented plan:

1. Add a deterministic generator, preferably
   `scripts/build_personlighedspsykologi_matrix_flashcards.py`, backed by a
   small reusable module in `notebooklm_queue/`.
2. Read only `student_synthesis/exam_theory_matrix.json` and reject generation
   unless all rows are validated and warning-free.
3. Generate stable card IDs from row ID, card family, orientation point, and
   target row; never hash display text into the ID.
4. Write a version-1 `freudd_flashcards` artifact with `front_text`,
   `back_html_sanitized`, `back_text`, categories, tags, content hashes, and
   card count.
5. Write/update the subject-local `flashcards/decks.json` registry.
6. Add artifact ownership entries for the registry and generated deck.
7. Extend invariants so the deck cannot silently drift from the matrix:
   registry path exists, deck loads through `flashcard_services.py`, card IDs
   are unique, every validated row has coverage, category counts match, and the
   deck does not leak raw student-note provenance.
8. Add focused tests for deterministic generation, schema validity, stable
   IDs, coverage thresholds, and Freudd service loading.
9. Leave `learning_material_regeneration_registry.json` unchanged for now and
   document that Freudd flashcard JSON is discovered by subject-local registry.
10. Commit, push `main`, deploy `freudd-portal`, and smoke-check both the
    subject page and
    `/subjects/personlighedspsykologi/cards/eksamensmatrix-personlighedspsykologi`.

Quality gates:

- no raw PDF/DOCX extraction text in learner-facing card fields
- no owner names, local file paths, or student-note IDs in learner-facing card
  text
- no card for a row with unresolved validation warnings
- all generated cards have non-empty front, HTML answer, plain-text answer,
  category slug/title, and deterministic content hash
- category counts sum to card count
- all deck artifacts can be loaded by `load_flashcard_deck`
- anonymous route returns a preview page; logged-in users can save answers and
  review ratings through the existing API
- deck card IDs remain stable across wording edits unless the underlying
  concept identity changes

Maintenance rule:

- later revisions should prefer appending cards or creating a v2 deck over
  rewriting existing card IDs, because Freudd stores user review state by
  `subject_slug`, `deck_slug`, and `card_id`
- NotebookLM or another LLM can be used later as a phrasing assistant, but the
  deterministic matrix generator remains the canonical writer

Implementation progress:

- 2026-05-25: started deterministic generator implementation against the
  existing Freudd `freudd_flashcards` artifact contract.
- 2026-05-25: generated and validated the first Freudd deck:
  `shows/personlighedspsykologi-en/flashcards/eksamensmatrix-personlighedspsykologi.json`.

Implemented files:

- generator module:
  `notebooklm_queue/personlighedspsykologi_matrix_flashcards.py`
- CLI writer:
  `scripts/build_personlighedspsykologi_matrix_flashcards.py`
- Freudd registry:
  `shows/personlighedspsykologi-en/flashcards/decks.json`
- Freudd deck:
  `shows/personlighedspsykologi-en/flashcards/eksamensmatrix-personlighedspsykologi.json`
- tests:
  `tests/test_personlighedspsykologi_matrix_flashcards.py`
  and the generated-deck service check in
  `freudd_portal/quizzes/tests/test_flashcards.py`

Generated deck state:

- total cards: 152
- categories: 6
- `Orienteringspunkter`: 52
- `Personbegreb`: 13
- `Metode og evidens`: 13
- `Styrker og begrænsninger`: 13
- `Sammenligninger`: 28
- `Eksamenstraps`: 33

Validation now enforced:

- the builder rejects matrix rows that are not `validated` or have warnings
- card IDs are stable identity IDs derived from theory row, card family, and
  comparison/orientation/trap identity
- learner-facing card fields are checked for local paths, student owner names,
  and raw student-note provenance leakage
- artifact ownership registers both the registry and deck as derived outputs
- `check_personlighedspsykologi_artifact_invariants.py` validates the
  registry, source matrix hash, deck schema, card counts, category counts, and
  row coverage
- Freudd service loading is covered by a Django test against the actual
  generated deck

Verification run:

- `./.venv/bin/python scripts/build_personlighedspsykologi_matrix_flashcards.py --validate-only`
- `./.venv/bin/python -m py_compile notebooklm_queue/personlighedspsykologi_matrix_flashcards.py scripts/build_personlighedspsykologi_matrix_flashcards.py scripts/check_personlighedspsykologi_artifact_invariants.py`
- `./.venv/bin/python scripts/check_personlighedspsykologi_artifact_invariants.py`
- `./.venv/bin/python -m pytest tests/test_personlighedspsykologi_matrix_flashcards.py tests/test_personlighedspsykologi_student_synthesis.py`
- `cd freudd_portal && ../.venv/bin/python manage.py test quizzes.tests.test_flashcards.PersonlighedspsykologiMatrixFlashcardArtifactTests`

### 2026-05-25: NotebookLM Alternative Flashcard Lab Implemented

Status: complete, including one live NotebookLM pilot run.

Scope for this pass:

- use NotebookLM as an alternative-card candidate generator, not as the
  canonical Freudd deck writer
- export processed Markdown packs from the validated matrix and current Freudd
  deck, without uploading original student-note PDFs/DOCX files
- split the lab into five bounded notebooks instead of one large mixed context
- normalize downloaded NotebookLM cards into review-only candidate artifacts
  with duplicate checks, theory mapping, category inference, unsafe-provenance
  checks, and review-status labels
- keep generated run outputs local and gitignored

Implemented notebook plan:

- `global-calibration-synthesis`
- `measurement-development-pathology`
- `psychoanalysis-experience-humanism`
- `critical-sociocultural-narrative`
- `oral-exam-comparison-workshop`

Implemented files:

- lab module:
  `notebooklm_queue/personlighedspsykologi_notebooklm_flashcard_lab.py`
- pack export CLI:
  `scripts/export_personlighedspsykologi_notebooklm_flashcard_packs.py`
- candidate normalizer CLI:
  `scripts/normalize_personlighedspsykologi_notebooklm_flashcards.py`
- optional NotebookLM pilot runner:
  `scripts/run_personlighedspsykologi_notebooklm_flashcard_pilot.py`
- single-call Gemini review CLI:
  `scripts/review_personlighedspsykologi_notebooklm_flashcards_with_gemini.py`
- lab workspace docs:
  `notebooklm-podcast-auto/personlighedspsykologi/flashcard_lab/README.md`
- tests:
  `tests/test_personlighedspsykologi_notebooklm_flashcard_lab.py`

Operational contract:

- start with the `critical-sociocultural-narrative` pilot because it has the
  richest comparison/trap payoff
- upload only generated Markdown packs from `flashcard_lab/runs/<run-id>/packs/`
- download NotebookLM flashcards as JSON and normalize them before review
- review normalized candidates against the existing Freudd deck before any
  variants-deck promotion
- do not import raw NotebookLM cards into Freudd
- keep accepted NotebookLM alternatives in a separate variants deck unless a
  later task explicitly edits and promotes them into the canonical matrix deck

Verification run:

- `./.venv/bin/python -m py_compile notebooklm_queue/personlighedspsykologi_notebooklm_flashcard_lab.py scripts/export_personlighedspsykologi_notebooklm_flashcard_packs.py scripts/normalize_personlighedspsykologi_notebooklm_flashcards.py scripts/run_personlighedspsykologi_notebooklm_flashcard_pilot.py`
- `./.venv/bin/python -m pytest tests/test_personlighedspsykologi_notebooklm_flashcard_lab.py tests/test_personlighedspsykologi_matrix_flashcards.py`
- `./.venv/bin/python scripts/export_personlighedspsykologi_notebooklm_flashcard_packs.py --pilot-only --run-id local-cli-smoke`
- `./.venv/bin/python scripts/run_personlighedspsykologi_notebooklm_flashcard_pilot.py --run-id local-dry-run-smoke --dry-run`
- `./.venv/bin/python scripts/run_personlighedspsykologi_notebooklm_flashcard_pilot.py --run-id pilot-20260525-critical-sociocultural-narrative`
- `./.venv/bin/python scripts/normalize_personlighedspsykologi_notebooklm_flashcards.py --run-id pilot-20260525-critical-sociocultural-narrative --notebook-slug critical-sociocultural-narrative --input-json notebooklm-podcast-auto/personlighedspsykologi/flashcard_lab/runs/pilot-20260525-critical-sociocultural-narrative/downloads/critical-sociocultural-narrative.flashcards.json`
- `./.venv/bin/python scripts/review_personlighedspsykologi_notebooklm_flashcards_with_gemini.py --candidates-json notebooklm-podcast-auto/personlighedspsykologi/flashcard_lab/runs/pilot-20260525-critical-sociocultural-narrative/candidates/critical-sociocultural-narrative.candidates.json`

Live pilot result:

- NotebookLM notebook ID:
  `6ba89f27-181a-44df-97e2-15f801974bb7`
- uploaded processed Markdown sources: 6
- raw NotebookLM cards: 80
- normalized candidates: 80
- automatic status labels after local QA:
  - `candidate`: 60
  - `needs_review`: 19
  - `auto_rejected`: 1
- single-call Gemini review:
  - model: `gemini-3.1-pro-preview`
  - prompt: `personlighedspsykologi-gemini-flashcard-review-v1`
  - `accept`: 60
  - `edit`: 19
  - `reject`: 1
- local run output is intentionally gitignored under
  `notebooklm-podcast-auto/personlighedspsykologi/flashcard_lab/runs/pilot-20260525-critical-sociocultural-narrative/`

Implementation note: the shared Gemini helper still defaults to high thinking
for existing preprocessing pipelines. The flashcard review CLI uses low
thinking by default because the full 80-card review bundle timed out at the
high-thinking default while the same single-call bundle completed with
low-thinking review generation.

### 2026-05-26: NotebookLM Variants Deck Promoted

Status: complete.

Scope for this pass:

- promote the reviewed pilot output into a separate Freudd variants deck
- keep the canonical matrix deck unchanged
- commit only the compact promotion decisions and learner-facing deck artifact,
  not the ignored raw NotebookLM/Gemini run folder
- make the shared `flashcards/decks.json` registry safe for multiple deck
  writers so rebuilding the matrix deck preserves the variants deck
- extend invariants and Freudd service tests so both decks keep loading

Implemented files:

- variant builder:
  `notebooklm_queue/personlighedspsykologi_notebooklm_variant_flashcards.py`
- promotion CLI:
  `scripts/build_personlighedspsykologi_notebooklm_variant_flashcards.py`
- promotion decisions:
  `shows/personlighedspsykologi-en/flashcards/notebooklm_variant_promotion_decisions.json`
- variants deck:
  `shows/personlighedspsykologi-en/flashcards/notebooklm-varianter-personlighedspsykologi.json`

Current deck state:

- canonical matrix deck: `eksamensmatrix-personlighedspsykologi`, 152 cards
- NotebookLM variants deck: `notebooklm-varianter-personlighedspsykologi`, 79
  cards
- source pilot decisions: 60 `accept`, 19 `edit`, 1 `reject`

Verification run:

- `./.venv/bin/python -m py_compile notebooklm_queue/personlighedspsykologi_matrix_flashcards.py notebooklm_queue/personlighedspsykologi_notebooklm_variant_flashcards.py scripts/build_personlighedspsykologi_matrix_flashcards.py scripts/build_personlighedspsykologi_notebooklm_variant_flashcards.py scripts/check_personlighedspsykologi_artifact_invariants.py`
- `./.venv/bin/python scripts/build_personlighedspsykologi_notebooklm_variant_flashcards.py --validate-only`
- `./.venv/bin/python scripts/build_personlighedspsykologi_matrix_flashcards.py --validate-only`
- `./.venv/bin/python -m pytest tests/test_personlighedspsykologi_matrix_flashcards.py tests/test_personlighedspsykologi_notebooklm_variant_flashcards.py tests/test_personlighedspsykologi_notebooklm_flashcard_lab.py tests/test_gemini_preprocessing.py`
- `./.venv/bin/python scripts/check_personlighedspsykologi_artifact_invariants.py`
- `cd freudd_portal && ../.venv/bin/python manage.py test quizzes.tests.test_flashcards.PersonlighedspsykologiMatrixFlashcardArtifactTests`

### 2026-05-26: NotebookLM Source-Pack Policy Tightened

Status: complete.

Decision: future NotebookLM flashcard packs should not include existing Freudd
cards as NotebookLM source material. Current cards are still used downstream
for local duplicate scoring and Gemini review, but NotebookLM now generates
from processed matrix/orientation/comparison material only.

Implementation changes:

- remove the exported `current-freudd-cards` Markdown source from future packs
- keep pack filenames compact: authoring brief, orientation points, matrix
  slice, comparison targets, and output contract
- record `freudd_deck_policy.included_as_notebook_source: false` in the lab
  manifest
- clean stale Markdown files from a pack directory before writing, so reused
  run IDs cannot accidentally upload old Freudd-card sources
- strengthen the authoring brief to ask for independent oral-exam candidates
  and leave duplicate detection to the post-generation review stage

Verification run:

- `./.venv/bin/python -m py_compile notebooklm_queue/personlighedspsykologi_notebooklm_flashcard_lab.py scripts/export_personlighedspsykologi_notebooklm_flashcard_packs.py scripts/run_personlighedspsykologi_notebooklm_flashcard_pilot.py`
- `./.venv/bin/python -m pytest tests/test_personlighedspsykologi_notebooklm_flashcard_lab.py`
- `./.venv/bin/python scripts/export_personlighedspsykologi_notebooklm_flashcard_packs.py --pilot-only --run-id local-no-current-freudd-smoke --print-manifest`

### 2026-05-26: Independent NotebookLM Third Deck Promoted

Status: complete.

Intended third deck:

- deck slug:
  `notebooklm-uafhaengige-varianter-personlighedspsykologi`
- title:
  `NotebookLM-uafhængige varianter: personlighedspsykologi`
- first cluster:
  `critical-sociocultural-narrative`

Implementation completed:

- the promotion builder now supports separate deck slugs/titles/descriptions,
  so a third deck can be promoted without overwriting
  `notebooklm-varianter-personlighedspsykologi`
- the pilot runner accepts `--storage`, allowing it to use the repo-local
  `notebooklm-podcast-auto/profiles/*_storage_state.json` files directly
- `nguyenanhpho19` was added to `notebooklm-podcast-auto/profiles.json` and
  authenticated into `notebooklm-podcast-auto/profiles/nguyenanhpho19_storage_state.json`
- improved source pack exported locally for run
  `independent-20260526-critical-sociocultural-narrative`
- exported pack has 5 NotebookLM sources and confirms
  `freudd_deck_policy.included_as_notebook_source: false`
- NotebookLM notebook ID: `6f07d6ff-2941-4fdc-ae81-ff1c6b903f07`
- raw NotebookLM cards: 77
- normalized status counts: 51 `candidate`, 25 `needs_review`, 1
  `auto_rejected`
- Gemini review: 45 `accept`, 29 `edit`, 1 `merge_with_existing`, 2 `reject`
- promoted deck cards: 74
- promotion decisions:
  `shows/personlighedspsykologi-en/flashcards/notebooklm_independent_variant_promotion_decisions.json`
- deck artifact:
  `shows/personlighedspsykologi-en/flashcards/notebooklm-uafhaengige-varianter-personlighedspsykologi.json`

Verification additions:

- artifact ownership covers the independent decisions and deck artifacts
- artifact invariants validate both NotebookLM variants decks
- Freudd service tests load the independent deck through
  `flashcard_services.py`

Run commands used:

```bash
./.venv/bin/python scripts/run_personlighedspsykologi_notebooklm_flashcard_pilot.py \
  --run-id independent-20260526-critical-sociocultural-narrative \
  --storage notebooklm-podcast-auto/profiles/nguyenanhpho19_storage_state.json

./.venv/bin/python scripts/review_personlighedspsykologi_notebooklm_flashcards_with_gemini.py \
  --candidates-json notebooklm-podcast-auto/personlighedspsykologi/flashcard_lab/runs/independent-20260526-critical-sociocultural-narrative/candidates/critical-sociocultural-narrative.candidates.json

./.venv/bin/python scripts/build_personlighedspsykologi_notebooklm_variant_flashcards.py \
  --deck-slug notebooklm-uafhaengige-varianter-personlighedspsykologi \
  --title "NotebookLM-uafhængige varianter: personlighedspsykologi" \
  --description "Gemini-reviewede NotebookLM-varianter genereret uden eksisterende Freudd-kort som NotebookLM-kilde." \
  --candidates-json notebooklm-podcast-auto/personlighedspsykologi/flashcard_lab/runs/independent-20260526-critical-sociocultural-narrative/candidates/critical-sociocultural-narrative.candidates.json \
  --gemini-review-json notebooklm-podcast-auto/personlighedspsykologi/flashcard_lab/runs/independent-20260526-critical-sociocultural-narrative/gemini_review/critical-sociocultural-narrative.gemini-review.json \
  --promotion-decisions-path shows/personlighedspsykologi-en/flashcards/notebooklm_independent_variant_promotion_decisions.json \
  --deck-path shows/personlighedspsykologi-en/flashcards/notebooklm-uafhaengige-varianter-personlighedspsykologi.json
```

## Purpose

This plan describes how to use older high-performing student notes as a
structured support layer for `personlighedspsykologi` course material.

The candidate files are:

- `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/personlighedspsykologi/Noter/Anes tabel.pdf`
- `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/personlighedspsykologi/Noter/narrativ-fra-jaque/Tabel alle teoretiske retninger.docx`

The core decision is to treat these files as a student synthesis and
exam-orientation layer, not as ordinary readings and not as authoritative
course sources.

## Assessment

`Anes tabel.pdf` is the stronger source candidate. It is a broad comparison
map across the main theory traditions in the course. It repeatedly uses the
course's four orientation points:

- essens vs kontekst
- determination
- agency
- historicitet

It also gives each tradition a useful student-facing structure:

- hovedpointe
- faghistorisk kontekst
- syn paa personligheden
- main thinkers
- centrale begreber
- metode
- orienteringspunkter
- muligheder og begraensninger

`Tabel alle teoretiske retninger.docx` is more compact and more uneven, but it
is still useful as a second student model. It uses a table format with
tradition/genstandsfelt, core concepts, personality understanding, method,
orientation points, and strengths/limitations. It also contains useful
comparison material, especially around socialkonstruktionisme versus
poststrukturalisme.

Both files are valuable because they show what a capable student believed was
exam-useful: not only source-level detail, but cross-theory placement,
contrast, critique, and oral-exam framing.

## Fit With Current System

The existing `Freudd Content Engine` already has the right upstream machinery:

- deterministic source inventory in `source_catalog.json`
- lecture bundles in `lecture_bundles/`
- source cards, lecture substrates, course synthesis, and podcast substrates
  under `source_intelligence/`
- course-level semantic artifacts such as `course_theory_map.json`,
  `course_concept_graph.json`, `course_glossary.json`, and
  `source_weighting.json`
- learner-facing outputs: podcasts, printouts, quizzes, slides, flashcards,
  and exam study plans

The student notes should add a missing human layer between source
understanding and exam-ready course mastery:

- what a strong student compresses
- which distinctions a strong student keeps alive
- how traditions are placed on the orientation axes
- what limitations and comparison moves are likely useful in oral answers

They should not override readings, slides, manual summaries, source cards, or
teacher/course artifacts.

## Proposed Artifact Model

Add a new intermediate artifact family for student synthesis, for example:

- `shows/personlighedspsykologi-en/student_synthesis/source_notes_index.json`
- `shows/personlighedspsykologi-en/student_synthesis/exam_theory_matrix.json`
- `shows/personlighedspsykologi-en/student_synthesis/comparison_axes.json`
- `shows/personlighedspsykologi-en/student_synthesis/student_exam_traps.json`

Suggested authority label:

- `student_exam_synthesis`

Suggested evidence role:

- lower than `reading_grounded`, `textbook_framing`, and `lecture_framed`
- higher than generic model inference when the claim is about exam framing,
  common comparison moves, or likely student misunderstandings

The artifact should preserve provenance:

- original file path
- extraction method
- generated timestamp
- hash of the original file
- validation status against current 2026 course artifacts
- per-cell confidence or review state

## Canonical Matrix Shape

The central artifact should be an exam theory matrix with one row per theory
tradition or subtradition:

- trait psychology
- biosocial/evolutionary/genetic perspectives
- psychoanalysis
- French psychoanalysis where needed
- phenomenology
- existential psychology
- humanistic psychology
- critical personalism
- critical psychology
- social constructionism
- poststructuralism
- discursive/feminist approaches where needed
- narrative psychology
- full-course synthesis / W12L1

Each row should include:

- theory label
- covered lecture keys
- main course role
- model of the person
- model of personality or subjectivity
- method/evidence style
- central concepts
- main thinkers
- essence/context placement
- determination placement
- agency placement
- historicity placement
- strongest affordances
- strongest limitations
- likely exam comparisons
- likely misunderstandings
- source-grounding pointers into current course artifacts
- notes from student synthesis
- validation status

The matrix should be built from the student files, then checked against the
current course substrate before it becomes a learner-facing artifact.

## Learner-Facing Uses

### 1. Master Comparison Sheet

Generate one polished PDF/Markdown comparison sheet for the whole course.

It should be optimized for oral exam preparation:

- one compact table across theory traditions
- the four orientation points always visible
- short method column
- short strengths/limitations column
- recommended comparison pairs
- no long prose dump

This belongs near the existing oral-exam material, not inside a single
lecture's reading printouts.

### 2. Theory Sheets

Generate one theory sheet per major tradition.

Each sheet should answer:

- What is the person?
- What is personality or subjectivity?
- Where is agency located?
- What determines the person?
- What is the role of context and history?
- What method/evidence does the theory trust?
- What does this theory make visible?
- What does this theory hide?
- Which two theories should it be compared with?

These sheets are different from reading printouts. They are course-compression
and oral-answer artifacts.

### 3. Freudd Portal Surface

Add a future Freudd surface for exam-oriented synthesis:

- a theory overview route
- orientation-point filters
- theory cards
- comparison matrix
- links from a lecture to the relevant theory row
- optional "compare with" prompts

This should come after the artifact exists and has been validated.

### 4. Flashcards

Use the matrix to generate higher-value flashcards.

Good card types:

- "Where is agency located in critical psychology?"
- "What would poststructuralism criticize in trait psychology?"
- "Which historicity is emphasized by evolutionary trait theory?"
- "What is the difference between social constructionism and
  poststructuralism?"
- "Which theory turns personality into subjectivity?"

This is likely more useful than definition-only cards.

### 5. Podcasts And Prompt Context

Use the student synthesis as compact course-orientation guidance for podcasts,
not as source evidence.

Prompt guidance should say, in effect:

- place this lecture on the four orientation axes
- name the comparison target that matters most
- prevent the likely student misunderstanding
- distinguish student synthesis from source-grounded claims

The podcast should not narrate that it is using an internal student synthesis
artifact.

### 6. Printout QA

Use the matrix as a review rubric for generated printouts:

- Does the output locate the reading within the theory tradition?
- Does it preserve at least one orientation-point implication?
- Does it name a useful limitation or contrast?
- Does it prevent the obvious exam-trap simplification?

The matrix should guide evaluation and regeneration priorities before it is
fed directly into every printout prompt.

## Implementation Phases

### Phase 1: Extraction And Inventory

Create a small extraction script or one-off operator workflow that produces:

- extracted text/Markdown
- file hashes
- source note metadata
- a rough section map
- detected traditions
- detected orientation-point passages

For the PDF, `pdftotext -layout` worked well enough for analysis. For the
DOCX, `pandoc` preserved the table content well enough for semantic
processing. The DOCX also contains embedded comparison images that should be
captured or OCR-reviewed separately if used.

### Phase 2: Structured Draft Matrix

Use a model to convert the extracted notes into a structured draft matrix.

The model should be instructed to:

- preserve the student's comparative structure
- avoid treating the notes as authoritative
- keep uncertain or incomplete cells explicit
- avoid long quotations
- separate student phrasing from normalized course language

### Phase 3: Course Validation

Validate each row against current course artifacts:

- `course_theory_map.json`
- `course_concept_graph.json`
- `source_intelligence/course_synthesis.json`
- relevant lecture bundles
- source cards for key readings and slides
- manual reading and weekly summaries

Validation should mark cells as:

- `validated`
- `needs_review`
- `outdated_or_mismatched`
- `student_only_exam_hint`

Student-only exam hints can be retained, but they must not be presented as
course-source evidence.

### Phase 4: Learner Output Generation

Generate the first learner-facing outputs:

1. full-course master comparison sheet
2. one theory sheet for W12L1 or the late-course synthesis
3. one flashcard deck pilot
4. optional Freudd preview route or static linked asset

The first pilot should target W12L1 and the final oral-exam preparation
surface, because that is where the matrix has the highest value.

### Phase 5: Integration With The Content Engine

After the pilot is reviewed, integrate the matrix into the Course
Understanding Pipeline as a controlled optional input:

- add the new artifact family to source-intelligence provenance
- update course-context selection to optionally pull compact matrix rows
- add explicit authority/evidence rules
- add staleness checks based on source-note hashes and validated matrix hashes
- add tests that ensure student synthesis cannot replace source-grounded
  evidence

## Guardrails

- Do not publish the student notes verbatim.
- Do not treat them as current course authority.
- Do not let them override readings, slides, source cards, or instructor
  framing.
- Do not dump the full notes into every NotebookLM prompt.
- Keep the student-synthesis layer compact and auditable.
- Mark colloquial, incomplete, or uncertain parts as such.
- Use the notes mainly for exam-useful structure, comparison, and
  misunderstanding prevention.

## Acceptance Criteria

The original first useful version criteria were:

- the two files are indexed with provenance and hashes
- a structured exam theory matrix exists
- every matrix row is mapped to current lecture keys
- every matrix row has validation status
- W12L1 has a generated master comparison sheet
- at least one theory-sheet pilot exists
- at least one flashcard pilot exists or is dry-run planned
- the output distinguishes source-grounded claims from student-synthesis
  framing

The version is not done merely because the notes have been extracted. The value
comes from validated comparison structure and learner-facing synthesis.

Current status:

- source-note indexing is complete for the initial two notes plus the eight
  additional notes from Karla/Jaque
- the validated 13-row matrix exists and is guarded by invariants
- printout matrix QA exists as an opt-in evaluation gate
- a Freudd flashcard deck exists, is deployed, and is smoke-checked live
- W12L1 master comparison and theory-sheet outputs have not been implemented

The active user priority has shifted away from printable outputs and toward
Freudd flashcard practice. Treat the flashcard deck as the first learner-facing
surface. Do not resume printout/master-sheet work unless Oskar asks for it or
the flashcard review shows a concrete need for a printable companion.

## Recommended Next Phase

Review and polish the deployed Freudd deck as a learning product:

1. Manually sample the live deck in Freudd across all six categories.
2. Decide whether the mixed Danish shell plus English theory-row content is
   acceptable, or whether v1.1 should localize learner-facing row labels and
   answers into Danish.
3. Tighten cards that feel too verbose, too easy, or too generic while keeping
   existing card IDs stable.
4. Add a small review-report artifact if the manual QA produces systematic
   findings.
5. Only after the flashcard deck feels good in use, consider a Freudd theory
   overview/comparison surface or a W12L1 theory sheet.
