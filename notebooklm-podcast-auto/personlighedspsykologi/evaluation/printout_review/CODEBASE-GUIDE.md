# Printout Review Codebase Guide
This guide is for coding LLMs working on the `printout_review` candidate lane.
It focuses on the code and docs needed to understand, modify, debug, and extend the experimental printout workflow for `personlighedspsykologi`.
The guide is intentionally dense.
Read it before editing the printout candidate system.

## 1. What this repo fundamentally does
The top-level repo is the `Freudd Learning System` content and delivery codebase.
It is not only a podcast repo.
It owns podcast publication, NotebookLM-driven content generation, semantic preprocessing, and a student-facing portal.
The printout candidate lane is one subsystem inside that larger engine.
Its job is to turn dense course readings into printable study artifacts that improve initiation, comprehension, attention maintenance, recall, and oral-exam transfer.
The printouts are not a replacement for the source text.
They are an output adaptation layer on top of a larger source-understanding pipeline.

## 2. The printout candidate in one sentence
The candidate lane generates fresh-from-source experimental printout bundles from upstream semantic artifacts, normalizes them into a stable schema, renders them as Markdown, and optionally renders them as PDFs for inspection.

## 3. The architectural stack you should hold in your head
Think of the system as layered:
1. Raw course readings live outside the repo in the OneDrive-backed subject root.
2. The recursive source-intelligence pipeline builds semantic artifacts from those readings.
3. The printout review lane selects one reading plus compact lecture/course context.
4. A provider backend generates structured JSON candidate content.
5. The experimental engine normalizes and validates that content.
6. The engine renders Markdown and optionally PDF.
7. A run manifest records every candidate generation attempt.
The printout lane therefore depends on both upstream semantics and local render logic.

## 4. Why this candidate lane exists
The production printout path is older and structurally simpler.
The candidate lane exists so the team can test learner-fit changes without destabilizing the canonical output tree.
This separation is deliberate.
It is not accidental duplication.
The cost is maintenance overhead.
The benefit is that pedagogy and layout can evolve without turning production into a moving target.

## 5. The business goal of the printouts
The system is optimized for difficult academic readings where ADHD-style friction is a real constraint.
The product goal is not “make a summary”.
The product goal is “make it easier to start, stay oriented, solve the main problem of the reading, and remember enough to use it in an oral exam”.
Every implementation choice should be read through that lens.
If a change improves schema purity but makes the worksheets less usable, it is a regression.

## 6. The most important docs before touching code
Read these in this order:
1. `TECHNICAL.md`
2. `docs/notebooklm-automation.md`
3. `shows/personlighedspsykologi-en/docs/printout-system.md`
4. `shows/personlighedspsykologi-en/docs/problem-driven-printouts.md`
5. `notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/README.md`
6. This file
The first two explain the repo and the content engine.
The next two explain the pedagogical intent.
The workspace README explains the operator workflow.
This guide ties those layers back to code.

## 7. The relevant top-level directories
You do not need the entire repo for printout work.
You do need these areas:
- `shows/personlighedspsykologi-en/docs/`
- `notebooklm_queue/`
- `notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/`
- `tests/`
Each of these owns a distinct part of the contract.

## 8. What each relevant branch of the directory tree does
`shows/personlighedspsykologi-en/docs/`
Course-specific design intent and pedagogical rules.
`notebooklm_queue/`
Shared generation and orchestration machinery.
`notebooklm_queue/personlighedspsykologi_recursive.py`
Upstream semantic preprocessing for the course.
`notebooklm_queue/personlighedspsykologi_printouts.py`
Older production printout generator; useful for contrast.
`notebooklm_queue/gemini_preprocessing.py`
Gemini JSON-generation backend.
`notebooklm_queue/openai_preprocessing.py`
OpenAI JSON-generation backend.
`notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/`
Experimental printout review workspace.
`tests/`
The behavior lock that keeps this lane from silently regressing.

## 9. The review workspace layout
Path:
`notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/`
Important files:
- `AGENTS.md`
- `README.md`
- `CODEBASE-GUIDE.md`
- `prompts/problem-driven-v1.md`
- `sample_manifest.template.json`
- `scripts/bootstrap_run.py`
- `scripts/generate_candidates.py`
- `scripts/printout_engine.py`
- `scripts/scaffold_engine.py`
- `runs/`
Everything important for the candidate lane starts here.

## 10. The local AGENTS rule you should remember
The local `AGENTS.md` defines the working rule `JSON -> Markdown -> PDF`.
This matters.
For content-only work, inspect JSON or Markdown first.
Use PDFs only when the change can affect layout, spacing, typography, answer-space sizing, diagram space, page breaks, or final sign-off.
This saves time and avoids overfitting to the PDF surface when the real bug is in the underlying content structure.

## 11. The current printout bundle order
The candidate lane now exports in this order:
1. `00-cover`
2. `01-reading-guide`
3. `02-active-reading`
4. `03-abridged-version`
5. `04-consolidation-sheet`
6. `05-exam-bridge` only when explicitly enabled
This order is reflected in filenames so Finder sort order matches print order when selecting files and using `cmd+p`.
That is a real product constraint.

