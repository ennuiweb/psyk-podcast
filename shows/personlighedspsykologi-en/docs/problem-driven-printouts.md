# Problem-Driven Printouts

This document describes the canonical learner-facing printout mode for
`personlighedspsykologi`.

The problem-driven mode is no longer only an alternative experiment. It is the
canonical pedagogical direction for the printout system and is implemented in
the main schema-v3 engine:

```text
notebooklm_queue/personlighedspsykologi_printouts.py
```

The `printout_review` workspace is now the candidate/QA lane for the same
engine. The older three-sheet scaffold structure remains legacy compatibility
context only.

All candidate printouts used to test this variant must be fresh from-source
generations. Existing baseline printouts may be used for comparison, but never
as seed material for a review candidate.

Current canonical render preference:

- keep completion markers/check boxes off by default
- keep `exam_bridge` opt-in; the default candidate bundle should stop at
  `consolidation_sheet` unless the run is explicitly testing transfer load

## Intended Learner Fit

This mode is aimed at learners who do not reliably engage with passive
information intake, but do engage when the material gives them:

- a problem to solve
- a question to answer
- something specific to find
- short closure events and visible progress

This is especially relevant when initiation friction, attention resistance, and
working-memory load are stronger barriers than raw reasoning ability.

## Core Hypothesis

The reading should not feel like a wall of information to absorb before any
reward arrives.

It should feel like a sequence of solvable tasks.

The design unit is:

- a problem
- a search task
- a decision
- a proof
- a small win

## Reward Structure

The default loop is:

1. `entry hook`
2. `micro-reward loops`
3. `resolution payoff`

Definitions:

- `entry hook`: a task the learner can start within 10 seconds
- `micro-reward loop`: a closure event every 1-3 minutes
- `resolution payoff`: a stronger moment of understanding or correctness

The recommended cognitive sequence is:

1. `search`
2. `model`
3. `challenge`

That means:

- first the learner finds a key sentence, distinction, example, or contradiction
- then the learner builds the model that explains it
- then the learner uses the model to beat a harder question

## Section Mapping

Keep the schema-v3 section boundaries for now, but change the pedagogical role
of each section.

### `reading_guide` as Mission Brief

The guide should define:

- the one main problem for this reading
- the concrete win condition
- what the learner should ignore on a first pass
- where the first reward will come from

Good framing:

- "Your job is to decide why Lewis rejects stable traits."
- "You only need enough of the text to settle this dispute."

Weak framing:

- "This reading is important because..."

### `abridged_reader` as Guided Solve Path

The abridged reader should not only explain the text. It should walk the
learner through a chain of local problems.

It should also be self-contained enough that the learner can continue into the
active-reading and consolidation sheets without opening the original text.

Each section should clearly show which delproblem it is helping to solve.

Each section should preferably contain:

- one local question or tension
- one compact explanation that resolves it
- one short original passage only when exact wording matters
- one short closure check

Good section goal:

- "Which model fails on the regression problem?"

Weak section goal:

- "Here is a general explanation of this subsection."

### `active_reading` as Guided Solve Sheet

This section should feel like a solve sheet based on the abridged reader, not a
detective worksheet in the source PDF and not a second recall test.

Prioritize:

- open-book work with the abridged reader
- short term-finding
- binary or narrow decisions
- short paragraph answers where the learner needs to state the move clearly
- progress through the listed delproblemer

Good task shapes:

- find the term that settles the issue
- choose between model A and model B
- state the author's target of criticism in one short line
- write 3-4 sætninger that explain the decisive move in plain language

Weak task shapes:

- discuss the text broadly
- open the PDF just to complete the worksheet
- make the whole sheet into closed-book recall

### `consolidation_sheet` as Model Builder

This sheet should make the learner reconstruct the mechanism with minimal
working-memory load.

It should be the main recall artifact and should be doable after reading only
the abridged reader.

Useful forms:

- fill the missing concept in a causal chain
- complete a contrast table
- reconstruct a flow diagram
- connect one concept to one example and one implication

The point is not just recall. The point is the reward of seeing the model lock
into place.

### `exam_bridge` as Boss Fight

This section should deliver one meaningful final challenge after the smaller
wins.

It should ask the learner to:

- use the model
- defend a distinction
- apply the theory to a case
- avoid a likely exam trap

The final task should feel like:

- "Now prove you actually have it."

## Language Policy

Use language that signals action and closure:

- solve
- find
- decide
- prove
- defend
- catch

Reduce language that signals diffuse obligation:

- read this section
- reflect on
- discuss broadly

## Printout Flow

The default flow for this mode is:

1. mission brief
2. guided solve path
3. evidence hunt
4. model reconstruction
5. boss fight

For a low-energy session, the minimum viable flow is:

1. mission brief
2. one guided solve section
3. one evidence hunt
4. one final decision

## Example Transformations

Instead of:

- "Read pages 73-76 because they are important."

Use:

- "Use pages 73-76 to answer this: why does Lewis think continuity comes from
  context rather than stable traits?"

Instead of:

- "Summarize the author's argument."

Use:

- "Find the exact move where the author shifts the cause from the person to the
  context."

Instead of:

- "Mini-check: what is the primary point?"

Use:

- "Verdict: which model survives the regression problem?"

## Evaluation

This mode is the canonical direction, but it should still be evaluated on real
learner use rather than treated as finished just because the docs and engine
agree.

Useful comparisons:

- problem-driven v3 output vs legacy/outdated three-sheet scaffold output
- search-heavy vs model-heavy vs challenge-heavy tasks
- short podcast plus printout vs printout alone

Useful observations:

- which version the learner starts fastest
- which version keeps attention longest
- which version produces the strongest sense of progress
- which version leaves the best recall after a short delay

## Relation To Other Docs

- repo-level design principles: [learning-material-design.md](/Users/oskar/repo/podcasts/docs/learning-material-design.md)
- output-layer boundary and evaluation map: [learning-material-outputs.md](/Users/oskar/repo/podcasts/shows/personlighedspsykologi-en/docs/learning-material-outputs.md)
- current canonical printout contract: [printout-system.md](/Users/oskar/repo/podcasts/shows/personlighedspsykologi-en/docs/printout-system.md)
