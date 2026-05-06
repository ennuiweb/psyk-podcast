# Problem-Driven Scaffolding

This document describes an alternative learner-facing scaffolding mode for
`personlighedspsykologi`.

It is not yet the canonical replacement for the existing scaffold contract in
`scaffolding-system.md`. Treat it as an explicit design variant to implement
and test.

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

Each section should preferably contain:

- one local question or tension
- one compact explanation that resolves it
- one source touchpoint
- one short closure check

Good section goal:

- "Which model fails on the regression problem?"

Weak section goal:

- "Here is a general explanation of this subsection."

### `active_reading` as Evidence Hunt

This section should feel like a detective worksheet, not a broad quiz.

Prioritize:

- binary or narrow decisions
- source hunts
- proof tasks
- trap detection

Good task shapes:

- find the sentence that proves the claim
- choose between model A and model B
- identify the example that forces the distinction
- catch the author's target of criticism

Weak task shapes:

- discuss the text broadly
- summarize several pages from memory

### `consolidation_sheet` as Model Builder

This sheet should make the learner reconstruct the mechanism with minimal
working-memory load.

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

## Pilot Evaluation

This mode should be tested on real learners rather than accepted as theory.

Useful comparisons:

- problem-driven scaffold vs current scaffold
- search-heavy vs model-heavy vs challenge-heavy tasks
- short podcast plus scaffold vs scaffold alone

Useful observations:

- which version the learner starts fastest
- which version keeps attention longest
- which version produces the strongest sense of progress
- which version leaves the best recall after a short delay

## Relation To Other Docs

- repo-level design principles: [learning-material-design.md](/Users/oskar/repo/podcasts/docs/learning-material-design.md)
- output-layer boundary and evaluation map: [learning-material-outputs.md](/Users/oskar/repo/podcasts/shows/personlighedspsykologi-en/docs/learning-material-outputs.md)
- current canonical scaffold contract: [scaffolding-system.md](/Users/oskar/repo/podcasts/shows/personlighedspsykologi-en/docs/scaffolding-system.md)
