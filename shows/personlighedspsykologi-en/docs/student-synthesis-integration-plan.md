# Student Synthesis Integration Plan

Created: 2026-05-24

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

The first useful version is done when:

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

## Recommended Next Step

Build `exam_theory_matrix.json` as the first concrete artifact, using the two
student files as input and validating the result against the current course
artifacts. Then generate a W12L1-focused master comparison PDF from that
matrix.