## 12. The user-facing versus internal output split
User-facing artifacts live directly under:
`review/`
Internal artifacts live under:
`review/.scaffolding/<source_id>/`
The user-facing folder is flat and should contain exported printouts only.
The internal folder contains:
- `reading-scaffolds.json`
- internal rendered Markdown when `--no-pdf` is used
Do not mix these layers.
That separation was added to avoid stale and misleading artifacts.
PDF filenames now carry provider, model, source id, and printout stem so
multiple LLMs can coexist in one flat folder.

## 13. Example output tree
```text
printout_review/
├── review/
│   ├── .scaffolding/
│   │   └── <source_id>/
│   │       ├── reading-scaffolds.json
│   │       └── rendered_markdown/
│   ├── openai-gpt-5_5--<source_id>--00-cover.pdf
│   ├── openai-gpt-5_5--<source_id>--01-reading-guide.pdf
│   ├── openai-gpt-5_5--<source_id>--02-active-reading.pdf
│   ├── openai-gpt-5_5--<source_id>--03-abridged-version.pdf
│   └── openai-gpt-5_5--<source_id>--04-consolidation-sheet.pdf
└── runs/<run-name>/
    ├── manifest.json
    ├── notes/
    └── prompts/
```
This is the disk contract you should preserve unless you are intentionally redesigning output policy.

## 14. The main pedagogical contract
The canonical course-specific design contract lives in:
`shows/personlighedspsykologi-en/docs/printout-system.md`
Treat it as binding.
The key roles are:
- `reading_guide`: appetizer and initiation aid
- `active_reading`: open-book guided solve
- `abridged_reader`: self-contained minimum viable reading path
- `consolidation_sheet`: memory-first recall and repair
- `exam_bridge`: optional oral-exam transfer cues
Every sheet should have one primary job.
That role separation is core to the product.

## 15. Production lane versus candidate lane
Candidate lane:
- path: `.../evaluation/printout_review/`
- engine: `scripts/printout_engine.py`
- schema: current review schema v3
- rule: fresh-from-source candidates only
Production lane:
- center of gravity: `notebooklm_queue/personlighedspsykologi_printouts.py`
- output root: `notebooklm-podcast-auto/personlighedspsykologi/output/...`
- older prompt contract and older artifact structure
Do not casually mix the two.
Use production artifacts as comparison references, never as seed material for candidate generation.

## 16. The broader upstream pipeline the candidate consumes
The candidate lane is downstream of the `Course Understanding Pipeline`.
For `personlighedspsykologi`, the key upstream file is:
`notebooklm_queue/personlighedspsykologi_recursive.py`
That file builds:
- source cards
- lecture substrates
- course synthesis
- revised lecture substrates
- podcast substrates
The candidate lane mainly consumes source cards, revised lecture substrates, and course synthesis.
That means printouts are not pure reading-local summaries.
They depend on lecture-level and course-level framing too.

## 17. Why the upstream recursive file matters even if you only touch printouts
Many “printout bugs” are really upstream-semantic bugs.
Examples:
- weak `quote_targets` in the source card
- wrong complexity score
- stale course synthesis
- revised lecture substrate that over-emphasizes a theme
The printout engine only sees a compact projection of those artifacts.
If the upstream signal is wrong, the printout can be formally valid but pedagogically weak.
When output quality seems mysteriously off, inspect upstream artifacts before blaming the renderer.

## 18. Key upstream constants the review lane imports directly
Source:
`notebooklm_queue/personlighedspsykologi_recursive.py`
Important constants:
```python
SUBJECT_SLUG = "personlighedspsykologi"
DEFAULT_SOURCE_CATALOG = DEFAULT_SHOW_DIR / "source_catalog.json"
DEFAULT_SOURCE_CARD_DIR = DEFAULT_RECURSIVE_DIR / "source_cards"
DEFAULT_REVISED_LECTURE_SUBSTRATE_DIR = DEFAULT_RECURSIVE_DIR / "revised_lecture_substrates"
DEFAULT_COURSE_SYNTHESIS_PATH = DEFAULT_RECURSIVE_DIR / "course_synthesis.json"
```
The candidate lane imports these path defaults rather than redefining them.
If upstream defaults move, the review lane must be updated too.

## 19. The local review run lifecycle
A normal fresh run is:
1. bootstrap a run
2. create a manifest and note stubs
3. select one or more sources
4. generate fresh candidate JSON with a provider
5. normalize and validate the result
6. write internal JSON
7. render Markdown and optionally PDF
8. update the manifest per source
Everything downstream depends on this sequence.
If you shortcut it, you often end up with stale or invalid candidate state.

## 20. The bootstrap entrypoint
Source:
`notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/scripts/bootstrap_run.py`
Purpose:
Create a review run skeleton without invoking a model.
What it writes:
- `manifest.json`
- `notes/<source_id>.md`
What it resolves:
- selected sources
- baseline output dir
- candidate output dir
- internal candidate JSON path
This is where a review run becomes a first-class unit on disk.

