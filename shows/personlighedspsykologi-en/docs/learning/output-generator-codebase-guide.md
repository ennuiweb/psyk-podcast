# Output Generator Codebase Guide

This guide covers the `personlighedspsykologi-en` output-generator subsystem. It is written for a coding LLM that needs high-context orientation before editing code. The goal is to explain what the subsystem fundamentally does, where each branch lives, how the call chains run, and which quirks are easy to miss. The guide focuses on the learner-facing output path rather than the full repo. That means podcasts, reports, quizzes, printouts, publication manifests, and the prompt/context machinery that feeds them. It does not try to document unrelated portal internals or the
legacy Google Drive-only feed path in full.

## 1. Business Purpose

At the highest level, this repo turns university course material into study outputs. For `personlighedspsykologi-en`, the outputs are learner-facing podcasts, reports, quizzes, slides metadata, and printouts. Those outputs are then published into multiple delivery surfaces. The public surfaces are RSS, R2 object storage, Spotify sync metadata, and the Freudd portal content manifest. The underlying idea is not “prompt a model and hope”. The system tries to create explicit course understanding first. It then uses that understanding to make the downstream prompts narrower
and more useful. So the repo is both a generation system and a context-shaping system. The output-generator part sits at the boundary between course understanding and public delivery. That boundary is where most bugs are operational, naming, provenance, or compatibility bugs rather than pure algorithm bugs.

## 2. What Counts As “The Output Generator Part”

For this guide, the relevant subsystem includes these branches. `notebooklm_queue/` is the queue-owned orchestration, prompt assembly, publication, and metadata layer. `notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py` is the main local generation wrapper for podcasts, quizzes, infographics, and report artifacts. `notebooklm_queue/course_context.py` and `notebooklm_queue/prompting.py` are the prompt-construction core. `notebooklm_queue/personlighedspsykologi_recursive.py` is upstream, but it matters because it creates the compact semantic artifacts
that the output layer consumes. `notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/` is the current canonical PDF-producing printout system. `notebooklm_queue/personlighedspsykologi_printouts.py` is the older legacy printout builder and still needs to be replaced by, or integrated with, the review engine. `shows/personlighedspsykologi-en/` contains show config, prompt version config, published manifests, and show-level docs. `podcast-tools/gdrive_podcast_feed.py` is the final feed builder that turns queue-published artifacts into RSS and inventory outputs.

## 3. The Fast Reading Order

If you are a coding model entering cold, read in this order. First read [TECHNICAL.md](/Users/oskar/repo/podcasts/TECHNICAL.md). Then read [docs/notebooklm-automation.md](/Users/oskar/repo/podcasts/docs/notebooklm-automation.md). Then read [shows/personlighedspsykologi-en/docs/learning/learning-material-outputs.md](/Users/oskar/repo/podcasts/shows/personlighedspsykologi-en/docs/learning/learning-material-outputs.md). Then read [shows/personlighedspsykologi-en/config.github.json](/Users/oskar/repo/podcasts/shows/personlighedspsykologi-en/config.github.json). Then read
[notebooklm_queue/adapters.py](/Users/oskar/repo/podcasts/notebooklm_queue/adapters.py). Then read [notebooklm_queue/execution.py](/Users/oskar/repo/podcasts/notebooklm_queue/execution.py). Then read [notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py](/Users/oskar/repo/podcasts/notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py). Then read [notebooklm_queue/prompting.py](/Users/oskar/repo/podcasts/notebooklm_queue/prompting.py). Then read
[notebooklm_queue/course_context.py](/Users/oskar/repo/podcasts/notebooklm_queue/course_context.py). Then read [notebooklm_queue/publish.py](/Users/oskar/repo/podcasts/notebooklm_queue/publish.py), [notebooklm_queue/metadata.py](/Users/oskar/repo/podcasts/notebooklm_queue/metadata.py), and [notebooklm_queue/repo_publish.py](/Users/oskar/repo/podcasts/notebooklm_queue/repo_publish.py). Then read the printout docs and engines if the task touches printouts.

## 4. Top-Level Directory Map

`shows/` This is the canonical show-level configuration and published artifact root. For this subsystem, `shows/personlighedspsykologi-en/` is the operational show root. It contains configs, inventories, manifests, semantic artifacts, and docs.

`notebooklm_queue/` This is the queue-owned runtime package. It owns discovery, durable state, prompt assembly, publication, and downstream verification. It is the best place to understand the intended production architecture.

`notebooklm-podcast-auto/` This is the older generation-wrapper world. It still matters heavily. The queue usually shells out into these wrappers instead of replacing them with a pure in-package generator. For `personlighedspsykologi`, this branch is still the direct generation surface.

`podcast-tools/` This contains feed-generation and storage-backend code. The output generator eventually hands off here to regenerate RSS and inventory data.

`scripts/` This contains many sidecar rebuild, audit, and sync helpers. The queue metadata stage relies on several of them. Do not assume “scripts/” means throwaway code here. Some of these scripts are hard dependencies in the publication pipeline.

`tests/` The tests are unusually useful for this subsystem. A lot of behavior is compatibility-driven and easier to infer from tests than from the implementation.

## 5. Show-Level Directory Map

Inside `shows/personlighedspsykologi-en/`, pay special attention to these files. `config.github.json` This is the queue-owned publication config for the live show.

`prompt_versions.json` This is the canonical place for human-readable prompt/setup version labels.

`content_manifest.json` This is both an output and an input. It is a portal-side published artifact, but it is also the source from which `course_context.py` builds lecture context notes.

`episode_inventory.json` This is the canonical published episode inventory used by discovery skipping and later sidecars.

`media_manifest.r2.json` This is the canonical R2 publication manifest for audio objects.

