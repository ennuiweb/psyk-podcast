# Reading Printout System

Scope: `personlighedspsykologi` printable reading printouts.

This is an `Output Adaptation Layer` consumer. It is downstream of the core
`Course Understanding Pipeline`, and upstream of any visual presentation layer.
It must not be treated as core source/course understanding.

## Canonical Status

The current canonical printout system is the schema-v3 engine under:

```text
notebooklm_queue/personlighedspsykologi_printouts.py
```

Its schema-v3, problem-driven behavior is the canonical product and pedagogy
contract for future printout work.

The review workspace under
`notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/`
is the candidate/QA lane. It imports the canonical engine and keeps candidate
PDFs flat in `review/`.

The older three-sheet `abridged_guide` / `unit_test_suite` / `cloze_scaffold`
implementation is preserved as
`notebooklm_queue/personlighedspsykologi_printouts_legacy.py` for compatibility
context only.

Current canonical-generation rule:

- canonical review printouts must always be generated fresh from source
- canonical baseline artifacts are comparison references only, never seed input
- rerendering is allowed only for already-fresh candidate artifacts
- completion markers/check boxes are off by default
- the current review workspace exports `active_reading` before `abridged_reader` in filenames as an operator-facing bundle-order choice; do not read that as a change to the underlying pedagogical dependency on `abridged_reader`

## Purpose

The printout generator creates offline reading worksheets that make dense
course readings easier to enter and complete. The goal is not to summarize the
text away. The goal is to give the student a structured reading route with many
small completion signals.

The overall purpose of the printout kit is to create better reading conditions
for dense `personlighedspsykologi` course texts, especially when executive
function, attention regulation, working memory, and initiation are the main
barriers. The printouts should not replace the source text. They should make it
easier to start the source, stay oriented inside it, notice the important moves,
and convert the reading into usable exam knowledge.

The kit should solve five different learning jobs:

- initiation: make it obvious where to start and what counts as progress
- comprehension: reduce dense prose into a navigable argument path
- attention maintenance: create small concrete tasks and visible completion
- consolidation: turn concepts, distinctions, and relations into recallable
  structures
- transfer: make the reading usable for course comparisons and exam answers

Each printout must have one primary job. Avoid one large "everything sheet";
that creates clutter and defeats the ADHD-friendly purpose.

## Printout Purposes

Schema v3 core artifacts:

Length rule:

- printout length should be dynamic, not flat
- shorter/simpler readings should generate shorter kits with fewer sections and tasks
- longer or denser readings may use the upper end of the safe ranges
- use source length and concept density as the main budget signals, but keep
  the existing artifact roles stable and do not let any single worksheet bloat
  into a mini-book
  - in practice this mostly changes counts of teaser paragraphs, abridged
    sections, solve steps, fill-ins, and diagram tasks
  - it should not change the five-file structure itself

- `reading_guide`: a one-page appetizer. Its purpose is to lower initiation
  friction by rendering as a short coherent teaser text that stages a few
  unresolved problems from the reading and makes the learner want to read on.
  It may weave in short original phrases, but it should not feel like an
  administrative overview sheet or a fill-out worksheet. Prefer several short
  teaser paragraphs with visible breathing room on the page, not a few dense
  essay blocks. At least one early paragraph should hook the learner through
  something concrete in the text, not only abstract metatheory.
- `abridged_reader`: an ADHD-friendly shortened reading path through the text.
  Its purpose is to preserve the argument's movement while using shorter
  paragraphs, section headings, page anchors, short quote targets, occasional
  short original passages when wording matters, and lists. It should work as a
  minimum viable reading path even when the full source does not happen. It is
  a reading text, not a worksheet, so it should not contain blanks, checkboxes,
  or mini-tests.
- `active_reading`: a guided solve worksheet. Its purpose is to let the student
  solve the reading guide's subproblems with `abridged_reader` open. It should
  feel explicitly open-book and visibly different from recall practice. It
  should use fewer, larger solve steps rather than a long fact-quiz. Keep
  internal location support in the structured data, but do not print visible
  helper lines such as `Abridged reader sektion 3` on the worksheet itself.