## 21. What the manifest actually means
The run manifest is the canonical state record for a review run.
Each entry includes:
- source identity
- baseline JSON path
- baseline output dir
- candidate output dir
- candidate JSON path
- prompt capture paths
- current candidate status
- review note path
The manifest is not just metadata.
It is the status ledger the CLI updates while work is happening.

## 22. Candidate statuses you should know
Statuses seen in practice:
- `pending`
- `written`
- `rerendered_existing`
- `skipped_existing`
- `error`
The `summary` block in the manifest is refreshed during the batch.
This was added because earlier batches were too silent and left stale old statuses that looked current.
If a batch feels hung, check the manifest and stdout first.

## 23. The main CLI entrypoint
Source:
`notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/scripts/generate_candidates.py`
This file owns:
- argument parsing
- provider selection
- preflight logic
- per-source orchestration
- prompt capture
- manifest progress updates
- final summary output
If you need to understand how operators actually run this lane, read this file first.

## 24. The most important CLI flags
High-value flags:
- `--manifest`
- `--source-id`
- `--provider`
- `--model`
- `--force`
- `--rerender-existing`
- `--no-pdf`
- `--include-exam-bridge`
- `--fail-fast`
- `--preflight-only`
These flags are enough to explain most real operator workflows.
If a future change adds a new mode, it should probably surface here.

## 25. Provider selection and preflight
`generate_candidates.py` supports `gemini` and `openai`.
It determines the provider-specific default model, checks whether the required API key exists, and runs provider preflight unless explicitly skipped.
It now also runs PDF render-toolchain preflight early when PDFs are enabled.
That means missing `pandoc`, a LaTeX engine, or `pdfinfo` causes a fast operator failure before provider cost is incurred.
This was a deliberate hardening fix.
Keep that fail-early behavior.

## 26. Non-idiomatic but intentional CLI behavior
The CLI does a guarded bootstrap import.
If imports fail, it records the failure and exits later with a better message that includes the preferred interpreter path.
It also manipulates `sys.path` manually because these scripts are meant to be executed directly from the repo.
This is non-idiomatic Python, but it is intentional.
Do not “clean it up” casually unless you also change the operator execution model.

## 27. Provider abstraction at the CLI boundary
`generate_candidates.py` hides provider-specific generation behind `_make_provider_json_generator(...)`.
The experimental engine receives a `json_generator` callback and does not need to know whether it came from Gemini or OpenAI.
That is good separation.
The engine stays provider-agnostic where it matters.
Provider-specific instability remains in the backend files.
This is the right current split.

## 28. Gemini backend purpose
Source:
`notebooklm_queue/gemini_preprocessing.py`
This file provides structured JSON generation helpers for Gemini.
Its core jobs are:
- resolve API key
- create client
- upload and stage source files
- poll file readiness
- send structured requests
- parse JSON responses
- retry rate-limit-like failures
- clean up uploaded files
If Gemini behavior changes, this is where you start.

## 29. Gemini backend constants worth knowing
```python
DEFAULT_GEMINI_PREPROCESSING_MODEL = "gemini-3.1-pro-preview"
DEFAULT_MAX_INLINE_SOURCE_CHARS = 16000
DEFAULT_MAX_OUTPUT_TOKENS = 8192
DEFAULT_GEMINI_THINKING_LEVEL = "high"
```
Gemini here is comparatively upload-oriented.
That suits multi-file source handling better than the current OpenAI approach.
The tradeoff is more lifecycle management around uploads and polling.

## 30. OpenAI backend purpose
Source:
`notebooklm_queue/openai_preprocessing.py`
This file provides structured JSON generation helpers for OpenAI.
Its core jobs are:
- resolve API key from env, local secret store, or Bitwarden
- create OpenAI client
- read source files locally
- extract PDF text
- OCR scanned PDFs when needed
- inline source text into the user prompt
- call the Responses API
- parse JSON responses
- retry transport or rate-limit failures
It is more local-text oriented than the Gemini backend.

## 31. OpenAI backend constants worth knowing
```python
DEFAULT_OPENAI_PREPROCESSING_MODEL = "gpt-5.5"
DEFAULT_OPENAI_REQUEST_TIMEOUT_SECONDS = 180
DEFAULT_OPENAI_OCR_TIMEOUT_SECONDS = 600
OPENAI_TRANSIENT_RETRY_DELAYS_SECONDS = (5, 15, 30)
```
OpenAI transport hardening was added because transient connection resets happened in real runs.
The backend now retries likely transient failures with logged backoff.
That made provider comparison much more stable.

## 32. A key OpenAI caveat
OpenAI source ingestion has a per-file truncation cap.
It does not yet have a strict global prompt budget across all source files.
This is a likely future scaling bug.
It matters most for multi-file readings or if the lane expands to more source-heavy subjects.
If you extend OpenAI use materially, add a global per-request source budget and log truncation decisions in metadata.

## 33. The prompt overlay
Source:
`notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/prompts/problem-driven-v1.md`
This overlay changes the pedagogical feel without redefining the schema.
Its themes are:
- problem-first framing
- short, appetizing reading-guide paragraphs
- concrete hooks early
- self-contained abridged reader
- fewer, larger active-reading solve steps
- recall after solve
- optional exam bridge
The overlay is not the place to alter file ownership or render policy.

