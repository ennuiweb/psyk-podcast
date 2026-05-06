# Learning Material Outputs

This document defines the learner-facing output layer for
`shows/personlighedspsykologi-en`.

Use it for:

- the boundary between learner-facing outputs and upstream engine artifacts
- the canonical paths for podcasts and printouts
- the quality contract for evaluating those outputs
- the current evaluation workflows and gaps

## Scope

This layer currently includes only two output families:

- podcasts
- printouts / reading scaffolds

This layer does not include:

- `source_catalog.json`
- `lecture_bundles/`
- `source_intelligence/`
- `course_glossary.json`
- `course_theory_map.json`
- `course_concept_graph.json`
- queue job state, publish manifests, or RSS/manifest plumbing internals except
  where they are the public delivery surface for podcasts

Those artifacts support the learner-facing layer, but they are not themselves
study materials.

## Current Output Inventory

### Podcasts

Canonical published podcast surfaces:

- `shows/personlighedspsykologi-en/media_manifest.r2.json`
- `shows/personlighedspsykologi-en/episode_inventory.json`
- `shows/personlighedspsykologi-en/feeds/rss.xml`

Canonical generation-side docs:

- `notebooklm-podcast-auto/personlighedspsykologi/docs/plan.md`
- `shows/personlighedspsykologi-en/docs/podcast-flow-artifacts.md`
- `shows/personlighedspsykologi-en/docs/podcast-flow-operations.md`

Canonical local generation root:

- `notebooklm-podcast-auto/personlighedspsykologi/output/<lecture>/`

### Printouts

Canonical printout artifact root:

- `notebooklm-podcast-auto/personlighedspsykologi/output/<lecture>/scaffolding/<source_id>/reading-scaffolds.json`

Derived render targets:

- `01-*.md`
- `01-*.pdf`
- `02-*.md`
- `02-*.pdf`
- `03-*.md`
- `03-*.pdf`

Canonical printout contract:

- `shows/personlighedspsykologi-en/docs/scaffolding-system.md`
- alternative test mode: `shows/personlighedspsykologi-en/docs/problem-driven-scaffolding.md`
- evaluation workspace: `notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/`

Important current-state note:

- the scaffold contract now targets schema v3
- legacy schema v1/v2 scaffold artifacts may still exist in local output trees
- quality review should either evaluate an artifact against its declared schema
  version or regenerate a fresh v3 artifact before comparing it to the current
  contract

## Quality Contract

Shared criteria across both families:

- source fidelity and accurate conceptual distinctions
- immediate problem tension where possible
- visible progress and short closure loops
- useful prioritization rather than generic summary voice
- misunderstanding prevention
- study usefulness for a real university learner
- transfer into course comparison and exam preparation

Podcast-specific criteria:

- spoken explanation should preserve distinctions without flattening them
- weekly episodes should synthesize tensions across readings, not just list them
- short episodes should compress without becoming vague
- the output should be judged for pedagogical usefulness, not entertainment

Printout-specific criteria:

- the canonical review target is the JSON artifact, not only the PDF render
- each sheet should have one clear job and operational instructions
- printouts should preferably expose a solvable mission, not only a summary path
- reading tasks should say what to look for, where to look, and when to stop
- printouts must not collapse into ordinary summaries with blanks inserted
- source touchpoints should make opening the real source feel feasible

## Learner-Fit Note

Some learners benefit much more from outputs that feel like a sequence of
solvable problems than from outputs that mainly ask for passive intake.

For that reason, `personlighedspsykologi` now also documents an explicit
problem-first alternative for printouts:

- `shows/personlighedspsykologi-en/docs/problem-driven-scaffolding.md`

That mode is intended for learners who engage more reliably when the material
gives them:

- a question to answer
- something specific to find
- a decision to make
- a quick sense of progress

## Evaluation Workflows

### Podcasts

Canonical evaluation workspace:

- `notebooklm-podcast-auto/personlighedspsykologi/evaluation/episode_ab_review/`

Current workflow:

1. bootstrap a balanced sample from published baseline episodes
2. transcribe baseline audio
3. generate matched candidate episodes into a run-local output root
4. transcribe candidate audio with the same STT backend
5. judge baseline vs candidate against the real source files with
   `judge_prompt.md`

Canonical artifacts for one run:

- `runs/<run-name>/manifest.json`
- `runs/<run-name>/transcripts/`
- `runs/<run-name>/prompts/`
- `runs/<run-name>/notes/`
- `runs/<run-name>/judgments/`

### Printouts

Current sidecar evaluation workspace:

- `notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/`

Current review baseline:

1. review `reading-scaffolds.json` first
2. verify it matches the intended scaffold schema for that artifact version
3. inspect Markdown/PDF renders only as derived usability checks
4. judge the printout against `scaffolding-system.md`

Current gap:

- podcasts already have run manifests, judge prompts, and summary outputs
- printouts now have a sidecar run workspace for problem-driven candidates
- printouts still do not yet have a full baseline-vs-candidate judge harness

## Practical Rule

When discussing this layer, use `learning material outputs` only for the two
learner-facing families above.

Do not blur:

- preprocessing quality
- prompt assembly quality
- queue/publication correctness
- learner-facing output quality

They are related, but they are not the same review target.
