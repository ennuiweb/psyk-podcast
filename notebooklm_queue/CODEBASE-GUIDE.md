# NotebookLM Queue Codebase Guide
This guide is for coding LLMs working in `notebooklm_queue/`.
This directory is the orchestration spine for the repo's generated-content pipeline.
It is where show-scoped queue records are discovered, queued, executed, published, and reconciled.

Terminology warning: the Python code and CLI still use historical names such as
`JobIdentity`, `job_id`, `job_count`, and `--job-id`. In user-facing status
reports, translate those to `queue record`, `lecture record`, or `queue record
id`. Reserve `job` for a single output item: one episode/audio file, quiz,
infographic, printout, slide deck, or other generated artifact.

## 1. Business purpose
The repo's publication system does not treat generation as a one-off script run.
It treats generation as a stateful queue of lecture-scoped records that move through a publication pipeline.
`notebooklm_queue/` exists to make that pipeline:
- resumable
- inspectable
- scriptable
- automatable
- safer to run unattended

If `podcast-tools/` is the feed/media layer, `notebooklm_queue/` is the state machine that decides what should happen next.

## 2. The mental model
Think of this package as five layers:
1. queue state storage
2. queue-record discovery
3. provider-backed generation execution
4. publication side effects
5. top-level orchestration CLI

The most important thing to preserve is stage ordering and recoverability.

## 3. Directory structure
Important files:
- `cli.py`
- `orchestrator.py`
- `store.py`
- `models.py`
- `execution.py`
- `runner.py`
- `discovery.py`
- `publish.py`
- `metadata.py`
- `repo_publish.py`
- `downstream.py`
- `course_context.py`
- `prompting.py`
- `openai_preprocessing.py`
- `gemini_preprocessing.py`
- `personlighedspsykologi_recursive.py`

Read them in roughly that order for operational work.

## 4. Main operator entrypoint
Source: `notebooklm_queue/cli.py`

This is the canonical operator surface.
It is not a thin wrapper.
It is the main public API for humans and automation.

Snippet:
```python
# notebooklm_queue/cli.py
from .orchestrator import DrainShowOptions, ServeShowOptions, drain_show_queue, serve_show_queue

drain_show = subparsers.add_parser(
    "drain-show",
    help="Discover, resume, and advance one show through all ready queue stages.",
)
serve_show = subparsers.add_parser(
    "serve-show",
    help="Keep draining one show, waiting through retry windows until the backlog is idle or needs intervention.",
)
```

Key commands:
- `enqueue`
- `list`
- `inspect`
- `report`
- `transition`
- `claim-next`
- `retry-ready`
- `reconcile`
- `lock-check`
- `discover`
- `run-dry`
- `run-once`
- `prepare-publish`
- `upload-r2`
- `rebuild-metadata`
- `push-repo`
- `sync-downstream`
- `drain-show`
- `serve-show`

If you change semantics here, you are changing operator behavior for the whole queue lane.

## 5. The stage pipeline
Source: `notebooklm_queue/orchestrator.py`

The queue is not “run one lecture record”.
It is “advance a show through a fixed staged pipeline”.

The stage order is the most important contract in this package:
1. `sync_downstream`
2. `push_repo`
3. `rebuild_metadata`
4. `upload_r2`
5. `prepare_publish`
6. `run_once`

This looks inverted if you read it casually.
That is intentional.
The orchestrator works from highest publish stage backward so partially completed work is resumed safely before starting new generation.

Snippet:
```python
# notebooklm_queue/orchestrator.py
stages = [
    _sync_downstream_stage,
    _push_repo_stage,
    _rebuild_metadata_stage,
    _upload_stage,
    _prepare_publish_stage,
    _run_once_stage,
]
```

Do not reorder these casually.
It will break resumability semantics.

## 6. Storage and locking
Source: `notebooklm_queue/store.py`

`QueueStore` owns the durable queue-record representation on disk.
It is responsible for:
- per-show roots
- queue record files
- indexes
- reconciliation
- transitions
- show-level locking

This package is not database-backed.
The file layout is part of the persistence contract.

Important consequence:
- path layout changes are schema changes
- index rebuild logic matters
- write atomicity matters

When debugging queue weirdness, inspect `QueueStore` before assuming the runner is wrong.

## 7. Data model
Source: `notebooklm_queue/models.py`

`JobIdentity` is the historical internal name for the core queue-record identity contract.
It usually includes:
- `show_slug`
- `subject_slug`
- `lecture_key`
- `content_types`
- `config_hash`
- optional campaign-like metadata

The queue is lecture-scoped, not notebook-scoped and not file-scoped.
That is a meaningful product decision.

## 8. Discovery
Source: `notebooklm_queue/discovery.py`

Discovery turns show config and repo state into queue records.
This is where hidden coupling to `shows/<show>/` tends to surface.

If discovery is wrong, downstream systems can be perfectly correct and still produce the wrong artifacts.

