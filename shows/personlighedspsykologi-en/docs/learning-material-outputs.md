# Learning Material Outputs

This document defines the learner-facing output layer for
`shows/personlighedspsykologi-en`.

Use it for:

- the boundary between learner-facing outputs and upstream engine artifacts
- the canonical paths for podcasts, printouts, quizzes, and slides
- the quality contract for evaluating those outputs
- the current evaluation workflows and gaps

## Scope

This layer currently includes four output families:

- podcasts
- printouts / reading scaffolds
- quizzes
- slides

This layer does not include:

- `source_catalog.json`
- `lecture_bundles/`
- `source_intelligence/`
- `course_glossary.json`
- `course_theory_map.json`
- `course_concept_graph.json`
- queue job state, publish manifests, or RSS/manifest plumbing internals except
  where they are the public delivery surface for learning materials

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

### Quizzes

Canonical published quiz surfaces:

- `shows/personlighedspsykologi-en/quiz_links.json`
- `shows/personlighedspsykologi-en/content_manifest.json`
- public quiz paths under `/q/<quiz_id>.html`

Canonical local generation root when quiz JSON artifacts are present:

- `notebooklm-podcast-auto/personlighedspsykologi/output/<lecture>/*.json`

Quiz entries should preserve two separate hash notions when available:

- `config_hash` from the generated quiz filename's `{type=quiz ... hash=...}`
  tag
- `source_config_hash` from the source audio/podcast filename in
  `quiz_links.json` when the quiz itself is only represented by a public link

### Slides

Canonical published slide surfaces:

- `shows/personlighedspsykologi-en/slides_catalog.json`
- `shows/personlighedspsykologi-en/content_manifest.json`
- public slide paths under `/slides/personlighedspsykologi/<lecture>/<subcategory>/...`

Slides are manually mapped and synced learning materials. They are tracked as
learner-facing outputs, but the registry should not treat the slide catalog as
an automatically generated Course Understanding artifact.

### Printouts

Canonical printout artifact root:

- `notebooklm-podcast-auto/personlighedspsykologi/output/<lecture>/printouts/<source_id>/reading-printouts.json`

Derived render targets:

- `01-*.md`
- `01-*.pdf`
- `02-*.md`
- `02-*.pdf`
- `03-*.md`
- `03-*.pdf`

Canonical printout contract:

- `shows/personlighedspsykologi-en/docs/printout-system.md`
- alternative test mode: `shows/personlighedspsykologi-en/docs/problem-driven-printouts.md`
- evaluation workspace: `notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/`

Important current-state note:

- the scaffold contract now targets schema v3
- legacy schema v1/v2 scaffold artifacts may still exist in local output trees
- quality review should either evaluate an artifact against its declared schema
  version or regenerate a fresh v3 artifact before comparing it to the current
  contract

### Regeneration Ledger

Canonical ledger:

- `shows/personlighedspsykologi-en/learning_material_regeneration_registry.json`

Canonical sync command:

```bash
./.venv/bin/python scripts/sync_personlighedspsykologi_learning_material_registry.py
```

Attach human setup versions when a prompt/setup iteration should be tracked by
name, not only by hashes:

```bash
./.venv/bin/python scripts/sync_personlighedspsykologi_learning_material_registry.py \
  --lecture-key W10L2 \
  --podcast-setup-version personlighedspsykologi-podcast-v1 \
  --printout-setup-version personlighedspsykologi-reading-printouts-v3
```

The canonical default labels live in:

- `shows/personlighedspsykologi-en/prompt_versions.json`

For queue-owned runs, these environment variables remain available as explicit
overrides on the queue process:

- `PERSONLIGHEDSPSYKOLOGI_PODCAST_SETUP_VERSION`
- `PERSONLIGHEDSPSYKOLOGI_PRINTOUT_SETUP_VERSION`
- `PERSONLIGHEDSPSYKOLOGI_SETUP_VERSION` as a shared default for both families

If they are unset, queue-owned runs and manual syncs fall back to the checked-in
labels in `prompt_versions.json`.

When `--lecture-key` is present, setup versions are attached only to matching
podcast and printout entries. Without `--lecture-key`, the supplied version is
treated as a ledger-wide label for all discovered materials in that family.
When `--lecture-key` is present and no manual `podcast_setup_version` is
supplied, the podcast ledger now derives an automatic
`personlighedspsykologi-podcast-<hash>` label from the active podcast prompt
system and stores it both as `prompt_system_label` and as the podcast
`setup_version`. This keeps unattended queue runs queryable by prompt-system
label without requiring operators to remember an env var first.