## 34. The engine file is the center of gravity
Source:
`notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/scripts/printout_engine.py`
This file owns too many responsibilities.
It is the main architectural weakness of the lane.
Current responsibilities include:
- path policy
- source selection
- context compaction
- length budgeting
- prompt assembly
- schema helpers
- normalization
- validation
- provider fallback invocation
- artifact persistence
- Markdown rendering
- PDF rendering
- stale-file cleanup
You will touch this file for most non-trivial printout changes.

## 35. Why the monolithic engine matters
The monolith is not just ugly.
It increases regression risk because small changes can collide with unrelated concerns.
A spacing tweak can break output cleanup.
A path-policy change can break rerendering.
A validation change can silently degrade layout because fewer items make it to render.
If you plan a major future refactor, split at least these concerns:
- normalization
- derivation
- validation
- artifact I/O
- Markdown rendering
- PDF rendering
Do not do that as part of a small hotfix.

## 36. Important engine constants
Read these first when orienting yourself:
- `PROMPT_VERSION`
- `SCHEMA_VERSION`
- `INTERNAL_ARTIFACT_DIRNAME`
- `V3_FIXED_TITLES`
- `V3_RENDER_STEMS`
- `PDF_RENDER_ENGINES`
- the spacing token map near the top of the file
These constants govern file naming, compatibility, render order, hidden artifact placement, and PDF engine selection.
Many downstream assumptions depend on them.

## 37. Current canonical stems
Source:
`.../scripts/printout_engine.py`
```python
V3_RENDER_STEMS = {
    "cover": "00-cover",
    "reading_guide": "01-reading-guide",
    "active_reading": "02-active-reading",
    "abridged_reader": "03-abridged-version",
    "consolidation_sheet": "04-consolidation-sheet",
    "exam_bridge": "05-exam-bridge",
}
```
Changing these affects output ordering, stale-file cleanup, tests, and operator expectations.

## 38. Source selection in the engine
Function:
`select_sources(...)`
This function:
- reads the source catalog
- filters by lecture keys
- filters by explicit source IDs
- optionally filters by source family
- ignores sources that do not exist locally
- sorts stably by lecture, sequence index, and source ID
Deterministic ordering matters for reproducible manifests and stable batch behavior.

## 39. Context compaction
Key helpers:
- `_compact_source_card(...)`
- `_compact_lecture_context(...)`
- `_compact_course_context(...)`
These functions compress upstream artifacts into prompt-sized context.
They are an important hidden layer.
If prompts seem semantically noisy or undergrounded, inspect compaction before blaming the provider.
This is also where upstream schema drift often first shows up in practice.

## 40. Dynamic length budgeting
Function:
`build_printout_length_budget(...)`
The candidate lane does not use a flat worksheet size.
The budget uses:
- length-band signals
- source page count
- source-card complexity
It then sets ranges for:
- teaser paragraphs
- opening passages
- subproblems
- abridged sections
- active solve steps
- fill-in sentences
- diagram tasks
- exam bridge items
This gives the system size sensitivity without changing the overall bundle shape.

## 41. Why count budget is not the same as page budget
The budget controls item counts.
It does not directly guarantee final page counts.
That distinction matters.
You can still get a medium reading with too much visual air if answer-space logic is wrong.
The current system is count-dynamic, not fully page-budget-driven.
Treat page budget as a render concern on top of count budget, not as the same thing.

## 42. System prompt assembly
Function:
`printout_system_instruction()`
This function encodes the cross-provider non-negotiables:
- Danish student-facing text
- artifact role split
- minimal metatext
- no answer leakage
- quote-length discipline
- abridged-reader self-containment
- active/open-book versus consolidation/recall distinction
If the product behavior feels wrong across providers, inspect this function first.

## 43. User prompt assembly
Function:
`printout_user_prompt(...)`
This function packages:
- source metadata
- compact source card
- lecture context
- course context
- length budget
- output contract
- required outputs
It defines what the model is actually asked to produce.
It also encodes a major architecture choice: the engine, not the model, owns more of the final worksheet mechanics than before.

## 44. The architecture correction that improved stability
The lane now treats `active_reading` as largely code-derived.
The prompt explicitly says the model should not spend generation effort on final solve-step formatting.
That was a major improvement.
The model is good at semantic content.
It is less reliable at machine-internal helper fields.
Moving more worksheet mechanics into code reduced failures on:
- `task_type`
- `blank_lines`
- mismatched section refs
- overly broad prompts

## 45. Normalization is the true internal IR boundary
Function:
`normalize_scaffold_payload(...)`
This is the most important function in the engine.
It turns raw provider JSON into the stable internal artifact shape that render and validation trust.
Think of it as the IR boundary.
Before normalization, provider output may be sloppy.
After normalization, the rest of the system expects coherence.
Many future fixes should land here, not in the raw prompt or final renderer.

