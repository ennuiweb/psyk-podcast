# Problem-Driven V1

Use this prompt overlay for learners who engage more reliably when the material
feels like a sequence of solvable problems instead of a wall of information.

## Learner Fit

Assume the learner benefits from:

- a concrete question to answer
- something specific to find
- a short decision to make
- visible progress and frequent closure signals

## Core Rule

Keep the full five-section content schema and the validation contract.
`exam_bridge` stays in the JSON, but it is an optional printout at render time
and should not be printed by default.

Generate every candidate fresh from the source text and current context. Do not
seed from canonical scaffolds, prior candidate wording, or baseline printout
artifacts.

Change the pedagogical feel.

Let the amount of material scale with the reading. Shorter or simpler readings
should stay on the lower end of the safe ranges. Longer or denser readings may
use the upper end, especially for abridged-reader sections, active-reading
solve steps, and consolidation tasks.

The printout should feel like:

- a mission brief
- a problem map
- a guided solve path
- a solve sheet
- a recall lock-in sheet
- a boss fight

## Section Roles

### `reading_guide`

Do not make this a dry overview sheet.

Make the visible sheet a short, coherent teaser text of roughly half to one
page.

Prefer 4-6 short paragraphs rather than 2-3 dense blocks. Most paragraphs
should be only 1-3 sentences long and should create a readable visual rhythm on
the page.

At least one early paragraph should start from a concrete hook inside the text:
an image, a term, a scene, a test format, or a striking formulation. Do not
let every paragraph stay at abstract metatheory level.

Weave in 2-4 short original phrases or sentence fragments from the reading
where they sharpen the tension, but do not render the sheet as excerpt blocks
or quote-followed-by-question blocks.

Good:

- a continuous prose teaser that builds tension
- several short paragraphs with visible breathing room
- at least one concrete hook that makes the reading feel vivid rather than purely abstract
- original wording embedded where it sharpens the problem
- a feeling of "wait, what does that mean?"

Avoid:

- generic importance statements
- long essay-like walls of text
- administrative headings like "main problem" or "how to use this sheet"
- point-form overview before the text has created any curiosity
- standalone fill-out questions or answer lines

### `abridged_reader`

Each section should revolve around one local tension, decision, or problem.

Each section should also make explicit which subproblem it helps solve.

The reader should be self-contained enough that the student can continue into
`active_reading`, `consolidation_sheet`, and `exam_bridge` without opening the
original text.

The learner should feel:

- "I solved that section."

not:

- "I passively received that section."
- "I am already doing worksheet tasks."

If exact wording matters, include one short original passage directly in the
section and explain why it is there. Do not send the learner back to the PDF
for core understanding.

Do not put blanks, mini-quizzes, checkboxes, or fill-out prompts inside
`abridged_reader`. It must read like a compact reading text, not a worksheet.

### `active_reading`

Use this as a guided solve sheet based on `abridged_reader` alone.

The learner should work with the abridged reader open, not from memory first.

Prefer:

- fewer, larger solve steps
- narrow decisions
- short paragraph explanations
- term-finding only when the term is genuinely central
- visible progress toward the listed subproblems
- explicit open-book feel: the learner may keep `abridged_reader` open all the
  way through
- prompt variation that sounds like real work with the text, for example
  `Skriv`, `Vælg`, `Forklar`, or `Afgør`, instead of repeating the same stock
  lead-in before every step
- no visible helper lines such as `Abridged reader sektion 3` in the rendered
  worksheet; keep that support in the hidden structure, not on the page

Avoid:

- source hunts
- "open the PDF" instructions
- broad summaries
- "reflect on" prompts
- multi-page synthesis questions
- pure closed-book recall as the main mode
- long strings of one-word quiz questions

### `consolidation_sheet`

Use the sheet to make the model lock into place with minimal working-memory
load.

This should now be the main recall sheet, done from memory first and checked
against the abridged reader only afterward.

It should feel clearly different from `active_reading`: shorter prompts,
narrower retrieval targets, and no sense that the student is still "solving the
text" with it open.

Prefer:

- reconstructing a mechanism
- filling a contrast
- rebuilding a causal chain
- short term recall that can be repaired from `abridged_reader`
- no visible `where to look` helper lines in the rendered sheet

Avoid:

- any dependency on original figures or source pages
- tasks that only make sense if the student reopens the PDF

### `exam_bridge`

End with one meaningful final challenge that proves the learner can use the
model.

It should feel like:

- "now prove you have it"

Keep it cue-based and oral-friendly. It should not read like a long advice
handout.

Use short spoken-style cues such as `Brug`, `Sammenlign`, `Sig højt`, and
`Undgå` rather than long coaching prose.

## Reward Loop

Target:

1. fast entry
2. micro-reward loops
3. stronger resolution payoff

The learner should be able to start the first task within 10 seconds.

## Language

Prefer verbs like:

- find
- decide
- prove
- catch
- defend
- settle

Reduce diffuse phrasing like:

- read this section
- reflect on
- discuss broadly

## Style Contract

Do not invent ad hoc emphasis patterns.

Assume the renderer applies a fixed visual contract:

- bold for what should be caught quickly
- italics for short original wording and decisive quoted phrases
- monospace only for navigational metadata such as page or section anchors

Write content that works cleanly with that contract instead of trying to
simulate layout manually.

## Reminder

Do not change the output schema.
Do not leak answers.
Keep tasks short, operational, and finishable.
Keep metatext and helper language minimal across all five printouts.
