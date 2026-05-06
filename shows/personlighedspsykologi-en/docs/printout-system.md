# Reading Printout System

Scope: `personlighedspsykologi` printable reading printouts.

This is an `Output Adaptation Layer` consumer. It is downstream of the core
`Course Understanding Pipeline`, and upstream of any visual presentation layer.
It must not be treated as core source/course understanding.

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

- `reading_guide`: a one-page advance organizer. Its purpose is to lower
  initiation friction, explain why the source matters, mark the reading route,
  and say what not to over-focus on. It is not the abridged reader.
- `abridged_reader`: an ADHD-friendly shortened reading path through the text.
  Its purpose is to preserve the argument's movement while using shorter
  paragraphs, section headings, page anchors, short quote targets, lists, and
  mini-checks. It should make the original source enterable and also work as a
  minimum viable reading path when the full source does not happen.
- `active_reading`: a split active-reading worksheet. Its purpose is to provide
  abridged-reader checks plus short original-source touchpoints.
- `consolidation_sheet`: a consolidation worksheet. Its purpose is to make the
  student retrieve key terms, distinctions, findings, and relations after or
  alongside reading. Diagram tasks support dual coding and relation-building.
- `exam_bridge`: a transfer worksheet. Its purpose is to show how the reading
  can be used in exam answers, which course themes it supports, what
  comparisons it enables, and which misunderstandings would weaken an exam
  response.

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

Default target kit in schema v3:

- `00-reading-guide`
- `01-abridged-reader`
- `02-active-reading`
- `03-consolidation-sheet`
- `04-exam-bridge`

## Abridged-Reader Policy

The `abridged_reader` should be designed around the realistic constraint that
the student may not manage to read the full original source. That should not be
treated as failure. The system should still produce substantial learning when
the abridged reader is the main reading path.

Design principle:

- reading only the `abridged_reader` should be a legitimate minimum viable
  learning path
- the original source should become targeted source contact, not an all-or-
  nothing wall
- source contact should happen through short, high-value touchpoints
- the abridged reader should support completion of the consolidation sheet and
  exam bridge at a useful level
- the source touchpoints should preserve contact with the author's wording,
  nuance, and strongest passages

The abridged reader should mostly use rewritten explanatory prose. It should
not be a copy-pasted source excerpt pack. Use short original anchors only where
the wording matters.

Target mix:

- 80-90% ADHD-friendly rewritten explanation
- 10-20% short quote anchors, quote fragments, and page references
- no long reproduced passages unless a future policy explicitly allows it

Each abridged-reader section should normally include:

- page range or source-location anchor
- short heading for the source move
- compact explanation in short paragraphs
- a few bullets when the source lists concepts, problems, or steps
- one or more short quote anchors when exact wording matters
- one "if you can do one source touchpoint" instruction
- one mini-check that can be answered from the abridged reader

The intended modes are:

- `abridged-only mode`: read `00-reading-guide`, read `01-abridged-reader`,
  answer abridged checks, complete `03-consolidation-sheet`, and use
  `04-exam-bridge`
- `source-touchpoint mode`: after the abridged reader, open the source only for
  5-8 high-value touchpoints
- `full-source mode`: use `02-source-touchpoints` as a guided path through the
  original when energy allows

## Source-Touchpoint Policy

The old unit-test idea is still valuable, but it should not assume that the
student will read the whole PDF linearly. For this course, the next schema
should separate two kinds of active-reading tasks:

- `abridged_checks`: questions answerable from the abridged reader
- `source_touchpoints`: tiny original-source hunts for the most valuable
  passages, definitions, examples, and quote anchors

`source_touchpoints` should be small enough that opening the PDF feels feasible.
They should not say "read the whole section" when a narrower task works.

Good source touchpoint pattern:

```text
Open p. 132. Find the paragraph around the phrase "public action".
Underline one sentence that shows why psychological language is performative.
Stop after you have underlined one sentence.
```

Bad source touchpoint pattern:

```text
Read pp. 129-138 and explain Gergen's theory of relational being.
```

The source-touchpoint list should be shorter than the old unit-test suite:

- default: 5-8 source touchpoints per reading
- each touchpoint should include page/location, action, answer/marking format,
  and stop signal
- touchpoints should prioritize definitions, argument pivots, canonical
  examples, and exam-useful quote anchors

The abridged checks can be more numerous and easier:

- default: 8-12 abridged checks
- answerable from `01-abridged-reader`
- used to confirm understanding before doing consolidation or exam transfer

This means the next implementation should not simply add a fourth PDF. It
should revise the learning flow so the abridged reader becomes central and the
original source becomes approachable through small source visits.

## Implementation Plan

Schema v3 implementation target:

- bump printout schema from `2` to `3`
- rename current `abridged_guide` conceptually to `reading_guide`
- add `abridged_reader` as a first-class JSON section
- replace or split current `unit_test_suite` into `abridged_checks` and
  `source_touchpoints`
- rename rendered cloze/diagram output to `consolidation_sheet`
- add `exam_bridge` as a first-class JSON section

Proposed JSON sections:

- `metadata`
- `reading_guide`
- `abridged_reader`
- `active_reading`
- `consolidation_sheet`
- `exam_bridge`

`active_reading` should contain:

- `abridged_checks`
- `source_touchpoints`

Proposed rendered files:

- `00-reading-guide`
- `01-abridged-reader`
- `02-active-reading`
- `03-consolidation-sheet`
- `04-exam-bridge`

Validation requirements to add:

- `abridged_reader.sections` must preserve source order
- each abridged-reader section must include a source location, explanation,
  quote anchors or explicit `no_quote_anchor_needed`, a source touchpoint, and
  a mini-check
- quote anchors must be short
- `abridged_checks` must be answerable from the abridged reader
- `source_touchpoints` must be fewer, narrower, and source-location anchored
- `exam_bridge` must connect the reading to course themes, likely exam uses,
  comparison targets, and misunderstanding traps

Migration rule:

- Existing schema-v2 artifacts can still be rerendered with the v2 path.
- Schema-v3 generation should require `--force` for existing sources so old
  JSON is not silently treated as equivalent.
- Keep JSON canonical. Markdown/PDF remain derived views.

## Data Contract

Canonical output is JSON:

```text
notebooklm-podcast-auto/personlighedspsykologi/output/<lecture>/printouts/<source_id>/reading-printouts.json
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
- `printouts.active_reading`: abridged checks plus source touchpoints
- `printouts.consolidation_sheet`: fill-in sentences plus blank diagrams
- `printouts.exam_bridge`: transfer sheet for course and exam use

For compatibility, live JSON artifacts may still include a mirrored
`scaffolds` object and legacy alias files under `.../scaffolding/...` while
the repo finishes migrating readers and generated history.

The canonical source for the current printout prompt version and the human
setup label is `shows/personlighedspsykologi-en/prompt_versions.json`.

Legacy schema-v2 artifacts can still be rerendered, but new live generation
targets schema v3.

## Current Generation Status

Status date: 2026-05-06.

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
notebooklm-podcast-auto/personlighedspsykologi/output/<lecture>/printouts/<source_id>/
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
  -path '*/printouts/*/reading-printouts.json' \
  | rg '/W0[1-3]L[12]/' \
  | sort
```

Count completed week 1-3 artifacts:

```bash
find notebooklm-podcast-auto/personlighedspsykologi/output \
  -path '*/printouts/*/reading-printouts.json' \
  | rg '/W0[1-3]L[12]/' \
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
