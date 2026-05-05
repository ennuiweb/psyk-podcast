# Freudd Learning System Architecture And Maturity

## Scope

This document is the canonical system-wide architecture and maturity assessment
 for the `Freudd Learning System`.

Use it for:

- the current subsystem map
- the relationship between product goal and implementation
- maturity assessment by subsystem
- system-wide strengths, weaknesses, and architectural tradeoffs
- the recommended next maturity steps

This is intentionally broader than:

- `notebooklm-automation.md` for the `Freudd Content Engine`
- `notebooklm-queue-current-state.md` for the `Freudd Generation Queue`
- `freudd-portal.md` and `freudd_portal/README.md` for the `Freudd Portal`

## Product Goal

The system goal is not merely to publish artifacts. The goal is to create the
best possible conditions for strong learning material for a course.

That includes:

- understanding the course material well
- selecting and structuring what matters
- generating useful learning artifacts
- publishing them reliably
- presenting them in a way that supports progression, motivation, and reuse

This goal matters because architectural quality should be judged against that
standard, not only against operational uptime.

## Subsystem Map

The current canonical subsystem map is:

1. `Freudd Learning System`
2. `Freudd Portal`
3. `Freudd Content Engine`
4. `Freudd Generation Queue`
5. `Distribution Layer`
6. `Freudd Podcast Network`

Inside `Freudd Content Engine`:

1. `Source Intelligence Layer`
2. `Course Context Layer`
3. `Prompt Assembly Layer`

In practical terms:

- `Freudd Portal` is the learner-facing web application
- `Freudd Content Engine` prepares learning material and generation inputs
- `Freudd Generation Queue` runs and publishes queue-owned generation work
- `Distribution Layer` turns validated outputs into RSS, manifests, Spotify
  mappings, and downstream deploy inputs
- `Freudd Podcast Network` is the public podcast surface consumed outside the
  portal

## Intelligence Design Principle

The `Freudd Content Engine` should be designed as a decomposed alternative to a
hypothetical model that could ingest and reason over an entire course in one
pass.

That implies three necessary information flows:

- bottom-up: source files -> lecture artifacts -> course artifacts
- top-down: course arc / theory structure -> local importance and selection
- sideways: lecture-to-lecture, concept-to-concept, and theory-to-theory
  relations

All three are necessary:

- without bottom-up flow, the system loses grounding
- without top-down flow, the system loses prioritization
- without sideways flow, the system loses comparison and synthesis

This should not be implemented as unrestricted recursive coupling between
layers. The mature shape is explicit artifacts with inspectable contracts and
mostly one-way derivation, plus deliberate cross-links where comparison is part
of the artifact itself.

## Preprocessing Versus Prompt Tuning

The most important distinction for the next phase is:

- preprocessing builds the course substrate
- prompt tuning decides how a specific generator uses that substrate

The core task is preprocessing. Prompt work matters, especially for NotebookLM
podcasts, but it is downstream of the substrate. The `Freudd Content Engine`
should therefore avoid treating prompt edits as the main way to improve course
understanding.

Near the exam deadline, the finished system should be judged by whether it
provides a better substrate than the simple baseline of "upload the source files
and use a simple prompt". If the richer system makes outputs worse, too
abstract, or less grounded, it has failed even if the architecture looks more
impressive.

The practical rule is:

- Python should orchestrate, cache, validate, and assemble
- Gemini should do most semantic interpretation
- prompts should receive compact selected substrate, not the full internal
  artifact stack

## Recursive Gemini Preprocessing Strategy

The intended direction is now a Gemini-heavy recursive preprocessing approach.
The goal is not to replace every script with model output. The goal is to use
scripts as stable rails around model-generated semantic passes.

The implemented recursive preprocessing wrapper supports these passes:

1. Source pass
2. Lecture pass
3. Course pass
4. Downward revision pass
5. Output substrate pass

The source pass sends individual readings and slide decks to Gemini and writes
structured source cards. These cards should capture claims, terms, distinctions,
theory roles, misunderstandings, source role, and provenance.