`quiz_links.json` This maps published audio to quiz URLs and quiz difficulty variants.

`source_catalog.json` This is not a learner-facing output, but it is a critical bridge between source files and output generation.

`source_intelligence/` This contains source cards, lecture substrates, revised lecture substrates, podcast substrates, and the recursive index.

`course_glossary.json`, `course_theory_map.json`, `source_weighting.json`, `course_concept_graph.json` These are semantic context artifacts consumed by `course_context.py`.

`docs/` This contains the human contracts for outputs, printouts, preprocessing, and operations.

## 6. Subject Wrapper Directory Map

Inside `notebooklm-podcast-auto/personlighedspsykologi/`, the important branches are these. `scripts/` This holds the live generation and download wrappers. `generate_week.py` is the main orchestration file for local and queue-triggered generation. `download_week.py` is the retrieval side of the NotebookLM artifact lifecycle. `sync_reading_summaries.py` and `sync_regeneration_registry.py` are publication-side sync helpers.

`output/` This is the canonical local output tree that queue publication scans. Queue execution treats this directory as the source of publishable artifacts. Naming and legacy alias handling here matter a lot.

`evaluation/episode_ab_review/` This is the podcast-candidate review lane. It matters if you are changing audio prompts or prompt-system experiments.

`evaluation/printout_review/` This is the current canonical PDF-producing printout system. It remains intentionally separate from the old main output tree until integration is done.

## 7. Queue Package Directory Map

Inside `notebooklm_queue/`, these files form the main output path. `cli.py` Command-line entrypoint.

`discovery.py` Creates lecture-scoped jobs from show configs and published inventory.

`adapters.py` Binds a show slug to generator/downloader scripts and the config hash logic.

`execution.py` Runs generate/download commands and interprets their partial-output state.

`publish.py` Scans local output directories and creates upload bundles, then uploads media to R2.

`metadata.py` Rebuilds RSS, quiz links, Spotify map, content manifest, and ledger artifacts after upload.

`repo_publish.py` Commits and pushes the generated repo-side artifacts using an allowlist.

`downstream.py` Waits for post-push workflows like Freudd deploy to finish before closing the queue job.

`orchestrator.py` Drains a show through the above stages until the backlog is idle or blocked.

`store.py` Persists jobs, run manifests, publish manifests, and locks outside git.

`prompting.py` Builds audio and report prompts from normalized config plus selected context.

`course_context.py` Compiles lecture-aware context notes from `content_manifest.json` and semantic artifacts.

`personlighedspsykologi_recursive.py` Builds the semantic artifacts that `course_context.py` and printout builders later consume.

`personlighedspsykologi_printouts.py` Legacy/outdated printout builder awaiting integration with the canonical review engine.

## 8. The Single Most Important Architectural Fact

The queue does not directly generate podcast artifacts itself. It shells out into subject-specific wrappers. That means the runtime is hybrid. State management lives in `notebooklm_queue/`. Actual generation still lives in `notebooklm-podcast-auto/personlighedspsykologi/scripts/`. This split is deliberate, but it creates duplication and compatibility traps. If you change naming, output routing, or prompt construction, you often need to touch both worlds. Many bugs happen when a queue assumption drifts away from wrapper behavior.

## 9. End-To-End Call Chain

The end-to-end path looks like this. Discovery finds lecture jobs. Execution claims a job and launches `generate_week.py`. `generate_week.py` builds source lists and prompt text, then shells out again into `generate_podcast.py`. `generate_podcast.py` writes request logs and later artifacts into the canonical output tree. `download_week.py` later resolves pending NotebookLM artifacts and writes files into the same tree. `execution.py` notices whether there are pending request logs, finished outputs, or both. If publishable outputs exist, the job moves toward
`awaiting_publish`. `publish.py` turns the output tree into a bundle and uploads media to R2. `metadata.py` regenerates feed-side and portal-side repo artifacts. `repo_publish.py` commits and pushes the allowlisted generated files. `downstream.py` waits for the downstream deploy workflow if required. The final user-visible results become RSS entries, R2 objects, Spotify mappings, quiz links, and Freudd content entries.

## 10. Discovery Layer

The queue discovers lectures through `notebooklm_queue/discovery.py`. It does not scan arbitrary directories. It uses a `ShowAdapter` from `adapters.py`. For `personlighedspsykologi-en`, discovery uses `shows/personlighedspsykologi-en/auto_spec.json`. Lecture aliases are normalized into canonical `W##L#` keys. By default, discovery skips lecture keys that already appear in the published `episode_inventory.json`. That default matters. It prevents a fresh queue store from trying to regenerate the whole back catalog. If you are debugging “why is discovery not finding my
lecture”, check `include_published`, the inventory, and the normalized lecture key format first.

Source: `notebooklm_queue/adapters.py`
```python
SHOW_ADAPTERS: dict[str, ShowAdapter] = {
    "personlighedspsykologi-en": ShowAdapter(
        show_slug="personlighedspsykologi-en",
        subject_slug="personlighedspsykologi",
        discovery_source="auto_spec_rules",
        generator_script="notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py",
        downloader_script="notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py",
    ),
}
```

Why it matters. The queue’s notion of “generation” is just “call this wrapper with this lecture key”. If you change wrapper location, CLI flags, or output root, update the adapter first.

## 11. Config Hashing

The adapter computes a config hash over multiple files. That hash becomes part of the queue job identity. For `personlighedspsykologi-en`, the hash includes `auto_spec.json`, `config.github.json`, and `prompt_config.json`. This is important because the queue treats config changes as job-identity changes. If you silently change prompt behavior without updating one of those files, the queue may not realize that a regeneration is logically different. Conversely, harmless changes to prompt config can create new jobs.