- `consolidation_sheet`: a consolidation worksheet. Its purpose is to make the
  student retrieve key terms, distinctions, findings, and relations after
  reading the abridged reader. This should be the main recall sheet. Diagram
  tasks support dual coding and relation-building. It should feel narrower and
  more memory-first than `active_reading`. It must not depend on original
  figures, page numbers, or reopening the source PDF. Keep any repair hints in
  the hidden structure, not as visible helper lines on the printed sheet.
- `exam_bridge`: a transfer worksheet. Its purpose is to show how the reading
  can be used in exam answers, which course themes it supports, what
  comparisons it enables, and which misunderstandings would weaken an exam
  response. It should read like oral-exam cues, not like a long advice
  handout, and it should prefer short spoken-style cue labels such as `Brug`,
  `Sammenlign`, `Sig højt`, and `Undgå`. It remains part of the schema, but it
  is an optional printout and should not be rendered by default.

Optional render-layer feature:

- `completion_markers`: a legacy/reversible layout flag. The current canonical
  renderer keeps check boxes off by default.

Visual style contract:

- `bold`: only for fast-scanning targets such as section labels, task verbs,
  and short cue heads
- `italics`: only for short original wording and decisive quoted phrases
- `monospace`: only for navigational metadata such as margin text, page labels,
  and page/section anchors

This contract should be enforced by rendering, not left to the model's
stylistic judgment.

Optional add-on artifacts:

- `misunderstanding_traps`: for dense theory texts where students are likely to
  misread a central move. Its purpose is conceptual error prevention.
- `argument_skeleton`: for philosophical or theory-heavy texts. Its purpose is
  to expose the source's claim-target-method-implication structure.
- `concept_ladder`: for concept-heavy texts. Its purpose is to move from term
  recognition to course-level and exam-level use.
- `quote_quarry`: a short list of quote targets only. Its purpose is to help
  locate a few high-value textual anchors without reproducing long passages.
- `answer_key`: optional and separate. Its purpose is delayed self-checking,
  never first-pass reading.

Default rendered kit in schema v3:

- `00-reading-guide`
- `01-abridged-reader`
- `02-active-reading`
- `03-consolidation-sheet`

Optional rendered add-on:

- `04-exam-bridge`

Review-lane export note:

- the experimental review workspace currently exports `00-cover`,
  `01-reading-guide`, `02-active-reading`, `03-abridged-version`,
  `04-consolidation-sheet`, and optional `05-exam-bridge`
- that numbering is a review-workspace export convention, not the canonical
  schema-role ordering

## Abridged-Reader Policy

Across all rendered printouts, keep metatext and helper language minimal. Avoid
labels such as "how to use this sheet", "role in the workflow", explicit stop
signals, and other teacherly scaffolding unless a specific artifact genuinely
needs them.

The `abridged_reader` should be designed around the realistic constraint that
the student may not manage to read the full original source. That should not be
treated as failure. The system should still produce substantial learning when
the abridged reader is the main reading path.

Design principle:

- reading only the `abridged_reader` should be a legitimate minimum viable
  learning path
- the original source should not be required for the core worksheet flow
- when exact wording matters, the abridged reader should bring a short original
  passage to the student instead of sending the student back to the PDF
- the abridged reader should support completion of the consolidation sheet and
  exam bridge at a useful level
- optional source contact is an add-on, not the core reading path

The abridged reader should mostly use rewritten explanatory prose. It should
not be a copy-pasted source excerpt pack. Use short original anchors by default
and only short paragraph-length excerpts where the wording clearly matters.

Target mix:

- 80-90% ADHD-friendly rewritten explanation
- 10-20% short quote anchors and occasional short original passages
- no long reproduced passages unless a future policy explicitly allows it

Each abridged-reader section should normally include:

- page range or source-location anchor
- short heading for the source move
- the local problem that this section resolves
- a pointer to which subproblem from `reading_guide` it advances
- compact explanation in short paragraphs
- a few bullets when the source lists concepts, problems, or steps
- one or more short quote anchors when exact wording matters
- at most one short original passage when the exact wording earns its place
- one mini-check that can be answered from the abridged reader

The intended modes are:

- `abridged-only mode`: read `00-reading-guide`, read `01-abridged-reader`,
  solve `02-active-reading`, complete `03-consolidation-sheet`, and use
  `04-exam-bridge`
- `repair mode`: if a recall answer fails, reopen only the referenced section
  of `01-abridged-reader`
- `source-contact add-on`: optional future source-touchpoint sheets may still
  exist, but they are not part of the core five-file flow

