# NotebookLM Flashcard Lab

This workspace is for generating flashcard candidates from processed
`personlighedspsykologi` data. As of 2026-05-26, the newest full all-cluster
NotebookLM deck is the only live Freudd deck for this subject.

Current live Freudd output:

- registry:
  `shows/personlighedspsykologi-en/flashcards/decks.json`
- deck:
  `shows/personlighedspsykologi-en/flashcards/notebooklm-fuld-matrix-personlighedspsykologi.json`
- builder:
  `scripts/build_personlighedspsykologi_full_notebooklm_flashcards.py`

Previous live decks, including the original matrix/Gemini-style deck and pilot
NotebookLM decks, are archived in:

- `shows/personlighedspsykologi-en/flashcards/archive/retired-live-decks-2026-05-26/`

NotebookLM should only see processed Markdown packs exported from the matrix,
orientation points, and comparison targets. Do not upload the original
student-note PDFs/DOCX files or existing Freudd flashcards for this workflow.
Existing Freudd cards are used only after generation for local duplicate checks
and Gemini review.

## Notebook Set

The planned lab uses five notebooks:

- `global-calibration-synthesis`
- `measurement-development-pathology`
- `psychoanalysis-experience-humanism`
- `critical-sociocultural-narrative`
- `oral-exam-comparison-workshop`

The recommended first pilot is `critical-sociocultural-narrative`, because it
stresses the parts of the course where comparison, critique, and exam traps add
the most value.

## Workflow

Export processed packs:

```bash
./.venv/bin/python scripts/export_personlighedspsykologi_notebooklm_flashcard_packs.py --pilot-only
```

Upload the generated Markdown files in the selected `runs/<run-id>/packs/<slug>/`
folder to NotebookLM, generate flashcards there, then download the flashcards as
JSON.

The exported NotebookLM source pack intentionally excludes existing Freudd
cards. Let NotebookLM generate independently from the processed course
structure, then dedupe against Freudd downstream.

Normalize downloaded NotebookLM output:

```bash
./.venv/bin/python scripts/normalize_personlighedspsykologi_notebooklm_flashcards.py \
  --run-id <run-id> \
  --notebook-slug critical-sociocultural-narrative \
  --input-json <downloaded-flashcards.json>
```

The normalizer writes local candidate JSON and review Markdown under
`runs/<run-id>/candidates/`. Those run outputs are gitignored.

Review candidates with Gemini in a single call:

```bash
./.venv/bin/python scripts/review_personlighedspsykologi_notebooklm_flashcards_with_gemini.py \
  --candidates-json <run>/candidates/<notebook-slug>.candidates.json
```

The Gemini reviewer builds a compact JSON bundle containing every candidate,
its nearest existing Freudd card, relevant matrix rows, and the review rubric.
It writes advisory review JSON/Markdown under `runs/<run-id>/gemini_review/`.
It does not promote or modify Freudd cards.

Promote reviewed candidates into the separate Freudd variants deck:

```bash
./.venv/bin/python scripts/build_personlighedspsykologi_notebooklm_variant_flashcards.py
```

The promotion script writes a compact committed decisions artifact and a
learner-facing Freudd deck under `shows/personlighedspsykologi-en/flashcards/`.
It never commits the raw NotebookLM/Gemini run folder.

When NotebookLM auth and quota are healthy, the pilot can also be run
end-to-end:

```bash
./.venv/bin/python scripts/run_personlighedspsykologi_notebooklm_flashcard_pilot.py
```

Run all five notebook clusters end-to-end:

```bash
./.venv/bin/python scripts/run_personlighedspsykologi_notebooklm_flashcard_pilot.py \
  --all-notebooks \
  --storage notebooklm-podcast-auto/profiles/nguyenanhpho19_storage_state.json
```

The all-cluster runner writes one NotebookLM notebook per cluster, downloads
JSON/Markdown flashcards for each cluster, and normalizes each download into
review-only candidates under `runs/<run-id>/candidates/`.

Use `--dry-run` first to inspect the planned NotebookLM commands without
creating a notebook or uploading sources.

## Current Full-Course Regeneration

The first all-cluster run is:

- run ID: `full-matrix-20260526-notebooklm-independent`
- source policy: no existing Freudd cards were uploaded to NotebookLM
- total raw NotebookLM flashcards: 259
- normalized status totals: 176 `candidate`, 58 `needs_review`, 25
  `auto_rejected`

Cluster counts:

| Cluster | Raw | Candidate | Needs review | Auto rejected |
|---|---:|---:|---:|---:|
| `global-calibration-synthesis` | 89 | 43 | 38 | 8 |
| `measurement-development-pathology` | 51 | 37 | 1 | 13 |
| `psychoanalysis-experience-humanism` | 29 | 21 | 7 | 1 |
| `critical-sociocultural-narrative` | 50 | 49 | 1 | 0 |
| `oral-exam-comparison-workshop` | 40 | 26 | 11 | 3 |