## 12. Execution Layer State Logic

`notebooklm_queue/execution.py` is the first place to read if jobs seem stuck. It does not merely run a command and wait for success. It interprets three different partial states. There can be request logs without finished artifacts. There can be finished artifacts plus more request logs still pending. There can be no request logs and no outputs, which is treated as failure. The important state distinction is between `waiting_for_artifact` and `awaiting_publish`. `waiting_for_artifact` means no new publishable bundle exists yet. `awaiting_publish` can happen even while
some request logs remain pending. That is how partial lecture publishes work.

Source: `notebooklm_queue/execution.py`
```python
if latest_progress["pending_request_count"] > 0:
    if _has_unpublished_outputs(job=job, progress=latest_progress):
        state = STATE_AWAITING_PUBLISH
    else:
        state = STATE_WAITING_FOR_ARTIFACT
```

Why it matters. This means a job can legitimately publish a partial lecture bundle and later resume for remaining artifacts. Do not collapse these states together in later changes.

## 13. Retry Classification

Execution retries are string-pattern driven. Rate limits, profile cooldown exhaustion, and transient NotebookLM failures are detected from stderr/stdout text. The retry backoff is progressive and capped. It is not based on structured error objects from downstream wrappers. This is fragile but intentional. If you change error message wording in the wrappers, you can accidentally disable queue retries. The retry scheduler also requires a valid ISO timestamp for `retry_scheduled`.

## 14. The Queue Does Not Trust Missing Outputs

After each generate/download phase, execution scans the canonical output directory. It counts artifacts by suffix. `.mp3` becomes `audio`. `.png` becomes `infographic`. `.json` becomes `quiz`. Request logs are explicitly ignored as artifacts. A publishable bundle hash is calculated over relative path, artifact type, size, and SHA256. This hash is how the queue knows whether new unpublished outputs exist. That means output naming is part of the state machine. Renaming a file changes the bundle hash even if the content is identical.

## 15. Orchestrator Stage Order

`notebooklm_queue/orchestrator.py` drains stages in reverse chronological value order. It first tries downstream sync. Then repo push. Then metadata rebuild. Then upload. Then publish-bundle preparation. Then execution. This lets resumable jobs continue from the furthest completed point. It is not just a pipeline runner. It is a “resume anywhere” state machine. If you add a stage, you must think about resume semantics, not just forward flow.

## 16. Local Generation Wrapper: Core Role

`notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py` is the main subject wrapper. It plans and generates per-lecture artifacts. It supports `audio`, `infographic`, `quiz`, and `report`. It can generate weekly overview artifacts, per-source artifacts, and short/brief variants. It resolves readings and selected slides into a unified source list. It also handles config-tagged filenames, profile rotation, legacy output migration, and optional review-manifest filtering. This is why the file is 4000+ lines long. It is both orchestration and compatibility
glue.

## 17. Why `generate_week.py` Is So Long

The file contains at least six concerns. CLI argument parsing. Filesystem/source discovery. Prompt normalization wrappers around `notebooklm_queue.prompting`. Profile rotation and cooldown logic. Legacy filename compatibility logic. The triple nested planning/execution loops for weekly, per-source, and short outputs. This is not ideal, but it is the current truth. Treat it as a compatibility-critical wrapper, not a clean domain module.

## 18. Wrapper Source Resolution

The wrapper reads from a OneDrive-backed source root by default. It also resolves a macOS Finder alias for the output root if needed. That alias handling exists for real local-machine reasons. It is not generic code. The docs explicitly warn that `output/` must be a real directory for shared mirror steps. If you touch `resolve_output_root`, be careful not to break the alias case or the “already a directory” fast path.

## 19. SourceItem Is The Core Local Abstraction

The wrapper uses a `SourceItem` named tuple for each generation target. Fields are `path`, `base_name`, `source_type`, `slide_key`, and `slide_subcategory`. This abstraction is the bridge between raw files and prompt-building logic. A lot of branch logic checks `source_type == "slide"` versus `"reading"`. If you add new source kinds, the prompting stack will not automatically understand them. The system is intentionally hardcoded around reading vs slide distinctions.

## 20. Slide Inclusion Is Selective

Slides are not all treated equally. `INCLUDED_SLIDE_SUBCATEGORIES` currently includes `lecture` and `exercise`. `seminar` slides are excluded from generation inputs in `generate_week.py`. However, seminar slide metadata can still appear in the course context note. This is a subtle but important distinction. Seminar slides influence prioritization, but they are not always direct generator inputs. Do not assume “all catalogued slides become direct outputs”.

## 21. Course Context Injection

The wrapper delegates the heavy lifting to `notebooklm_queue/course_context.py`. It loads a context bundle from `content_manifest.json` plus `docs/core/overblik.md`. It then builds a lecture-aware context note per prompt. That note can include course frame, source character, lecture summary, slide titles, reading map, semantic guidance, and podcast substrate guidance. This is the main mechanism that ties upstream course understanding to downstream generation. If output quality changes unexpectedly, inspect the generated course context note. It is often more important than the
literal custom prompt text.

Source: `notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py`
```python
course_context_bundle = course_context_helpers.load_course_prompt_context_bundle(
    repo_root=repo_root,
    config=course_context_cfg,
    slides_catalog_path=slides_catalog_path,
)
```

And later.
```python
weekly_course_context_note = build_course_context_note(
    course_context_bundle=course_context_bundle,
    course_context_cfg=course_context_cfg,
    lecture_key=week_label,
    prompt_type="weekly_readings_only",
)
```

## 22. Prompting Layer Responsibilities