The lecture pass combines source cards for each lecture, with raw files included
where needed, and writes lecture substrates. These should identify the lecture
question, source roles, reading/slide relations, central tensions, and the few
ideas that must carry forward.

The course pass reads all lecture substrates and writes course-level artifacts:
course arc, glossary, theory map, distinction map, and sideways relations.

The downward revision pass revisits each lecture with the course-level map in
view. This is where top-down information flow becomes explicit: the system asks
what matters locally once the whole course movement is visible.

The output substrate pass writes compact artifacts for generation. For this
project phase, podcast substrates are in scope; broader setup for every output
family is not.

This is recursive in the useful sense: each level compresses and interprets the
previous one, then course-level structure flows back down to revise lecture
substrates. It should not become an opaque loop where model prose repeatedly
rewrites itself without provenance.

Guardrails:

- every LLM artifact must be schema-validated
- every artifact must carry input source ids and dependency hashes
- model claims should be marked as source-grounded, slide-framed, or synthetic
  course interpretation where possible
- missing sources must remain explicit, not filled in by inference
- final podcast prompts should use only the selected substrate slice needed for
  that output

Implementation status as of 2026-05-05:

- the shared Gemini JSON/upload client, course-specific builders, recursive
  wrapper, validator/index, and optional podcast-substrate prompt integration
  are implemented
- source-card generation uploads actual PDF/source files to Gemini; the
  lecture-substrate pass also uploads the lecture's raw source PDFs by default
- Gemini calls use explicit high thinking, JSON MIME output, and
  stage-specific structured-output schemas while preserving Gemini 3's default
  temperature behavior
- the first live `W05L1,W06L1` recursive batch has generated and validated
  source cards, lecture substrates, a partial course synthesis, revised lecture
  substrates, and podcast substrates
- `shows/personlighedspsykologi-en/source_intelligence/index.json` is the
  coverage/staleness status file for those LLM-derived artifacts

## Overall Verdict

The system is real, useful, and operationally advanced. It is not a prototype.

It is already mature enough to:

- generate and publish course podcast material
- maintain a learner-facing portal on top of the generated assets
- operate queue-owned publication for live shows
- support a mixed publication environment during migration

It is not yet mature enough to claim that it systematically creates the best
possible learning conditions across the full course-material lifecycle.

The core reason is simple:

- operational maturity is high
- pedagogical intelligence maturity is medium to low

So the system is currently stronger at moving artifacts through a reliable
pipeline than at deeply modeling the course before generation.

## Maturity Matrix

Scores use a `1-5` scale:

- `1` = immature / brittle
- `2` = early but usable
- `3` = solid and working
- `4` = mature
- `5` = highly mature / hard to improve materially

| Subsystem | Purpose fit | Operational maturity | Architectural clarity | Current score | Notes |
|---|---:|---:|---:|---:|---|
| `Freudd Portal` | 4 | 4 | 3 | 3.8 | Product-rich and strongly aligned to learning flow, but too much logic is concentrated in very large files. |
| `Freudd Content Engine` | 3 | 3 | 3 | 3.2 | Good prompt/context infrastructure, and the upstream engine now has file-, lecture-, and course-level semantic artifacts, but weighting is not yet fully driving downstream selection and hosted rebuildability still lags. |
| `Source Intelligence Layer` | 3 | 3 | 3 | 3.3 | It now has deterministic source catalog, lecture bundles, glossary, theory map, weighting, concept graph, and a validated first recursive Gemini batch for `W05L1,W06L1`; it still needs podcast-output quality evaluation and broader lecture coverage before it can be called mature. |
| `Course Context Layer` | 4 | 4 | 4 | 4.0 | Deterministic, reusable, and conceptually clean. One of the better-designed parts of the system. |
| `Prompt Assembly Layer` | 4 | 4 | 3 | 3.7 | Much better than ad hoc prompt strings, but growing dense and still dependent on relatively weak upstream semantic artifacts. |
| `Freudd Generation Queue` | 5 | 4 | 4 | 4.3 | The most mature backend subsystem. It owns a serious end-to-end state machine and real publication logic. |
| `Distribution Layer` | 4 | 4 | 3 | 3.8 | Works well and is already integrated with queue-owned publication, but still carries migration-era complexity. |
| `Freudd Podcast Network` | 3 | 4 | 4 | 3.7 | Reliable publication surface, but still somewhat downstream of the engine rather than actively optimized for learning outcomes. |
| `Freudd Learning System` overall | 4 | 4 | 3 | 3.7 | Strong system with real leverage, but not yet an optimal or fully consolidated learning-material machine. |