These outputs now form the base live full NotebookLM deck, after filtering out
`auto_rejected` cards and folding in the reviewed gap-repair and deterministic
coverage-closure supplements described below.

## Gap-Repair Workflow

The matrix/source coverage audit currently drives a targeted gap-repair pass
for missing or weak high-priority units. This is not a replacement full-course
deck; it is a surgical candidate-generation pass for coverage gaps in the live
full NotebookLM deck.

Current gap-repair run:

- run ID: `gap-repair-20260526-high-priority`
- plan:
  `shows/personlighedspsykologi-en/flashcards/coverage/gap_repair_notebook_plan.md`
- source policy: processed matrix/source-basis Markdown only; no existing
  Freudd cards and no raw student-note PDFs/DOCX files are uploaded
- source-pack root:
  `notebooklm-podcast-auto/personlighedspsykologi/flashcard_lab/runs/gap-repair-20260526-high-priority/packs/`

The three repair notebooks are:

| Notebook | Purpose |
|---|---|
| `gap-repair-comparisons-traps` | comparison-target and likely-misunderstanding gaps |
| `gap-repair-orientation-method` | orientation-point and method/evidence gaps |
| `gap-repair-source-basis` | source-basis nuance gaps |

Run result, 2026-05-26:

| Notebook | NotebookLM ID | Raw | Candidate | Needs review | Auto rejected |
|---|---|---:|---:|---:|---:|
| `gap-repair-comparisons-traps` | `ba9adb81-c57b-4b21-8018-8de553808082` | 25 | 17 | 4 | 4 |
| `gap-repair-orientation-method` | `de8cee83-a875-4dcf-9c21-8e642baa5a79` | 17 | 10 | 1 | 6 |
| `gap-repair-source-basis` | `8f5a1c3c-881e-486d-9f6d-e19f7652da72` | 15 | 14 | 1 | 0 |

Total: 57 raw repair cards, 41 `candidate`, 6 `needs_review`, and 10
`auto_rejected`. A local scan of normalized candidates found no student names,
local paths, source-note IDs, coverage-field labels, or target/gap labels in
the card text. The run output is intentionally local and gitignored under
`runs/gap-repair-20260526-high-priority/`.

Review and promotion result:

- Gemini reviewed the 47 non-rejected repair candidates in one call using the
  corrected gap-repair rubric where overlap with the live deck is not, by
  itself, a rejection reason.
- Decisions artifact:
  `shows/personlighedspsykologi-en/flashcards/coverage/gap_repair_review_decisions.json`
- result: 46 `accept`, 1 `merge_with_existing`, 0 `edit`, 0 `reject`
- live full NotebookLM deck after gap-repair promotion: 280 cards
- coverage after gap-repair promotion: high-priority missing/weak units reduced
  from 57 to 14

## Deterministic Coverage Closure

Oskar's current target is 100% deterministic matrix/source coverage for the
live Freudd deck. The final closure pass uses the validated matrix and current
coverage report directly, not another NotebookLM generation round, so every
remaining `missing` or `weak` coverage unit receives a small traceable card.

Coverage-closure result, 2026-05-26:

- artifact:
  `shows/personlighedspsykologi-en/flashcards/coverage/coverage_closure_flashcards.json`
- Markdown review view:
  `shows/personlighedspsykologi-en/flashcards/coverage/coverage_closure_flashcards.md`
- generator:
  `scripts/build_personlighedspsykologi_coverage_closure_flashcards.py`
- closure cards: 39 total
- fields closed: 5 `central_concepts`, 8 `limitations`, 2
  `method_evidence_style`, 12 `source_note_basis`, and 12 `strengths`
- final live full NotebookLM deck: 319 cards
- final coverage audit: 367 matrix units, 209 `strong`, 158 `partial`, 0
  `missing`, 0 `weak`, and 0 high-priority missing/weak units

## Answer-Enrichment Overlay

The first answer-enrichment pass targets the 39 deterministic coverage-closure
cards because those were intentionally minimal and many had label-only or
single-clause answers. The enrichment is stored as a fail-closed overlay, not as
manual edits to the generated deck.

- overlay JSON:
  `shows/personlighedspsykologi-en/flashcards/answer_enrichment_overrides.json`
- overlay Markdown:
  `shows/personlighedspsykologi-en/flashcards/answer_enrichment_overrides.md`
- validator/applicator:
  `notebooklm_queue/personlighedspsykologi_answer_enrichment.py`
- applied by:
  `scripts/build_personlighedspsykologi_full_notebooklm_flashcards.py`