`notebooklm_queue/prompting.py` is not a generic prompt template file. It is a normalization and assembly module. It defines defaults for audio prompt strategy, exam focus, study context, meta prompting, audio prompt framework, and report prompt strategy. Then it validates and normalizes user config from `prompt_config.json`. Then it assembles final prompt sections in a deterministic order. The wrapper mostly passes through to this module. So if you want to change the shared prompt contract, change `prompting.py`, not just the wrapper.

## 23. Audio Prompt Structure

Audio prompts are built from a layered section model. Audience and tone come from `audio_prompt_strategy`. Prompt-type specific focus bullets come from `prompt_types`. Exam focus is a separate priority lens. Framework rules are separate again. Course context, when present, is inserted before source roles and after the main task framing. Meta prompt sidecars are appended at the end. This sequencing is deliberate. Changing the order can materially change prompt behavior even without changing the text.

Source: `notebooklm_queue/prompting.py`
```python
sections.append(f"{heading}\n{course_context_note.strip()}")
sections.append(f"{rules_heading}\n{_format_bullets(course_context_rules)}")
sections.append(_source_roles_section(...))
sections.append(f"Focus on:\n{_format_bullets(focus_items)}")
sections.append(f"{exam_focus['heading']}\n{_format_bullets(exam_items)}")
sections.append(f"{prompt_framework['heading']}\n{_format_bullets(framework_rules)}")
```

## 24. Source Roles Are Hardcoded And Important

The system treats readings, lecture slides, and seminar slides as having different interpretive roles. This matters for both prompt construction and course-context selection. Readings are for claims, distinctions, and argumentative depth. Lecture slides are for sequence, framing, and emphasis. Seminar slides are for application, clarification, and likely misunderstandings. This role split is a core design principle, not a minor detail. A change that blurs these roles can degrade output quality even if all files are still present.

## 25. Short Prompt Mode Is Thinner On Purpose

`short` outputs are not just regular prompts with a shorter length flag. The prompting layer trims focus items, trims exam items, and trims course-context rules. `course_context.py` also trims the context note more aggressively in short mode. So `short` is a separate contract, not a small parameter tweak. If you compare long and short outputs, remember that both the prompt and the context note are structurally different.

## 26. Report Prompt Path

Reports use the same context-selection layer as audio. They do not use the same prompt scaffolding. `build_report_prompt` is simpler and explicitly describes a study-guide style output. This is the first concrete non-audio consumer of the course-context layer. That matters architecturally. It proves the system is designed to reuse one context-selection layer across multiple output families. So if you refactor course context, keep audio and report consumers in sync.

## 27. Meta Prompt Sidecars

Meta prompting is a sidecar-note mechanism. Per-source sidecars can live next to source files. Weekly sidecars can live in the lecture directory. If enabled, their contents are appended as “external pre-analysis”. There is also an automatic meta-prompt generation mode. For course-understanding-backed podcast runs, the docs say this automatic mode is intentionally disabled in the checked-in config. That is because course-context artifacts are the preferred context source now. A model editing this stack should not re-enable automatic sidecars casually.

## 28. Config-Tagged Filenames Are Not Cosmetic

The wrapper appends a human-readable `{...}` config tag token to output filenames by default. This token includes content type, language, some format parameters, and a prompt hash. The tag is there to preserve variant identity in the filesystem and publication path. Some flows require it. For example, `quiz.difficulty=all` is rejected unless config tagging is enabled. If you remove or weaken config tagging, you break multi-difficulty coexistence and reproducibility.

## 29. Filename Length Handling

Config tags can push filenames over the 255-byte limit. The wrapper truncates the base stem while preserving the tag tail. This behavior is intentional and tested. It means visible title text may be truncated even though the config tag remains stable. If you later parse filenames, do not assume the visible title stem is fully preserved. The tag is the stable identity anchor.

## 30. Legacy Output Aliases

The wrapper contains explicit migrations and alias handling for old filenames. Weekly overview used to be `Alle kilder`. It is now `Alle kilder (undtagen slides)`. Some older reading outputs also used a leading `X ` prefix. Skip logic checks current names and legacy aliases. Migration helpers rename legacy outputs when possible. This matters because duplicate or skipped generation bugs often come from alias mismatches. Read the alias helpers before touching output naming.

## 31. Weekly vs Per-Source vs Short Output Loops

The wrapper effectively has three generation loops. Weekly overview generation runs once per lecture when multiple readings exist. Per-source generation runs for each reading and selected slide. Short/brief generation runs as an optional second per-source family. These loops are duplicated in both planning and execution blocks. That duplication is error-prone, but it is current behavior. If you add a new output type or new condition, you usually need to update both the dry-run planning branch and the real execution branch. Failing to do that creates misleading dry runs.

## 32. Profile Rotation Logic

The wrapper can rotate among NotebookLM profiles. It tracks cooldowns per profile based on request logs and error text. Rate limit, auth, and profile-scoped failures each create cooldowns. The preferred profile is updated from the auth metadata written into request logs. That means output request logs have control-plane value beyond debugging. If request-log shape changes, profile rotation can break. The queue’s retry logic and the wrapper’s profile rotation are separate systems. Do not confuse them.

## 33. Request Logs Are First-Class Artifacts

Every generated output can have `.request.json` and `.request.error.json` sidecars. The queue watches them. The wrapper uses them for skip decisions. Profile cooldown logic reads them. Partial publish logic depends on them. Legacy alias resolution also checks them. If you are debugging duplicate generation, missing publishes, or profile rotation, inspect the request logs first.

## 34. Generate Command Boundary

The wrapper does not directly talk to NotebookLM APIs. It shells into `notebooklm-podcast-auto/generate_podcast.py`. This command receives notebook title, instructions, artifact type, output path, format options, profile options, retry options, and source paths. The wrapper treats a timeout or non-zero exit as recoverable if a request log with an `artifact_id` exists. That is a very important behavior. A failed subprocess can still mean “artifact successfully queued upstream”. Do not naively turn every non-zero subprocess exit into a hard failure.