## 46. What normalization currently repairs
Normalization does all of the following:
- fixes titles
- migrates legacy payload shapes
- repairs `opening_passages`
- normalizes teaser paragraphs
- normalizes subproblems
- normalizes `answer_shape`
- normalizes quote anchors
- normalizes source passages
- inserts `no_quote_anchor_needed` fallbacks
- canonicalizes `solves_subproblem`
- derives `active_reading`
- rewrites consolidation references toward the abridged reader
- repairs diagram task structure
- normalizes optional exam-bridge content
This is intentionally a fail-soft stage.

## 47. `opening_passages` as a good example of fail-soft logic
`reading_guide.opening_passages` is supportive hidden structure.
It is not the printed core of the guide.
Provider responses sometimes underfill or mis-shape it.
The engine now tries to repair it.
If repair fails, the system can degrade gracefully instead of killing the entire candidate.
This is the right tradeoff because the printed reading guide primarily uses teaser paragraphs, not these helper objects.

## 48. `solves_subproblem` as a machine-link repair point
Provider output often varies here.
Sometimes it is a number.
Sometimes it is a label.
Sometimes the label text drifts.
Normalization canonicalizes it into stable refs like `Delproblem 1`.
That fix matters because later active-reading derivation relies on the guide and the abridged reader linking up correctly.
Without canonicalization, the content can be semantically good but mechanically disconnected.

## 49. `answer_shape` is a semantic and layout field
`answer_shape` influences more than wording.
It affects:
- task-type inference
- blank-line allocation
- compact versus extended answer space
- active-reading rebalance behavior
That means a bad `answer_shape` can create both content and layout bugs.
If a sheet feels oddly airy or cramped, inspect normalized `answer_shape` values before touching the PDF wrapper.

## 50. Active-reading derivation
Core function:
`_derive_active_reading_payload(...)`
This function synthesizes solve steps from:
- reading-guide subproblems
- abridged-reader sections
- local problems
- answer-form hints
This is one of the strongest design decisions in the current lane.
It lets the model focus on content while code handles worksheet mechanics.
It also made fresh generation significantly more stable across providers.

## 51. Why active-reading derivation was necessary
Before this change, the model had to author too many internal fields.
That caused repeated issues with:
- `task_type`
- `blank_lines`
- over-broad prompts
- mismatched section references
- inflated page counts
The current design is better.
Keep as much of active-reading structure code-owned as practical.

## 52. Task-type heuristics
Helpers to know:
- `_looks_like_decision_question(...)`
- `_looks_like_term_question(...)`
- `_infer_task_type(...)`
- `_normalize_task_type(...)`
These heuristics classify prompts into shapes like term, decision, and short paragraph.
They are not purely semantic.
Wording changes can therefore affect layout behavior indirectly through task-type inference.
Remember this if a prompt tweak changes worksheet density.

## 53. Response-space heuristics
Helpers:
- `_paragraph_blank_lines(...)`
- `_active_step_needspace_baselines(...)`
- `_append_response_space(...)`
- `_append_fill_to_page_response_area(...)`
This is where semantic intent becomes physical writing space.
Many visual bugs are actually response-space bugs.
If an active-reading sheet looks wrong, inspect these functions before blaming prompt text.

## 54. Consolidation remains partly model-owned
The model still provides more direct content for `consolidation_sheet` than for `active_reading`.
Typical model-owned pieces:
- overview bullets
- fill-in sentences
- diagram task prompts
The engine then repairs and constrains them.
This is acceptable because consolidation tasks are narrower and more mechanically checkable than active-reading solve steps.

## 55. Consolidation repair helpers
Important helpers:
- `_rewrite_diagram_task_for_abridged_only(...)`
- `_require_abridged_reference(...)`
- `_extract_required_elements_from_task(...)`
- `_normalize_required_elements(...)`
- `_ensure_minimum_required_elements(...)`
The key rule is that consolidation must be solvable from the abridged reader alone.
Tasks should not depend on original PDF figures or reopening the source PDF.

## 56. Validation happens after normalization
Primary validator:
`validate_printout_payload(...)`
Supporting validators:
- `_validate_v3_reading_guide(...)`
- `_validate_v3_abridged_reader(...)`
- `_validate_v3_active_reading(...)`
- `_validate_v3_consolidation(...)`
- `_validate_v3_exam_bridge(...)`
This split is intentional.
Repair first.
Fail hard later.
If you validate too early, fresh provider output becomes brittle.

## 57. What validation really enforces
Validation checks more than shape.
It also enforces product behavior, for example:
- count ranges within the budget
- quote anchors short enough
- source passages short enough
- active-reading prompts not too broad
- consolidation not leaking source-page dependencies
- exam-bridge count limits
A validation failure often indicates a real worksheet regression, not only malformed JSON.

## 58. The per-source orchestration function
Function:
`build_printout_for_source(...)`
This is the engine’s public center.
It orchestrates:
- source existence checks
- source-card loading
- compact lecture/course context loading
- output-path selection
- rerender versus fresh-generation logic
- prompt building
- provider invocation
- normalization
- validation
- internal JSON write
- Markdown/PDF rendering
- stale-file cleanup
Read this function if you need the whole source-to-artifact sequence in one place.

## 59. Fresh versus rerender flows
Fresh mode:
- builds prompt
- calls provider
- writes new internal JSON
- renders outputs
Rerender mode:
- loads existing internal JSON
- rejects seeded artifacts
- re-normalizes
- rerenders outputs
This distinction is important.
Rerendering is the correct tool for layout changes.
Fresh generation is the correct tool for content comparisons and provider evaluation.