## What Is Already Mature

### 1. Queue and publication ownership

The `Freudd Generation Queue` is the clearest example of high maturity.

What is strong:

- explicit job/state ownership
- durable queue storage outside git
- show-scoped locking
- real generation/download execution
- publish-bundle validation
- object upload
- repo metadata rebuild
- repo commit/push
- downstream synchronization

This is not a toy queue. It is already a serious workflow runtime.

### 2. Deterministic course framing

The `Course Context Layer` is architecturally good.

It is strong because it:

- is deterministic rather than model-dependent
- is reusable across output types
- clearly separates course framing from source preprocessing
- improves prompts without relying on vague style instructions
- can now consume compact semantic guidance from the `Source Intelligence Layer`
  without collapsing that layer back into opaque prompt prose

This is exactly the kind of layer that is hard to replace with “just better
prompting”.

### 3. Portal product fit

The `Freudd Portal` is genuinely aligned with learning rather than being a thin
asset browser.

It already supports:

- lecture-first navigation
- reading and podcast tracking
- summaries
- quizzes and progress
- motivation and scoreboard mechanics
- subject-level coherence

That makes it a real learning product layer, not just a presentation shell.

## What Is Not Mature Enough

### 1. The upstream intelligence layer is still too shallow

This is the biggest gap in the whole system relative to its goal.

Right now the `Source Intelligence Layer` mainly consists of:

- manual summaries
- optional per-source or weekly sidecars
- a deterministic `source_catalog.json`
- a course-specific interpretation policy file
- deterministic `lecture_bundles`
- a committed course semantic seed
- `course_glossary.json`
- `course_theory_map.json`
- a first hash-based staleness index
- a first `course_concept_graph.json`

What is still missing:

- explicit distinction map
- richer cross-lecture concept graph depth
- prompt-integrated source weighting
- automatic stale invalidation enforcement
- hosted rebuildability for the new local-only artifacts

Without those, the engine still lacks a rich intermediate understanding of the
course.

One useful refinement is now explicit: the preprocessing policy for a live
course does not need to be fully generic. For `personlighedspsykologi`, the
engine should be allowed to encode course-local assumptions such as:

- `grundbog` chapters functioning mainly as conceptual framing
- lecture slides functioning mainly as framing/emphasis evidence
- seminar slides functioning mainly as application/discussion evidence

That kind of course tuning is acceptable when it stays explicit, inspectable,
and versioned as data rather than being hidden inside prompt prose.

### 2. Reproducibility is incomplete

Important preprocessing still depends on local-only source access.

The clearest example is `source_catalog.json`:

- it is a useful artifact
- but it cannot yet be rebuilt in GitHub Actions because the raw source files
  are not available there

That means one of the most important intelligence artifacts is not yet fully
owned by the hosted system.

### 3. Mixed migration ownership still leaks complexity

The live system is still in a mixed state:

- some active shows are queue-owned
- some are still legacy-workflow-owned

This is operationally sensible during migration, but it is not the final clean
architecture.

It creates:

- duplicated conceptual paths
- more policy branching
- more publication-state reasoning overhead
- longer-lived compatibility code

## Where The System Is Over-Complex

The system is not over-complex everywhere. It is over-complex in specific ways.

### 1. Transitional publication complexity

The biggest architectural overhead is migration-era coexistence:

- legacy workflow publication
- queue-owned publication
- mixed show ownership
- R2-backed but still differently owned feeds

This complexity is justified for transition, but it should not become the final
steady-state design.

### 2. Large concentrated modules

Some files are now doing too much:

- `freudd_portal/quizzes/views.py`
- `freudd_portal/quizzes/content_services.py`
- `notebooklm_queue/publish.py`
- `notebooklm_queue/prompting.py`
- `notebooklm_queue/metadata.py`

This does not mean they are broken. It means future change-cost and reasoning
cost will keep rising if the system continues to grow inside these files.

## Where The System Is Too Simple

### 1. Semantic course modeling

The biggest underbuilt area is course-level semantic structure.

The system still lacks enough first-class artifacts for:

- deeper recurring distinctions across lectures
- richer cross-lecture concept graph structure
- stronger source weighting and selection logic
- lecture-level slide-informed synthesis beyond current bundle summaries

That is exactly the kind of intelligence required to claim the engine creates
the best possible conditions for learning material.

### 2. Source weighting

The engine still does not seriously model:

- text length
- centrality
- source role
- foundational vs supporting status
- lecture emphasis vs source emphasis

Without that, prompt context remains flatter than it should be.

### 3. Invalidating stale understanding

The system now has a first hash-based stale/index model for course semantic
artifacts, but it does not yet enforce automatic rebuilds or publication blocks
when those dependencies drift.

That means semantic artifacts are now traceable, but not yet self-policing.

## Architectural Soundness

The architecture is sound overall.

Why it is sound:

- major subsystem boundaries mostly make sense
- the queue/store model is appropriate for the scale and failure model
- the portal consumes generated artifacts via clear contracts
- the content-engine layers are conceptually separable
- the system is well documented compared with many repos of similar scope
- the test surface is substantial

Why it is not yet optimal:

- too much transitional duality remains
- too much semantic understanding still lives in prose summaries rather than
  structured artifacts
- some hosted ownership boundaries are still incomplete
- a few core modules are now too large

So the architecture is not “wrong”. It is better described as:

- structurally sound
- operationally strong
- intellectually underpowered upstream
- still partially transitional

## Does It Achieve Its Goal?

### Yes, for the practical short-term goal

If the goal is:

- publish useful course material
- support quiz-driven and lecture-first learning
- run real end-to-end automation
- keep public and portal distribution in sync

then yes, the system already succeeds.

### Not fully, for the strongest form of the goal

If the goal is:

- maximize learning-material quality before generation
- build a deeply course-aware content engine
- scale that quality bar across subjects without heavy manual interpretation

then not yet.

The missing piece is not primarily queue reliability or UI. It is the depth of
the `Freudd Content Engine`, especially upstream of prompt assembly.

## Recommended Next Moves

These are the highest-leverage maturity moves from here.

### Priority 1: Operationalize the `Source Intelligence Layer`

The deterministic baseline artifacts now exist. The next high-leverage work is
not more prompt tuning and not primarily more hand-coded semantic inference. It
is a Gemini-driven recursive preprocessing layer, with scripts providing
orchestration and validation.

The immediate target is:

1. source cards for all available readings and slide decks
2. lecture substrates built from source cards
3. course-level synthesis built from lecture substrates
4. downward revision of each lecture substrate using the course synthesis
5. compact podcast substrates for generation

This is still the single best way to improve learning-material quality.

### Priority 2: Reduce migration-era duality

Move more active publication paths toward a cleaner single ownership model and
retire remaining transitional logic where possible.

### Priority 3: Split the biggest modules

The highest-risk long-term maintenance hotspots are:

- portal views/content services
- queue publish/metadata/prompt modules

Refactoring them is not urgent if behavior is stable, but it should happen
before the next large capability wave.

### Priority 4: Make preprocessing more reproducible

Important engine artifacts should become rebuildable in hosted infrastructure,
not only from the local workstation.

### Priority 5: Add explicit quality evaluation loops

The system currently validates operational correctness better than pedagogical
quality. It should eventually have:

- comparison runs
- quality review bundles
- lecture-level acceptance criteria for generated material

## Roadmap Pain Register

The roadmap is driven by a small set of concrete system pains, not by a vague
wish to “improve architecture”.

### Pain 1: The `Freudd Content Engine` is still too shallow pedagogically

The system can generate useful material, but it still lacks enough structured
semantic preprocessing upstream to claim it creates the best possible
conditions for learning material.