Source: `notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py`
```python
try:
    result = subprocess.run(cmd, check=False, timeout=generator_timeout)
except subprocess.TimeoutExpired:
    if request_log_has_artifact(output_path):
        return
```

## 35. Review Manifest Filtering

`generate_week.py` can filter generation using an episode A/B review manifest. This is only loosely related to production. But the filtering logic is deep enough that it influences per-source and short generation. It matches by normalized output key, source paths, or slide keys. If you see surprising omissions in review runs, inspect the normalization helpers. They strip config tags and normalize title prefixes. This is another reason not to casually rename output files.

## 36. Course Context Bundle Loading

`course_context.py` loads context from show-relative paths. If explicit paths are absent, it derives them from the slides catalog location. That means the slides catalog path is not only about slides. It is also used as an anchor to find `content_manifest.json` and `docs/core/overblik.md`. If you move or pilot a show config, make sure the path resolution still leads to the right show directory.

## 37. Course Context Note Composition

The context note is built from multiple sections. `Course and lecture frame`. `Source character`. `Lecture synthesis`. `Teaching context`. `Reading map`. `Semantic guidance`. `Podcast substrate`. `Target source fit`. `Grounding rules`. Not every note includes all sections. The sections depend on prompt type, source kind, configured limits, and which semantic artifacts exist. If a generated prompt feels oddly generic, check which note sections are missing.

## 38. Semantic Guidance Selection

The semantic guidance is not a blind dump of glossary and theory map data. It ranks and filters items using evidence-origin priorities and source-match bonuses. The evidence-origin priority changes by prompt type. For example, single-slide prompts prioritize lecture- or seminar-framed evidence more than single-reading prompts do. This is subtle but important. It means the same semantic artifact can surface differently depending on the target output. This is one of the strongest examples of the repo encoding real pedagogical structure instead of generic RAG.

## 39. Podcast Substrate Injection

Podcast substrate injection is optional and compact. It is gated behind `course_context.podcast_substrate.enabled`. The substrate file is selected per lecture. Then a section within that file is chosen based on prompt type and source match. The resulting note gives angle, must-cover, avoid, grounding, concepts, tensions, and source-selection hints. This is only for audio-style prompts. Report prompts do not consume the podcast substrate section. If you modify substrate schema, update both the builder and the selector.

## 40. Recursive Pipeline Role

`notebooklm_queue/personlighedspsykologi_recursive.py` is upstream but central. It builds source cards from raw readings/slides. Then lecture substrates. Then course synthesis. Then revised lecture substrates. Then compact podcast substrates. The output-generator path consumes those artifacts rather than raw full-course prompts. This is the backbone of the “decomposed whole-course reasoning” design.

## 41. Recursive Artifact Freshness

The recursive module is full of freshness and dependency-hash logic. Existing artifacts can be skipped only if their dependency hashes still match. Different artifact stages compare different dependencies. This matters because output quality may degrade when course-understanding artifacts go stale. The queue does not rebuild them automatically as part of normal publication. So a coding model should not assume the semantic artifacts are always fresh. If a task touches course understanding, inspect freshness helpers and related indexes.

## 42. Output Layer Dependency On Recursive Artifacts

The output layer consumes these recursive outputs most directly. `source_cards/` feed printout builders and source-intelligence summaries. `revised_lecture_substrates/` feed printout lecture context. `course_synthesis.json` feeds printout course context and course-context note generation. `podcast_substrates/` feed audio prompt context when enabled. This means seemingly “downstream” bugs can originate in upstream recursive artifacts. If prompts look wrong but code seems unchanged, compare the substrate artifacts and their prompt versions.

## 43. Legacy Main-Code Printouts: Current State

`notebooklm_queue/personlighedspsykologi_printouts.py` is the older legacy printout builder. It still uses schema version `1`. Its JSON sections are `abridged_guide`, `unit_test_suite`, and `cloze_scaffold`. It writes under `output/<lecture>/printouts/<source_id>/`. It also keeps `scaffolds` as a legacy alias to the same data. This module is downstream of source cards and course synthesis but upstream of markdown/PDF rendering, but it is no longer the product-canonical printout path. Do not use this builder as the current printout contract.

## 44. Legacy Main-Code Printout Builder Call Chain

The legacy builder selects sources from `source_catalog.json`. For each source, it resolves actual source file paths from the subject root. It requires an existing source card. It optionally compacts revised lecture substrate and course synthesis context. It calls a Gemini JSON generator. It validates the returned payload. Then it writes `reading-printouts.json`. Then it renders markdown and PDFs. Finally it mirrors the output into the legacy `scaffolding/` alias path.

## 45. Legacy Main-Code Printout Compatibility Quirk

The legacy main-code printout artifact stores both `printouts` and `scaffolds`. They point to the same payload. This is pure compatibility scaffolding for callers that still expect the old key. The module also promotes legacy `reading-scaffolds.json` into the main output location if needed. So the old main-code printout path is already a migration bridge. A change that writes only `printouts` or only `scaffolds` can break older code.

Source: `notebooklm_queue/personlighedspsykologi_printouts.py`
```python
artifact = {
    "printouts": printouts,
    "scaffolds": printouts,
}
```

## 46. Legacy Main-Code Printout Rendering

The legacy renderer is simple compared with the review engine. It writes three markdown files. `01-abridged-guide.md` `02-unit-test-suite.md` `03-cloze-scaffold.md` Then it calls `pandoc` to render PDFs. It uses `xelatex` if available, otherwise plain pandoc defaults. There is no fancy PDF margin pass or compendium cover. This path is outdated for current product work.