## Worksheet Flow

The old unit-test idea is still valuable, but for this course `active_reading`
and `consolidation_sheet` should no longer do the same job.

- `active_reading`: guided solve tasks answerable from the abridged reader with
  the reader open
- `consolidation_sheet`: later recall tasks done from memory first

The boundary should be visible in the rendered printouts:

- `abridged_reader`: read-only compact text
- `active_reading`: open-book solve sheet
- `consolidation_sheet`: closed-book recall and repair sheet

Good active-reading pattern:

```text
Delproblem 2: Afgør om teksten placerer kontinuitet i personen eller i
konteksten.
Brug abridged reader sektion 3.
```

Bad active-reading pattern:

```text
Luk arket og genkald hele teorien fra hukommelsen.
```

The active-reading sheet should usually contain:

- default: 4-8 solve steps
- fewer, larger prompts rather than a long string of one-word checks
- a mix of narrow decisions and short paragraph explanation, with term-finding
  only when genuinely central
- varied task verbs such as `Skriv`, `Vælg`, `Forklar`, and `Afgør` so the
  sheet does not read like the same quiz prompt repeated
- answerable from `01-abridged-reader`
- clear references back to abridged-reader sections
- enough answer space for paragraph tasks, not only one-line responses

The consolidation sheet should be the recall phase after that:

- default: 5-8 fill-in sentences plus 1-3 diagram tasks
- solvable from `01-abridged-reader` alone
- `where_to_look` should point to abridged-reader sections, not source pages
- no tasks should depend on original figures, page references, or reopening the
  PDF
- completed from memory first and checked afterward

This is the current canonical behavior in the main printout engine.

## Main-Code Contract

The main builder now targets schema v3. The legacy three-sheet scaffold model is
kept only in `notebooklm_queue/personlighedspsykologi_printouts_legacy.py`.

Main-code schema:

Proposed JSON sections:

- `metadata`
- `reading_guide`
- `abridged_reader`
- `active_reading`
- `consolidation_sheet`
- `exam_bridge`

`active_reading` should contain:

- `solve_steps`

Canonical rendered files:

- `00-cover`
- `01-reading-guide`
- `02-active-reading`
- `03-abridged-version`
- `04-consolidation-sheet`
- `05-exam-bridge` only when explicitly enabled

Validation requirements to add:

- `abridged_reader.sections` must preserve source order
- each abridged-reader section must include a source location, explanation,
- quote anchors or explicit `no_quote_anchor_needed`, optional short original
  passages when wording matters, a local problem, a subproblem link, and a
  mini-check
- quote anchors must be short
- original passages must stay short enough to function as one decisive excerpt
- `solve_steps` must be answerable from the abridged reader
- `abridged_reader_location` and `where_to_look` must point to abridged-reader
  sections rather than source pages
- `active_reading` must support both short answers and short paragraph answers
- `exam_bridge` must connect the reading to course themes, likely exam uses,
  comparison targets, and misunderstanding traps

Migration rule:

- Existing schema-v2 artifacts can still be rerendered with the v2 path.
- Schema-v3 generation should require `--force` for existing sources so old
  JSON is not silently treated as equivalent.
- Keep JSON canonical. Markdown/PDF remain derived views.

## Data Contract

Current canonical review JSON lives under each review output root's hidden
artifact directory:

```text
notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/<review-output-root>/.scaffolding/<source_id>/reading-scaffolds.json
```

The target main-code JSON path after integration is:

```text
notebooklm-podcast-auto/personlighedspsykologi/output/printout-json/<source_id>/reading-printouts.json
```

The JSON artifact is the source of truth for later visual work. Markdown and
PDF files are render targets derived from the JSON, not the canonical content
format.

Current artifact contract:

- `artifact_type`: `reading_printouts`
- `schema_version`: `3`
- `generator.prompt_version`: `personlighedspsykologi-reading-printouts-v3`
- `printouts.reading_guide`: one-page advance organizer
- `printouts.abridged_reader`: ADHD-friendly minimum viable reading path
- `printouts.active_reading`: abridged-only guided solve steps
- `printouts.consolidation_sheet`: active-recall fill-in sentences plus blank
  diagrams
- `printouts.exam_bridge`: transfer sheet for course and exam use