The ledger records learner-facing outputs, not upstream engine internals. It
tracks podcast, printout, quiz, and slide materials with their lecture key,
status, generated/published timestamps where available, prompt/generator
metadata, config hashes, request attempts, auth profile, artifact paths, and the
current `source_intelligence/` snapshot hashes.

For podcasts, `episode_inventory.json` and `media_manifest.r2.json` are the
authoritative current-publication surfaces. Local NotebookLM request logs enrich
those podcast entries with prompt hashes, auth profile, and attempt history when
available, but the ledger must not require local request logs to know that an
episode is live. Podcast entries keep `feed_published_at` and
`media_published_at` separate because feed scheduling and object upload time are
different operational facts. Lecture-scoped queue syncs also stamp matching
podcast entries with `prompt_system`, `prompt_system_label`, and
`prompt_system_fingerprint` so future sessions can group podcasts by the prompt
system that produced them even when request logs have already been cleaned up.

For printouts, `config_hash` / `config_fingerprint` are computed from the
printout generator setup: artifact type, schema version, provider, model,
prompt version, and full generation config. The Course Understanding provenance
is tracked separately as `course_understanding_fingerprint` plus the underlying
provenance hashes, so prompt/setup changes and source-understanding changes can
be compared independently.

For podcasts and printouts, `setup_version` is the human-facing setup label
used during prompt iteration. It complements, but does not replace, the
hash/fingerprint fields. Once attached to a material, it is retained by later
syncs until a new setup version is supplied for that same material. For
podcasts, queue-owned lecture runs now fall back to the automatic
`prompt_system_label` when no explicit setup version is provided.

When a material's observed prompt/config identity changes, the previous observed
identity is retained in `revision_history` so prompt iterations do not erase the
last known hash.

Queue-owned publication for `personlighedspsykologi-en` runs the sync after RSS,
inventory, Spotify, and Freudd content-manifest metadata rebuilds. `push-repo`
allowlists the ledger, so a regenerated podcast can update the public feed and
commit the tracking file in the same queue-owned publication pass.

Future Course Understanding or prompt iterations should start by checking this
ledger, then regenerate the relevant materials, then check it again. It is the
canonical answer to which learner-facing materials have actually been
regenerated under the current pipeline.

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

Quiz-specific criteria:

- quizzes should map to the correct source or lecture-level episode
- difficulty variants should be distinguishable and not duplicate each other
- question rationales should correct likely misunderstandings, not only mark
  answers
- the registry should retain the quiz-specific config hash when the generated
  quiz artifact is available

Slide-specific criteria:

- slide decks should be attached to the correct lecture and subcategory
- seminar and exercise slides should not be mistaken for lecture slides
- public slide paths should remain stable enough for Freudd links and study
  workflows
- manually mapped slides should stay clearly separated from generated
  Course Understanding artifacts

## Learner-Fit Note

Some learners benefit much more from outputs that feel like a sequence of
solvable problems than from outputs that mainly ask for passive intake.

For that reason, `personlighedspsykologi` now also documents an explicit
problem-first alternative for printouts:

- `shows/personlighedspsykologi-en/docs/problem-driven-printouts.md`

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

1. review `reading-printouts.json` first
2. verify it matches the intended scaffold schema for that artifact version
3. inspect Markdown/PDF renders only as derived usability checks
4. judge the printout against `printout-system.md`

Current gap:

- podcasts already have run manifests, judge prompts, and summary outputs
- printouts now have a sidecar run workspace for problem-driven candidates
- printouts still do not yet have a full baseline-vs-candidate judge harness

## Practical Rule

When discussing this layer, use `learning material outputs` only for the four
learner-facing families above.

When checking whether a prompt or Course Understanding iteration has reached the
learner-facing layer, use
`shows/personlighedspsykologi-en/learning_material_regeneration_registry.json`
first. Queue state and NotebookLM request logs can explain a run, but the ledger
is the durable checked-in record.

Do not blur:

- preprocessing quality
- prompt assembly quality
- queue/publication correctness
- learner-facing output quality

They are related, but they are not the same review target.