## 47. Canonical Printout Review Engine: Why It Exists

The canonical current engine lives at `notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/scripts/printout_engine.py`. It is the PDF-producing system developed over the recent printout iteration and is now the product-canonical printout path. It remains outside the main output tree only because main-code integration is still pending. It uses a richer schema version `3`. It normalizes and validates much more aggressively. It separates user-facing PDFs from internal JSON/markdown scaffolding. It also supports both Gemini and OpenAI JSON generation while keeping the same downstream contract.

## 48. Review Engine Output Routing

The review engine writes user-facing output into `candidate_output/<source_id>/`. It writes the internal JSON artifact into `candidate_output/.scaffolding/<source_id>/reading-scaffolds.json`. If PDFs are disabled, markdown also stays in the internal `.scaffolding` tree. The user-facing output directory stays PDF-only or empty. This routing is deliberate. It prevents internal scaffolding files from being mistaken for sign-off artifacts. Tests enforce this behavior.

## 49. Review Engine Schema Split

The review engine supports both legacy schema `2` and current schema `3`. Schema `3` uses these sections. `reading_guide` `abridged_reader` `active_reading` `consolidation_sheet` `exam_bridge` The renderer adds a `00-cover` compendium file and can optionally render the exam bridge. The engine can rerender existing artifacts and normalize older payloads forward. This makes it more migration-heavy than it first appears.

## 50. Review Engine Title Canon

The engine hardcodes canonical English section titles. `Reading Guide` `Abridged Version` `Active Reading` `Consolidation Sheet` `Exam Bridge` These titles are not suggestions. They are normalized and tested. If a model returns creative titles, the engine will repair or reject them depending on path. This is a case where user-facing language is intentionally rigid for consistency.

## 51. Review Engine Budgeting

The review engine calculates a `length_budget` from page count, length band, and source-card complexity. This budget controls how many teaser paragraphs, sections, solve steps, diagram tasks, and exam-bridge elements are allowed. Short, medium, and long texts get different allowable ranges. The model prompt includes the budget contract. Validation also enforces it after generation. So this engine is not just “generate a JSON object”. It is “generate a JSON object within a source-sensitive cardinality envelope”.

## 52. Review Engine Uses Prompt Contract Text Instead Of JSON Schema Mode

The review engine intentionally sets `response_json_schema=None` during live generation. The comment and code around schema helpers explain why. Gemini rejects some `maxItems` constraints in response schemas. So the engine uses a human-readable JSON contract in the prompt and enforces the strict bounds locally. This is a very important quirk. If you try to “improve” it by restoring hard response-schema enforcement blindly, you may reintroduce provider-specific failures.

## 53. Review Engine Normalization Is Opinionated

`normalize_scaffold_payload` does a lot more than cleanup. It repairs bad abridged-reader references. It migrates legacy `abridged_checks` into `solve_steps`. It derives `active_reading` from the reading guide and abridged reader when needed. It maps unknown task type aliases to supported task types. It rewrites prompts that are too broad into narrower task verbs. This is deliberate pedagogical post-processing. The engine does not trust the model to satisfy the learner-fit contract directly.

## 54. Review Engine Validation Is Strict

Validation checks cardinality and required fields. It also checks pedagogy. Reading-guide teaser paragraphs must be substantial prose, not bullet-list fragments. Quote anchors must stay short to avoid copyright issues. `active_reading` must reference abridged-reader sections, not source pages. Consolidation tasks must not depend on original figures or page numbers. Exam-bridge content is validated only if the render flag says it will actually be rendered. This split is tested and intentional.

## 55. Review Engine Rendering Is Richer

The review renderer generates five or six artifacts. `00-cover` `01-reading-guide` `02-active-reading` `03-abridged-version` `04-consolidation-sheet` `05-exam-bridge` optionally It also adds optional completion markers. It uses explicit LaTeX spacing helpers to prevent sections from orphaning badly across pages. It computes page count with `pdfinfo` and does a second pandoc pass to print total pages in headers and footers. This is much more sophisticated than the legacy main-code printout renderer.

## 56. Review Engine Seed Rules

Seeded baseline-derived candidates are forbidden. The engine rejects `seeded_from_baseline` metadata. It also rejects reuse of existing artifacts whose generator provider is marked `seeded-from-baseline`. This matters when rerendering. The system allows rerendering only for fresh-from-source candidate JSON. The docs and tests both enforce this. If you add migration helpers here, do not create accidental seed paths.

## 57. Review Engine Provider Multiplexing

`generate_candidates.py` chooses provider `gemini` or `openai`. It builds a provider-specific `json_generator` callback. The downstream engine stays provider-agnostic. Provider-specific config metadata is still recorded into the artifact. This is a clean boundary. If you add a new provider, preserve the same `build_printout_for_source` contract and only swap the injected generator.

Source: `evaluation/printout_review/scripts/generate_candidates.py`
```python
provider_json_generator, provider_generation_config_metadata = _make_provider_json_generator(
    provider=provider,
    model=model,
)
result = printout_engine.build_printout_for_source(
    json_generator=provider_json_generator,
    generation_provider=provider,
    generation_config_metadata_override=provider_generation_config_metadata,
)
```

## 58. Publication Bundle Preparation

`notebooklm_queue/publish.py` scans the canonical local output directory and classifies artifacts. It does not publish directly from request logs or manifests. It reads actual files under the lecture output directory. It records both artifact counts and still-pending request logs. A partial bundle is valid as long as the requested artifact types for this run are present. This is what lets queue publication proceed even when some artifacts for the lecture are still pending upstream. If you change output file extensions or naming patterns, update bundle classification code
too.