For compatibility, live JSON artifacts may still include a mirrored
`scaffolds` object. The current main output contract no longer writes
`scaffolding/` directories; review/evaluation internals still use
`.scaffolding/` under the review workspace only.

The canonical source for the current printout prompt version and the human
setup label is `shows/personlighedspsykologi-en/prompt_versions.json`.

Legacy schema-v1/v2 artifacts can still exist and may be rerendered for
comparison, but new canonical generation targets schema v3 through the main
printout engine. The review workspace is only the candidate/QA lane.

## Legacy Main-Code Generation Status

Status date: 2026-05-06.

This section describes older main-code output history and should not be treated
as proof of current canonical problem-driven coverage. Check the
`printout_review` run manifests and PDFs for current canonical output.

Weeks 1-3 are complete for reading sources. Each completed source has:

- `reading-printouts.json`
- `00-reading-guide.md` and `.pdf`
- `01-abridged-reader.md` and `.pdf`
- `02-active-reading.md` and `.pdf`
- `03-consolidation-sheet.md` and `.pdf`
- `04-exam-bridge.md` and `.pdf`

Completed source IDs:

- `w01l1-grundbog-kapitel-1-introduktion-til-personlighed-1e727647`
- `w01l1-lewis-1999-295c67e3`
- `w01l2-koutsoumpis-2025-96f4dcf7`
- `w01l2-mayer-and-bryan-2024-07faf915`
- `w01l2-phan-et-al-2024-bf3395d7`
- `w02l1-columbus-and-strandsbjerg-2025-2962b765`
- `w02l1-zettler-et-al-2020-0c54e6e4`
- `w02l2-bleidorn-et-al-2022-25c2d2de`
- `w02l2-li-and-wilt-2025-92f596ad`
- `w03l1-kandler-and-instinske-2025-01535a8e`
- `w03l1-lu-benet-martinez-and-wang-2023-38a36550`
- `w03l1-volk-and-puchalski-2025-60aaf5d0`
- `w03l1-zettler-et-al-2025-6ce9bdc0`
- `w03l2-bach-and-simonsen-2023-d58362ff`
- `w03l2-sharp-and-wall-2021-cb92ecf4`

Count summary:

- completed reading sources: `15`
- canonical JSON artifacts: `15`
- derived Markdown files: `75`
- derived PDF files: `75`

Artifact root:

```text
notebooklm-podcast-auto/personlighedspsykologi/output/printout-json/<source_id>/reading-printouts.json
```

Generation status is determined by the presence of
`reading-printouts.json`. The CLI skips existing artifacts by default unless
`--force` is passed, so it is safe to run the next lecture batch without
regenerating weeks 1-3.

## Source Handling

Gemini reads the actual source files. Local code must not extract, OCR, or
semantically interpret reading PDFs.

Local code may:

- select source IDs from `source_catalog.json`
- attach the source PDF files to Gemini
- pass compact course-understanding context as prioritization guidance
- hash inputs for provenance
- validate Gemini JSON
- render JSON to Markdown/PDF or later web layouts

Gemini receives:

- the actual source PDF file or files
- compact source-card context for the same source
- revised lecture substrate for the lecture when available
- full course synthesis when available
- an explicit prompt-level JSON contract for schema-v3 printout fields

The source PDF remains authoritative. Source cards and course context only
prioritize what matters.

The printout generator intentionally does not send the full schema-v3 contract
as Gemini `response_json_schema`. The v3 printout shape is large enough that
Gemini can reject it at request validation time. Instead, the call uses JSON
response mode, includes the exact output contract in the prompt, and then fails
closed with local validation before writing artifacts.

## Quality Contract

The generated worksheets should be operational, not merely pretty summaries.
Each task should tell the student what to look for, where to look, and when to
stop.

Required behavior:

- The preparatory guide explains why the reading matters and gives a
  chronological reading route with stop criteria.
- The abridged reader is usable as the minimum viable reading path, while still
  pointing back to the original source through short source touchpoints.
- Abridged checks are short, concrete, chronological, and answerable from the
  abridged reader.
- Source touchpoints are tiny original-source hunts, not disguised full-reading
  assignments.
- Active-reading tasks must not ask for essays, reflection, broad discussion,
  or whole-text synthesis.
- `answer_shape` must describe answer format only, for example `1 ord`,
  `2 ord`, `et navn`, or `en kort saetning`; it must not add semantic hints.