## 60. Seeded artifacts are deliberately forbidden
The review lane now enforces fresh-from-source candidate generation.
Seeded or scaffold-recycled artifacts are invalid review candidates.
The engine rejects seeded review artifacts in rerender and skip-existing flows.
This protects evaluation integrity.
Do not reintroduce seeded shortcuts for convenience.
If a candidate should be comparable, it must have been generated under the current prompt and engine from the real source.

## 61. Artifact metadata is part of reproducibility
The internal JSON stores:
- provider
- model
- prompt version
- generation-config metadata
- variant metadata
This means a candidate artifact is both content and provenance.
If you compare outputs across providers or runs, inspect this metadata.
Two similar-looking worksheets may not have been produced under the same conditions.

## 62. The render split
Top-level functions:
- `render_printout_files(...)`
- `render_v2_printout_files(...)`
- `render_v3_printout_files(...)`
The candidate lane primarily uses v3.
V2 remains for compatibility with old artifacts and tests.
Do not delete v2 support casually unless you also migrate or retire every artifact and test that still depends on it.

## 63. Markdown is the real visible intermediate
The current pipeline is truly `JSON -> Markdown -> PDF`.
That means Markdown is the best intermediate for most textual review.
It is close enough to the final sheet to show wording and structure.
It is much cheaper to inspect than PDF.
It is also the best place to compare provider output before layout effects are added.
Respect the local workflow rule and inspect Markdown first for content changes.

## 64. The cover renderer
Function:
`render_compendium_cover_markdown(...)`
The cover page is not just decoration.
It anchors bundle order and can shape first-impression UX.
The cover renderer also injects hidden HTML comments that later become margin metadata in the PDF layer.
That coupling is easy to miss.
If you change cover logic, inspect the PDF wrapper too.

## 65. Hidden margin metadata
Helper:
`_pdf_margin_metadata(...)`
The renderer uses HTML comments like:
```text
<!-- printout-title: Reading Guide -->
<!-- printout-source: Grundbog kapitel 01 - Introduktion til personlighedspsykologi -->
<!-- printout-lecture: Forelæsning 1, uge 1 -->
```
The PDF wrapper parses these and uses them to build headers and footers.
If you rename or remove these comments, margin text degrades even though Markdown may still look fine.

## 66. Artifact-specific markdown renderers
Important functions:
- `render_reading_guide_markdown(...)`
- `render_abridged_reader_markdown(...)`
- `render_active_reading_markdown(...)`
- `render_consolidation_markdown(...)`
- `render_exam_bridge_markdown(...)`
These renderers apply the style contract.
They decide where bold, italics, monospace, answer space, and completion markers appear.
If the final sheet feels wrong visually, start here.

## 67. Reading-guide renderer quirks
The reading guide should feel like an appetizer, not a worksheet.
That means:
- short paragraphs
- visible breathing room
- no answer lines
- minimal metatext
If you make it too dense or too administratively labeled, you violate the product goal even if tests stay green.
Completion cues on this sheet must stay peripheral.

## 68. Abridged-reader renderer quirks
The abridged reader is a reading text.
It is not a worksheet.
It should not accumulate blanks, checkboxes, or visible helper lines.
It may include short quote anchors and short original passages when wording matters.
If you accidentally move worksheet behavior into this renderer, you erase the role separation that the design docs insist on.

## 69. Active-reading renderer quirks
The active-reading renderer is historically the most failure-prone worksheet renderer.
Common risks:
- prompts getting orphaned from their answer space
- too many blank lines for short answers
- the last synthesis answer inflating the page
- spacing looking too compressed or too diffuse
Recent fixes made this better by standardizing spacing and deriving more of the structure from code.
Still, this is one of the first places to inspect after layout regressions.

## 70. Consolidation renderer quirks
The consolidation renderer mixes:
- overview bullets
- inline blanks
- diagram instructions
- diagram drawing space
- completion footer
That makes it deceptively complicated.
Historically it produced almost-empty second pages when diagram space expanded badly.
It is better now, but still more sensitive than the abridged reader or reading guide.

## 71. Exam-bridge renderer quirks
The exam bridge remains part of the JSON schema but is optional at render time.
It should stay cue-like and oral-friendly.
If it becomes verbose, it stops helping oral exam rehearsal and starts reading like a handout.
That is why it is not rendered by default.
If you turn it on, remember that it is still a secondary artifact in the current workflow.

## 72. Completion markers
Completion markers are render-layer features, not semantic content.
They are controlled by variant metadata.
That is good design because the “definition of done” feel can be toggled without forcing prompt changes.
Current markers use `[ ]` text for PDF robustness.
Earlier attempts at prettier glyphs were less stable.
Do not assume a more decorative solution is automatically better.

## 73. Spacing contract
Spacing is now more standardized than before.
The engine uses a centralized spacing-token approach rather than scattered magic numbers.
Key helpers:
- `_spacing_cm(...)`
- `_vspace_cm(...)`
- `_vspace_key(...)`
- `_append_spacing_gap(...)`
If you reintroduce local ad hoc spacing numbers in renderers, future layout drift will return.
Keep spacing policy centralized.