## 59. R2 Upload Layer

Upload is currently R2-only for queue-managed publication. The show config must say `storage.provider = "r2"`. Upload verifies each object after writing it. Then it merges the artifact into `media_manifest.r2.json`. This manifest is a repo-side publication artifact, not only a runtime cache. If an upload completes but the manifest merge is wrong, feed rebuilds will still be wrong.

## 60. Metadata Rebuild Layer

`notebooklm_queue/metadata.py` is where “generation” becomes “published repo state”. It can run these phases. `sync_quiz_links` `validate_manual_summaries` `sync_regeneration_registry` `generate_feed` `validate_regeneration_inventory` `audit_slide_briefs` `sync_spotify_map` `rebuild_content_manifest` `sync_learning_material_registry` Which phases run depends on the show slug and whether the bundle contains quiz or infographic artifacts. For `personlighedspsykologi-en`, even audio-only bundles still rebuild content-manifest-facing metadata.

## 61. Metadata Validation Rules

Metadata validation is bundle-aware but still strict. Feed and inventory must exist. Spotify map must exist for shows that use it. `quiz_links.json` is required if quiz artifacts were actually in the bundle. `content_manifest.json` is always required for `personlighedspsykologi-en`. If quiz assets are required, `content_manifest.json` must actually contain quiz assets. This is an example of the repo failing closed on publication correctness.

## 62. Repo Publish Layer

`repo_publish.py` only commits allowlisted files. It checks `git status --porcelain`. Tracked changes outside the allowlist are a hard error. This is important because queue publication runs in a potentially dirty working tree. For `personlighedspsykologi-en`, the allowlist includes feed, inventory, quiz links, Spotify map, content manifest, media manifest, and both regeneration ledgers. If your change produces a new generated file that should be committed, you must update the allowlist.

## 63. Rebase Conflict Policy

Repo publish resolves rebase conflicts on allowlisted generated files by taking `--theirs`. During rebase, “theirs” means the queue-generated commit being replayed. This is the opposite of what many developers assume. The code comment says this explicitly. Do not change it casually. If you do, queue publication may start discarding its own generated artifacts during push races.

## 64. Downstream Completion Layer

After push, `downstream.py` optionally waits for a deployment workflow. For Freudd-connected shows, it only cares if the changed allowlist paths include `content_manifest.json`, `quiz_links.json`, or `spotify_map.json`. If yes, it waits for `deploy-freudd-portal.yml`. If not, no downstream target is required. This is path-sensitive. If you move or rename portal-facing files, downstream verification logic must follow.

## 65. Prompt Version And Setup Version Tracking

`shows/personlighedspsykologi-en/prompt_versions.json` stores two related concepts. `prompt_versions` These are artifact-stage prompt version labels like `reading_printouts` and `podcast_substrate`. `setup_versions` These are human-facing run labels like `podcast` and `printout`. The registry sync scripts use these labels. The queue metadata layer also appends them to sync commands. If you do prompt iteration work, keep these labels in sync with the actual generator changes or later analysis becomes misleading.

## 66. Regeneration Ledgers

There are two important ledgers. `regeneration_registry.json` This is podcast-centric publication tracking. `learning_material_regeneration_registry.json` This is the broader learner-material ledger for podcasts, printouts, quizzes, and slides. The queue metadata stage refreshes them. These files are not optional reporting fluff. They are used to answer “what has actually been regenerated under the current setup”. If you add a new output family or rename artifact metadata fields, update the sync scripts and tests.

## 67. Tests To Read First

If you touch prompts or wrapper naming, read `notebooklm-podcast-auto/personlighedspsykologi/tests/test_generate_week.py`. If you touch course context, read `tests/notebooklm_queue/test_course_context.py`. If you touch queue state transitions, read `tests/notebooklm_queue/test_execution.py` and `tests/notebooklm_queue/test_orchestrator.py`. If you touch the review printout engine, read `tests/test_printout_review_printout_engine.py`. If you touch the legacy main-code printout builder, read `tests/test_personlighedspsykologi_printouts.py`. If you touch metadata rebuild or ledgers, read
`tests/notebooklm_queue/test_metadata.py` and `tests/test_sync_personlighedspsykologi_learning_material_registry.py`.

## 68. Error-Prone Quirk: Duplicate Logic Between Wrapper And Shared Modules

`generate_week.py` re-exports many helpers from `prompting.py` and `course_context.py`. This can make it look like the wrapper owns the logic when it actually delegates. When fixing a prompt bug, verify whether the real implementation is in the wrapper or in the shared module. Patching only the wrapper alias is a common mistake. The wrapper often just passes through.

## 69. Error-Prone Quirk: “Report” Is A First-Class Content Type

Several older comments and help text still emphasize audio/infographic/quiz. But `report` is real and supported in the wrapper, output extension logic, and prompt builder. If you add validation or classification code, do not forget `report`. At the queue publication layer, report artifacts are currently not classified as publishable media artifacts. That means report generation is more local/output-tree oriented than queue-publication oriented. Be clear which layer owns reports before changing behavior.

## 70. Error-Prone Quirk: JSON Extension Means Different Things In Different Places

In `execution.py`, any `.json` output in the canonical lecture output directory counts as a `quiz`. In the printout systems, JSON is the internal artifact representation. The review printout engine therefore keeps JSON out of the user-facing output directory on purpose. This is not just aesthetic separation. It avoids accidental misclassification by queue publication logic.

## 71. Error-Prone Quirk: Legacy Names Still Affect Skip Logic

Even if you think you only changed present-day naming, `should_skip_generation` checks legacy aliases. That means old files can suppress new generation. If you are debugging a “why did it skip?” issue, inspect alias candidates, not only the exact current output path. This is especially relevant for weekly overview and old prefixed reading outputs.