Concretely:

- the full-course LLM preprocessing code path exists, and the first live
  `W05L1,W06L1` batch has generated source cards, lecture substrates, partial
  course synthesis, downward revisions, and podcast substrates
- source-card, lecture-substrate, course-synthesis, downward-revision, and
  podcast-substrate schemas/builders are implemented; broad coverage is still
  pending until the remaining lectures are run
- the next quality risk is no longer "can we build it?" but "are the generated
  artifacts better than the simple upload-and-prompt baseline?"
  once the whole course arc is visible
- the compact podcast substrate layer exists and is wired for prompt
  injection, but still needs podcast-output quality evaluation before scaling
- no automatic stale invalidation enforcement for derived understanding
- sideways comparison across lectures and theories is still more scripted and
  seeded than source-derived

### Pain 2: The live architecture is still partially transitional

The system still carries migration-era mixed ownership:

- queue-owned shows
- legacy-workflow-owned shows

This is pragmatic, but it means some complexity is transitional rather than
intrinsic.

### Pain 3: Important modules are becoming too concentrated

The current largest maintenance hotspots are:

- `freudd_portal/quizzes/views.py`
- `freudd_portal/quizzes/content_services.py`
- `notebooklm_queue/publish.py`
- `notebooklm_queue/prompting.py`
- `notebooklm_queue/metadata.py`

The issue is not immediate correctness. It is rising future change-cost and
reasoning-cost.

### Pain 4: The `Source Intelligence Layer` is still not complete enough

The current baseline is now materially better than a file inventory. It has:

- `source_catalog.json`
- `lecture_bundle.json`
- `course_glossary.json`
- `course_theory_map.json`
- a first hash-based stale/invalidation index

The remaining missing runtime state is:

- real Gemini-generated source cards for all available sources
- real Gemini-generated lecture substrates
- real Gemini-generated course synthesis and downward revision
- real compact podcast substrates for generation
- quality evaluation of whether these artifacts improve NotebookLM podcasts

### Pain 5: Reproducibility is still incomplete

Some important intelligence artifacts still depend on local-only source access.
That weakens hosted rebuildability and makes the content engine less first-class
in automated infrastructure than it should be.

### Pain 6: Manual summaries are both a strength and a scaling constraint

Manual summaries improve quality, but they also make the system harder to scale
cleanly across more courses unless richer deterministic and structured semantic
layers sit beneath prompt assembly.

## Execution Roadmap

This is the recommended execution order if the goal is to mature the system
without destabilizing what already works.

### Phase 1: Strengthen the `Source Intelligence Layer`

Goal:

- make the upstream course-understanding layer materially richer through
  recursive Gemini preprocessing before doing more prompt work

Current baseline delivered:

1. `source_catalog.json`
2. lecture-bundle layer
3. course glossary / theory map
4. a first stale/invalidation index for derived artifacts
5. a canonical one-command local rebuild path for the full
   `Source Intelligence Layer`

Remaining gap before this phase is truly complete:

- source cards for all available readings and slide decks
- lecture substrates that combine source cards with slide framing
- course synthesis derived from lecture substrates
- downward revision of each lecture substrate from the whole-course view
- podcast substrates that are compact enough for NotebookLM

### Phase 2: Produce Output Substrates

Goal:

- convert the recursive preprocessing results into compact generation inputs

Recommended outputs:

1. podcast substrate per lecture
2. source-aware podcast substrate per reading/slide where needed
3. compact weekly substrate for `Alle kilder (undtagen slides)` audio
4. validation that each substrate is grounded, concise, and usable
5. prompt integration that uses the substrate without expanding the final prompt

Current default decisions for this phase:

- keep the backend richer than the final prompt surface
- treat NotebookLM podcast prompts as a fragile interface that should receive
  compact, high-value guidance rather than ontology dumps
- let reading prompts prioritize `reading_grounded` and `textbook_framing`
  evidence
- let lecture-slide prompts prioritize `lecture_framed` evidence while still
  anchoring substantive claims in readings
- let seminar-slide prompts prioritize `seminar_applied` evidence for likely
  misunderstandings, applications, and clarifications