## 74. PDF wrapper
Function:
`_pdf_wrapped_markdown(...)`
This function injects LaTeX-level header, footer, page-count, and keep-with-next behavior around the Markdown.
It also applies the lowercase monospaced margin metadata style.
This wrapper is not a trivial post-process.
It can change pagination.
Treat changes here as layout-sensitive and inspect real PDFs afterward.

## 75. Two-pass PDF generation
Function:
`markdown_to_pdf(...)`
Flow:
1. render a temporary PDF
2. inspect page count with `pdfinfo`
3. rerender final PDF with `side x/x`
This is why `pdfinfo` became a hard dependency.
It also means PDF generation is intentionally slower than one-pass rendering.
The benefit is stable page labels in headers and footers.

## 76. Render-toolchain preflight
Function:
`preflight_render_toolchain(render_pdf=True)`
Required binaries for PDF mode:
- `pandoc`
- one of `xelatex`, `lualatex`, `pdflatex`
- `pdfinfo`
Additional binary sometimes needed for OpenAI scanned-PDF source reads:
- `ocrmypdf`
Preflight happens early now.
That was added because hidden runtime dependencies caused expensive mid-run failures.

## 77. Output cleanup is part of correctness
Helpers:
- `_remove_output_pdf_files(...)`
- `_remove_output_markdown_files(...)`
- `_remove_output_json_files(...)`
- `_remove_stale_v3_output_files(...)`
Stale artifacts are dangerous.
They can make an operator inspect the wrong file and misjudge the system.
Cleanup is therefore not optional hygiene.
It is part of the correctness contract.

## 78. The `--no-pdf` stale-PDF bug and the fix
Earlier, a `--no-pdf` run could leave old PDFs in the user-facing source folder.
That was a serious workflow bug because content-only runs looked visually current when they were not.
The fix was:
- write Markdown only to internal `.scaffolding/.../rendered_markdown/`
- remove known exported PDFs from the user-facing source folder when `render_pdf=False`
Preserve this behavior.
It makes the JSON/Markdown-first development loop trustworthy.

## 79. Legacy alias support
Relevant helpers:
- `_promote_legacy_printouts_if_present(...)`
- `_cleanup_legacy_review_dirs(...)`
- `_sync_and_cleanup_legacy_aliases(...)`
The lane still knows about older `scaffolding/` output conventions and naming schemes.
That is compatibility glue for real historical artifacts.
It is easy to underestimate.
If you change path policy, inspect these functions too.

## 80. Why the path logic feels defensive
The code has lived through multiple output layout schemes:
- legacy production scaffolding folders
- older review numbering schemes
- newer flat source folders
- hidden internal scaffolding directories
Because of that history, path logic is intentionally conservative.
Do not simplify it casually unless you have checked old artifacts, rerender flows, and tests together.

## 81. The test suite layout
Primary test files for this lane:
- `tests/test_printout_review_printout_engine.py`
- `tests/test_printout_review_generate_candidates.py`
- `tests/test_openai_preprocessing.py`
Upstream context tests that still matter:
- `tests/test_personlighedspsykologi_recursive.py`
- `tests/test_personlighedspsykologi_printouts.py`
The first three are the most important for day-to-day candidate-lane work.

## 82. What the engine test suite really locks down
`tests/test_printout_review_printout_engine.py` covers:
- normalization of malformed payloads
- title and stem stability
- active-reading derivation
- optional exam-bridge behavior
- Markdown render paths
- internal versus user-facing output separation
- stale Markdown cleanup
- stale PDF cleanup
- render-toolchain preflight
- spacing/render expectations
Read this suite as executable documentation.

## 83. What the CLI test suite really locks down
`tests/test_printout_review_generate_candidates.py` covers:
- batch continuation behavior
- fail-fast behavior
- per-source manifest updates
- provider-specific metadata plumbing
- render-preflight behavior
- no-PDF handling
These are real operational contracts, not just unit-level niceties.
Breaking them makes the lane harder to run even if generation still “works”.

## 84. What the OpenAI test suite really locks down
`tests/test_openai_preprocessing.py` covers the source-ingestion side of OpenAI use.
That includes:
- text extraction
- OCR fallback
- timeout handling
- retry semantics
- JSON parsing expectations
Because OpenAI uses inline source text in this lane, these tests matter whenever you change source-handling behavior.

## 85. Read tests before code when confused
The tests often describe the intended contract more clearly than the implementation.
This is especially true for:
- output paths
- stale cleanup
- optional printout behavior
- active-reading derivation
- render preflight
If you are unsure what “correct” means, start with tests.
Then inspect the implementation.

## 86. Known intentional non-idioms
Several patterns are intentionally non-idiomatic:
- large monolithic `printout_engine.py`
- direct script execution with manual `sys.path` handling
- hidden HTML comments carrying PDF metadata
- heavy normalization before validation
- provider bootstrap fallbacks
These choices are not elegant, but they are practical for local operator workflows.
Do not remove them casually.