## 72. Error-Prone Quirk: Seminar Slides Are Context But Usually Not Direct Inputs

This is easy to miss because the course context note mentions seminar slides. The actual generation source list in the wrapper excludes seminar slides from direct output generation. So a developer can think “seminar slides are already part of generation inputs” when they are only part of contextual prioritization. Changing that boundary would be a meaningful product change. Treat it as such.

## 73. Error-Prone Quirk: Short Output Applies To Select Families Only

Short generation is not universal. `BRIEF_SUPPORTED_CONTENT_TYPES` is `audio`, `infographic`, and `report`. Short quiz outputs are explicitly cleaned up as stale/disallowed. So the code actively prevents some short combinations even if filenames would allow them. A new content family needs an explicit decision about short support.

## 74. Error-Prone Quirk: Review Engine And Production Engine Share Terms But Not Contracts

Both engines talk about printouts/scaffolds. Both have legacy alias helpers. Both generate markdown/PDF. But the schemas, output routing, normalization behavior, and rendering expectations are different. Do not port a fix from one engine to the other without checking whether the assumptions still hold. The review engine is much more aggressive about normalization and pedagogy.

## 75. Error-Prone Quirk: Provider Errors Are Handled At Different Layers

The wrapper handles NotebookLM request-generation subprocess errors. The queue handles wrapper-phase retry scheduling from plain text messages. The review printout engine handles Gemini transient JSON-generation retries internally. OpenAI preprocessing has its own retry logging path. So “retry behavior” is not centralized. If you change error classes or messages, think across all three layers.

## 76. Error-Prone Quirk: Course Context Can Fail Open

`generate_week.py` catches `RuntimeError` from `load_course_prompt_context_bundle`. It prints a warning and disables course-aware lecture context for the run. That means output generation can continue with degraded context silently. If output quality drops, a context-bundle load warning may be the root cause. This is important in pilot or path-migration work.

## 77. Error-Prone Quirk: Prompt Version Labels Are Separate From Config Tags

Config tags hash actual prompt/config content for filenames. Prompt version labels are human-readable tracking labels in artifacts and ledgers. They are not interchangeable. A run can have a new config-tag hash without a new human-facing prompt version label. Or vice versa. When auditing regenerated outputs, use both.

## 78. Error-Prone Quirk: Queue Publication Only Owns Certain Artifact Families

Audio and infographics are uploadable media artifacts. Quiz metadata is synced as repo-side artifacts. Reports and printouts are currently more local/portal-supporting artifacts than queue-upload media. So “output generation” is broader than “queue publication”. Keep that distinction in mind when designing new features.

## 79. Where To Look For A Naming Bug

Check `generate_week.py` filename builders and legacy alias helpers first. Then check `config.github.json` feed filters and title settings. Then check `podcast-tools/gdrive_podcast_feed.py` if the bug is in published RSS or inventory. Then check any sync scripts that derive IDs from filenames. Most naming bugs are multi-layer.

## 80. Where To Look For A Missing Artifact Bug

Check the canonical local output directory under `notebooklm-podcast-auto/personlighedspsykologi/output/<lecture>/`. Check for `.request.json` and `.request.error.json`. Check `execution.py` progress classification. Check whether the queue job moved to `waiting_for_artifact` or `awaiting_publish`. If printouts are involved, check whether JSON was intentionally moved to an internal `.scaffolding` directory.

## 81. Where To Look For A Prompt-Quality Regression

Inspect the resolved prompt text from `generate_week.py --dry-run --print-resolved-prompts`. Inspect the generated course context note. Inspect `course_glossary.json`, `source_weighting.json`, `course_theory_map.json`, and `podcast_substrates/<lecture>.json`. Compare prompt version labels in `prompt_versions.json`. Only after that should you blame the raw custom prompt text in `prompt_config.json`.

## 82. Where To Look For A Publication Regression

Inspect the latest queue run manifest under the queue storage root. Inspect the publish manifest recorded in job artifacts. Check `publish.py` bundle classification, `metadata.py` phase failures, and `repo_publish.py` allowlist enforcement. Then inspect the repo-side generated artifacts under `shows/personlighedspsykologi-en/`. For Freudd-facing breakage, also inspect `downstream.py` and the deploy workflow result.

## 83. Where To Look For A Printout Regression

If it is a legacy main-code printout issue, inspect `notebooklm_queue/personlighedspsykologi_printouts.py`. If it is a current canonical printout issue, inspect `evaluation/printout_review/scripts/printout_engine.py`. If the issue is schema shape, inspect JSON first. If the issue is wording, inspect markdown. If the issue is layout, inspect PDFs and the render toolchain. The review workspace README says exactly this, and it is the right workflow.

## 84. Suggested Refactor Boundaries

If you need to refactor safely, these are the cleanest boundaries. Extract more planning/execution duplication out of `generate_week.py`. Keep `prompting.py` as the shared prompt-construction module. Keep `course_context.py` as the deterministic context-selection module. Do not mix queue-state logic into the wrapper. Do not move publication allowlist logic into generic git helpers. Integrate the review printout engine into the main path deliberately; do not revive or extend the old three-sheet builder as if it were still the product target.

## 85. Final Mental Model

Think of the subsystem as five layers. Layer 1 is source understanding. Layer 2 is context selection. Layer 3 is output request generation. Layer 4 is artifact publication. Layer 5 is learner-facing delivery surfaces. Most local bugs are layer-boundary bugs. The codebase is strongest when each layer speaks through explicit artifacts, filenames, and manifests. It is weakest when meaning is inferred implicitly from legacy names or scattered text patterns. When editing, preserve explicit contracts whenever possible.