Typical failure modes:
- wrong lecture selection
- missing content type inference
- stale config hash
- reading/generated artifact mismatch

## 9. Dry-run versus execution
Sources:
- `notebooklm_queue/runner.py`
- `notebooklm_queue/execution.py`

`build_dry_run_plan(...)` resolves what would be generated/downloaded.
`execute_job(...)` performs the real work.

This split matters because many issues are planning issues, not provider issues.
When debugging “why did it generate the wrong thing”, compare dry-run output with execution output.

## 10. Publication side effects
Sources:
- `publish.py`
- `metadata.py`
- `repo_publish.py`
- `downstream.py`

These files are separate because publication is not one action.
It is several stateful side effects:
- validate local generated artifacts
- upload approved media
- rebuild feed/inventory metadata
- commit/push generated repo artifacts
- wait for downstream GitHub workflow completion

`downstream.py` is especially important when queue records appear “stuck after push”.
That often means publication is waiting for post-push workflow confirmation, not that generation failed.

## 11. Provider split
Sources:
- `openai_preprocessing.py`
- `gemini_preprocessing.py`

These files are not queue orchestration.
They are provider backends used by higher-level generation flows.

OpenAI backend:
- local text extraction / OCR
- inline prompt assembly
- explicit timeout/retry handling
- char-budget and preprocessing concerns

Gemini backend:
- file upload
- readiness polling
- model call after remote file preparation
- best-effort uploaded-file cleanup

Do not assume both providers fail the same way.
They have different transport and preprocessing failure modes.

## 12. OpenAI preprocessing quirks
Source: `notebooklm_queue/openai_preprocessing.py`

Important non-idiomatic traits:
- secrets may come from env, local secret store, or Bitwarden CLI
- text extraction can fall back to OCR
- transient retry rules are partly string-match based
- scanned PDFs may require `ocrmypdf`

This file is operationally fragile because it bridges documents, OCR, secrets, and API transport in one place.
Be conservative here.

## 13. Gemini preprocessing quirks
Source: `notebooklm_queue/gemini_preprocessing.py`

Important traits:
- uploads source files first
- waits for remote readiness
- generation happens after file lifecycle succeeds
- cleanup is best-effort, not guaranteed

Typical failure classes:
- file never becomes ready
- transient connection reset
- generation transport error after successful upload

That means you can have partial remote side effects even when no artifact is written locally.

## 14. Course-specific recursive semantics
Source: `notebooklm_queue/personlighedspsykologi_recursive.py`

This file is critical even if you are not “working on the course pipeline”.
It builds the semantic artifacts that later drive:
- podcasts
- printouts
- summaries
- course context

Snippet:
```python
# notebooklm_queue/personlighedspsykologi_recursive.py
SUBJECT_SLUG = "personlighedspsykologi"
DEFAULT_SOURCE_CARD_DIR = DEFAULT_RECURSIVE_DIR / "source_cards"
DEFAULT_REVISED_LECTURE_SUBSTRATE_DIR = DEFAULT_RECURSIVE_DIR / "revised_lecture_substrates"
DEFAULT_COURSE_SYNTHESIS_PATH = DEFAULT_RECURSIVE_DIR / "course_synthesis.json"
```

If downstream output quality is mysteriously bad, inspect the upstream semantic artifacts before changing renderers.

## 15. Call chain: one end-to-end queue run
The most useful operational call chain is:
1. `cli.py:main`
2. `orchestrator.py:drain_show_queue` or `serve_show_queue`
3. stage-specific wrapper
4. `execution.py:execute_job` for generation
5. `publish.py` / `metadata.py` / `repo_publish.py` / `downstream.py` for publication
6. `store.py` transitions persist state after each phase

This is the chain to trace when behavior is wrong but no single component obviously crashed.

## 16. Where content context comes from
Sources:
- `course_context.py`
- `prompting.py`

These files assemble compact context payloads for generation.
They are the bridge between:
- raw course structure
- upstream semantic artifacts
- model prompts

If output tone, emphasis, or reading selection seems wrong, these are often more relevant than provider code.

## 17. Error-prone patterns
The major hazards in this package are:
- file-based durable state with multiple derived indexes
- staged orchestration whose order is semantically meaningful
- provider-specific retries and partial side effects
- hidden coupling to show config and artifact naming
- large course-specific preprocessing files living alongside generic queue code

This is not a clean hexagonal architecture.
It is a working orchestration system with real-world operational seams.

## 18. Safe change strategy
When changing queue behavior:
1. identify whether the bug is in discovery, planning, execution, or publication
2. preserve store/index/write contracts
3. preserve stage ordering unless the redesign is explicit and complete
4. test both fresh-run and resume-run behavior mentally
5. prefer additive telemetry over clever control-flow changes

If you are unsure where to start, start at `cli.py`, then `orchestrator.py`, then `store.py`.