## 87. The current main weak points
The highest-risk areas today are:
- provider transport reliability
- OpenAI total input size budgeting
- active-reading answer-space tuning
- consolidation diagram page budget
- path cleanup across legacy layouts
- margin metadata coupling between Markdown and PDF
If a future regression appears, start with these surfaces.

## 88. Likely future failure: larger OpenAI source bundles
The system still lacks a hard total prompt budget across all inline source files for OpenAI.
That is a predictable future issue.
A robust fix would:
- compute a total request budget
- allocate budgets per source file
- log truncation decisions into artifact metadata
- test multi-file inputs explicitly
This should be addressed before expanding heavy OpenAI use.

## 89. Likely future failure: semantic drift upstream
If source-card or course-synthesis structures change upstream, the candidate lane may still import and run while producing worse prompts.
This is not an import failure.
It is semantic drift.
Whenever upstream recursive schemas change, review:
- `_compact_source_card(...)`
- `_compact_lecture_context(...)`
- `_compact_course_context(...)`
Do not assume tests alone will catch quality drift.

## 90. Likely future failure: typography changes causing pagination regressions
Spacing, headers, footers, and answer-space are interdependent.
A typography-only patch can create:
- extra pages
- orphaned prompts
- over-dense reading guides
- mispositioned completion footers
If you touch typography, inspect PDFs.
This is exactly the class of change the local AGENTS flags as PDF-sensitive.

## 91. The default debugging order
When a candidate looks wrong, debug in this order:
1. internal JSON
2. internal Markdown
3. PDF if layout-sensitive
4. manifest entry
5. prompt capture
6. upstream source card and compact context
This order is efficient.
It keeps you from staring at PDF symptoms when the real bug is structural.

## 92. When to inspect JSON first
Choose JSON-first when the issue is:
- wrong number of sections
- wrong artifact role
- wrong subproblem mapping
- answer leakage
- bad hidden helper fields
- odd source-passage structure
These are structural issues.
PDF inspection adds little value at that point.

## 93. When to inspect Markdown first
Choose Markdown-first when the issue is:
- wording too didactic
- reading guide too essay-like
- abridged version too note-like
- active reading too quiz-like
- consolidation too verbose
Markdown is the fastest learner-facing view that is still close to the final bundle.
Use it.

## 94. When to inspect PDF first
Choose PDF-first when the issue is:
- page breaks
- line spacing
- answer-space sizing
- diagram space
- header/footer placement
- completion-marker placement
- overall density or emptiness
The PDF surface is the truth for these problems.
Do not debug them in JSON alone.

## 95. Common operator commands
Bootstrap a run:
```bash
./.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/scripts/bootstrap_run.py \
  --run-name 2026-05-problem-driven-pilot \
  --lectures W01L1
```
Generate one source without PDFs:
```bash
./.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/scripts/generate_candidates.py \
  --manifest notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/runs/2026-05-problem-driven-pilot/manifest.json \
  --source-id w01l1-lewis-1999-295c67e3 \
  --no-pdf
```

## 96. Provider-comparison pattern
For content comparison, prefer `--no-pdf`.
Gemini example:
```bash
./.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/scripts/generate_candidates.py \
  --manifest notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/runs/<run>/manifest.json \
  --provider gemini \
  --no-pdf
```
OpenAI example:
```bash
./.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/scripts/generate_candidates.py \
  --manifest notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/runs/<run>/manifest.json \
  --provider openai \
  --model gpt-5.5 \
  --no-pdf
```

## 97. Safe content-change workflow
If you are changing prompts or normalization logic for content quality:
1. keep the schema contract intact
2. generate fresh candidates
3. inspect internal JSON
4. inspect internal Markdown
5. inspect PDFs only after content looks right or before final sign-off
This is the cheapest and most truthful loop.
It is also the workflow encoded in the local AGENTS file.

## 98. Safe render-change workflow
If you are changing spacing, typography, headers, footers, page-break logic, or output order:
1. rerender existing fresh candidate JSON
2. inspect PDFs
3. verify user-facing and internal output separation
4. verify stale cleanup
5. run the engine and CLI tests
Do not pay provider cost for layout-only changes.
Rerendering exists precisely for this workflow.

## 99. Definition of done for this lane
For content work:
- internal JSON is correct
- Markdown reads correctly
- relevant tests pass
- substantial changes get a final PDF spot-check
For render work:
- PDFs regenerate cleanly
- spacing and page breaks are acceptable
- headers and footers are correct
- output folders contain only the right artifacts
- no stale files remain
Docs and workflow guidance should also be updated if the change affects how future agents should work.

## 100. Final recommendations
Treat the candidate lane as a content-engine adapter, not a standalone mini app.
Respect the role split between printout types.
Keep user-facing output flat and internal artifacts hidden.
Prefer code-owned worksheet mechanics where the structure is mechanical.
Prefer model-owned content where genuine semantic choice matters.
Read tests as contract documents.
Inspect JSON and Markdown before PDF when the issue is content.
Inspect PDF first when the issue is layout.
Preserve fresh-from-source generation.
If you debug from upstream semantics through normalization to rendering, you will usually be looking in the right place.