- Cloze sentences remove exactly one key term, distinction, result, or
  connection.
- Diagram tasks say what to draw and which elements to include, but do not draw
  or answer it.
- Guidance fields must not leak answers through parenthetical hints.
- Quote targets must be short search phrases, not reproduced long passages.
- Tone should be serious and practical for a university student, not childish
  or motivational.

Known failure mode from old prompt-only examples:

- they became normal summaries with blanks added
- they lacked chronological hidden-object tasks
- they lacked explicit stop signals
- they did not use course-level context for prioritization
- they were too easy to skim without actually reading the source

## Commands

List completed week 1-3 printout JSON artifacts:

```bash
find notebooklm-podcast-auto/personlighedspsykologi/output \
  -path '*/printout-json/*/reading-printouts.json' \
  | rg '/w0[1-3]l[12]-' \
  | sort
```

Count completed week 1-3 artifacts:

```bash
find notebooklm-podcast-auto/personlighedspsykologi/output \
  -path '*/printout-json/*/reading-printouts.json' \
  | rg '/w0[1-3]l[12]-' \
  | wc -l
```

Generate the next lecture pair as JSON/Markdown only:

```bash
./.venv/bin/python scripts/build_personlighedspsykologi_printouts.py \
  --lectures W04L1,W04L2 \
  --no-pdf \
  --continue-on-error \
  --skip-preflight
```

Render PDFs for generated printouts without Gemini calls:

```bash
./.venv/bin/python scripts/build_personlighedspsykologi_printouts.py \
  --lectures W04L1,W04L2 \
  --rerender-existing \
  --continue-on-error
```

Continue a wider batch safely. Existing printout JSON files are skipped unless
`--force` is passed:

```bash
./.venv/bin/python scripts/build_personlighedspsykologi_printouts.py \
  --lectures W04L1,W04L2,W05L1,W05L2 \
  --no-pdf \
  --continue-on-error \
  --skip-preflight
```

Plan W11L1 reading printouts without API calls:

```bash
./.venv/bin/python scripts/build_personlighedspsykologi_printouts.py --lectures W11L1 --dry-run
```

Generate one source as JSON/Markdown only:

```bash
./.venv/bin/python scripts/build_personlighedspsykologi_printouts.py \
  --source-id w11l1-gergen-1999-73c2217e \
  --no-pdf \
  --force \
  --skip-preflight
```

Generate all W11L1 reading printouts as JSON/Markdown only:

```bash
./.venv/bin/python scripts/build_personlighedspsykologi_printouts.py \
  --lectures W11L1 \
  --no-pdf \
  --continue-on-error \
  --skip-preflight
```

Normalize/rerender an existing printout JSON without a Gemini call:

```bash
./.venv/bin/python scripts/build_personlighedspsykologi_printouts.py \
  --source-id w11l1-gergen-1999-73c2217e \
  --rerender-existing \
  --no-pdf
```

Omit `--no-pdf` only when local PDF rendering is desired. PDF rendering
requires `pandoc`; `xelatex` is used automatically when available.

## Validation

The local validator fails closed when Gemini returns weak worksheet structure.
Before validation, the builder deterministically normalizes `answer_shape`
fields to remove semantic hints such as `der beskriver ...`, so format cleanup
does not require a paid retry. It also truncates overlong quote anchors before
writing artifacts, so Gemini cannot accidentally turn a short search phrase
into a reproduced passage. Other deterministic repairs are limited to shape,
not substantive interpretation: missing question marks are added to question
fields, comma-separated diagram elements are converted to lists, and too-short
exam-move lists are padded with standard exam-transfer moves. Parenthetical
hints are stripped from stop/done signals before validation because those hints
often leak the answer.
It checks:

- required top-level sections
- cardinalities for overviews, abridged-reader sections, active-reading checks,
  source touchpoints, cloze tasks, and diagrams
- non-empty operational fields
- short active-reading questions ending in `?`
- rejection of broad prompts such as `diskuter`, `reflekter`, and `vurder`
- rejection of semantic hints inside `answer_shape`
- exactly one blank marker per cloze sentence
- no answer leaks in operational hint fields
- short quote targets
- at least two required elements per diagram

This validation is intentionally strict. It is cheaper to retry a failed source
than to silently accumulate low-quality printouts.