- keep the final prompt surface conservative: usually 1-2 ranked sources, 1-2
  terms, 1 theory frame, and 1 cross-lecture tension at most
- make `short` prompts stricter still: local arc, target-centered context, and
  fewer duplicated instructions

Exit condition:

- podcasts can be generated from a stable substrate that is visibly better than
  the simple baseline of raw source files plus a simple prompt
- outputs improve because preprocessing gets better, not because prompts become
  much longer

### Testing Readiness Implementation Status

For `personlighedspsykologi`, the code needed before podcast testing now
exists:

1. shared Gemini preprocessing client
2. source-card builder
3. lecture-substrate builder
4. course-synthesis builder
5. downward-revision builder
6. podcast-substrate builder
7. recursive rebuild wrapper
8. substrate validator
9. narrow prompt integration behind a config flag

The shared client lives in `notebooklm_queue/` and owns Gemini upload,
generation, JSON parsing, retries, and metadata capture. Course-specific scripts
live under `scripts/` and write artifacts under:

```text
shows/personlighedspsykologi-en/source_intelligence/
```

The first test set should be:

- `W05L1`
- `W06L1`
- one early lecture
- one late lecture

The system is ready for podcast quality testing when those lectures have source
cards, lecture substrates, revised lecture substrates, podcast substrates,
schema validation, and dry-run prompt output showing compact substrate
injection. `W03L2` remains allowed as partial because of the known missing
source.

The remaining blocker is no longer basic model/key access or first artifact
generation: the local secret-store key passes `gemini-3.1-pro-preview`
preflight, and the first `W05L1,W06L1` recursive artifacts validate cleanly.
The remaining gate is podcast-output quality testing, cost monitoring, and
comparison against the simple baseline.

### Phase 3: Add explicit quality loops

Goal:

- make learning-material quality review a first-class part of the system

Recommended outputs:

1. comparison run bundles
2. artifact review manifests
3. lecture-level acceptance criteria
4. quality scoring or rubric-backed evaluation runs

Exit condition:

- the system can compare generations and judge quality more explicitly than by
  manual listening alone

### Phase 4: Reduce architectural drag

Goal:

- simplify the system where complexity is transitional rather than essential

## Decision Register

These are the active implementation decisions that do not currently need user
input and should be treated as default policy unless real evidence suggests
otherwise.

### Decided defaults

- The `Source Intelligence Layer` may be fairly rich; the NotebookLM prompt
  surface should stay comparatively thin.
- `personlighedspsykologi` is allowed to use explicit course-local
  interpretation policy when it is versioned as data and documented.
- The system should support bottom-up, top-down, and sideways flow, but mostly
  through inspectable artifacts rather than recursive prompt logic.
- New semantic artifacts should first improve selection and coherence, not
  automatically become visible prompt content.

### Deferred decisions

These are the likely next user-facing decision points, but none blocks the
current roadmap work yet.

- whether course-level semantic artifacts should stay mostly English, become
  Danish-first, or stay mixed
- how much additional LLM enrichment to allow above the current deterministic
  and manual-summary baseline
- when stale artifacts should merely warn versus hard-block generation
- when hosted rebuildability should become mandatory for source-intelligence
  artifacts

Recommended outputs:

1. retire more migration-era dual paths
2. consolidate publication ownership
3. split the largest queue and portal hotspots
4. improve hosted reproducibility for important engine artifacts

Exit condition:

- the steady-state architecture is easier to reason about than the migration
  architecture

## Final Assessment

The `Freudd Learning System` is already a strong and unusually capable system.

Its biggest success is that it already behaves like a real integrated product
and not a pile of scripts.

Its biggest maturity gap is that the `Freudd Content Engine` still does not
understand the course as richly as the rest of the system deserves.

So the clearest maturity statement is:

- the system is operationally mature enough to trust
- it is architecturally sound enough to keep building on
- it is not yet pedagogically mature enough to stop investing in upstream
  course intelligence

That makes the next frontier clear: not “more automation everywhere”, but
deeper course understanding inside the engine.