- enriched cards: 39
- enriched answer length: 22-32 words
- safety contract: the builder fails if `old_back_text` is stale, a target
  card is missing, a new answer is too short/long, or learner-facing text leaks
  local paths, student-note names, source-note IDs, or hidden provenance

The live deck remains 319 cards after enrichment, and the deterministic
coverage audit remains at 0 `missing`, 0 `weak`, and 0 high-priority
missing/weak units.

## Learner-Facing Provenance Cleanup

Freudd learners should see the course concepts, not the internal data pipeline.
The full-deck builder therefore removes hidden provenance phrases such as
`ifølge matrixen`, `matrixen`, `kildegrundlag`, `kildesubstrat`, `substrat`,
and English `source` from learner-facing card fronts, answers, and background
text. Conceptual uses of Danish words such as `kilde til evidens` or
`ressourceorienteret` are allowed when they are part of the psychology content.

This cleanup is enforced in
`notebooklm_queue/personlighedspsykologi_full_notebooklm_flashcards.py` and by
`scripts/check_personlighedspsykologi_artifact_invariants.py`.

## Background Overlay

The first background pass adds an optional `Baggrund` layer to every live
flashcard. It explains why the answer is useful for theory understanding or
oral-exam comparison without naming the internal matrix, source-intelligence
artifacts, source-note IDs, or student notes to the learner.

- overlay JSON:
  `shows/personlighedspsykologi-en/flashcards/card_background_overlays.json`
- overlay Markdown:
  `shows/personlighedspsykologi-en/flashcards/card_background_overlays.md`
- validator/applicator:
  `notebooklm_queue/personlighedspsykologi_flashcard_backgrounds.py`
- generator:
  `scripts/generate_personlighedspsykologi_flashcard_backgrounds.py`
- applied by:
  `scripts/build_personlighedspsykologi_full_notebooklm_flashcards.py`
- background cards: 319
- background length: 38-60 words
- safety contract: each background is keyed by `card_id`, `old_front_text`,
  and `old_back_text`; stale cards, missing cards, too-short/too-long
  backgrounds, or hidden-provenance leakage block the build.

Rebuild the closure, live deck, and audit in order:

```bash
./.venv/bin/python scripts/build_personlighedspsykologi_coverage_closure_flashcards.py
./.venv/bin/python scripts/build_personlighedspsykologi_full_notebooklm_flashcards.py
./.venv/bin/python scripts/generate_personlighedspsykologi_flashcard_backgrounds.py
./.venv/bin/python scripts/build_personlighedspsykologi_full_notebooklm_flashcards.py
./.venv/bin/python scripts/audit_personlighedspsykologi_flashcard_coverage.py
```

Export the processed packs and committed plan:

```bash
./.venv/bin/python scripts/export_personlighedspsykologi_notebooklm_gap_repair_packs.py
```

Inspect intended NotebookLM commands without creating notebooks:

```bash
./.venv/bin/python scripts/run_personlighedspsykologi_notebooklm_gap_repair.py \
  --dry-run \
  --storage notebooklm-podcast-auto/profiles/nguyenanhpho19_storage_state.json
```

Run the real repair generation when auth/quota are healthy:

```bash
./.venv/bin/python scripts/run_personlighedspsykologi_notebooklm_gap_repair.py \
  --storage notebooklm-podcast-auto/profiles/nguyenanhpho19_storage_state.json
```

The runner creates one NotebookLM notebook per repair pack, downloads the
generated JSON/Markdown cards, and normalizes them into review-only candidate
artifacts under the ignored run folder. Review and promotion remain separate:
gap-repair cards must be checked against the live deck and matrix before any
Freudd import or merge.

## Current Pilot

The first live pilot run is:

- run ID: `pilot-20260525-critical-sociocultural-narrative`
- notebook ID: `6ba89f27-181a-44df-97e2-15f801974bb7`
- raw NotebookLM flashcards: 80
- normalized status counts: 60 `candidate`, 19 `needs_review`, 1
  `auto_rejected`
- Gemini review: 60 `accept`, 19 `edit`, 1 `reject` using
  `gemini-3.1-pro-preview`

The historical pilot run output remains local review material. Its formerly live
Gemini-reviewed promotion artifacts are archived under
`shows/personlighedspsykologi-en/flashcards/archive/retired-live-decks-2026-05-26/`.

## Review Contract

- Do not import NotebookLM cards directly into Freudd.
- Treat every NotebookLM card as a candidate until reviewed.
- Do not upload existing Freudd cards to NotebookLM as source material.
- Review candidates against the existing Freudd deck after generation and before promotion.
- Reject cards that leak student names, local paths, or source-note provenance.
- Reject or edit generic definition cards that do not add exam-useful recall,
  comparison, or trap-prevention value.
- Keep accepted alternatives in a separate variants deck unless a later task
  explicitly merges them into the canonical matrix deck.
