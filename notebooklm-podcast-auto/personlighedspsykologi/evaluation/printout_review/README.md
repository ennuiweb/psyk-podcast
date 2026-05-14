# Printout Review Workspace

This folder is the candidate/review workspace for the canonical printout system for
`personlighedspsykologi`.

Its current purpose is to generate, inspect, and iterate problem-driven reading
printout candidates.

The canonical schema-v3 engine now lives in:

`notebooklm_queue/personlighedspsykologi_printouts.py`

The review scripts import that main engine instead of owning a separate product
implementation.

The accepted problem-driven prompt overlay also lives in the main engine. Both
`scripts/build_personlighedspsykologi_printouts.py` and this workspace's
`scripts/generate_candidates.py` call the same `problem_driven_*` helpers, so
main and review generation cannot silently drift through separate prompt
builders.

## Current Use

The canonical printout track is:

- `problem_driven_v1`

It keeps the intended schema-v3 printout shape, but changes the learner-facing
behavior to emphasize:

- a mission to solve
- a problem map up front
- a self-contained abridged reader
- guided problem-solving from the abridged reader
- recall after the solve phase
- model-building payoffs
- a stronger final challenge

Current render preference:

- completion markers/check boxes stay off by default
- `exam_bridge` stays opt-in and is omitted unless the run explicitly enables it

All printouts generated through this workspace must be generated fresh from the
source with the current prompt and engine. Seeded or scaffold-recycled
artifacts are not valid canonical outputs.

## Why This Lives Here

The main output path and the candidate review path have separate output
contracts.

Main outputs are source-scoped under:

`notebooklm-podcast-auto/personlighedspsykologi/output/<lecture>/printouts/<source_id>/`

Candidate PDFs remain flat in this workspace's `review/` directory.

## Folder layout

- `prompts/problem-driven-v1.md`
  The editable prompt overlay for the current experiment.
- `CODEBASE-GUIDE.md`
  Dense architecture guide for coding LLMs working on this workspace.
- `scripts/printout_engine.py`
  Compatibility wrapper that re-exports the canonical schema-v3 engine.
- `scripts/bootstrap_run.py`
  Creates a run manifest and review-note skeletons from selected sources.
- `scripts/generate_candidates.py`
  Generates canonical review printouts into the shared flat review root.
- `scripts/run_parallel_candidates.py`
  Thin resumable parallel runner around `generate_candidates.py`.
- `review/`
  Shared user-facing PDF drop zone for all candidate printouts.
- `runs/<run-name>/manifest.json`
  Canonical manifest for one printout review run.
- `runs/<run-name>/notes/`
  Manual review notes for each selected source.
- `runs/<run-name>/prompts/`
  Exact prompt captures used for candidate generation.
- `review/.scaffolding/artifacts/<provider>-<model>/<source_id>/`
  Hidden provider/model-scoped JSON, Markdown, and PDF staging artifacts used by
  the shared review root.

Candidate PDFs now all land in one flat shared directory:

- `review/`

They are distinguished only by filename. The filename contract is:

- `<provider>-<model>--<source_id>--<printout-stem>.pdf`

Example:

- `openai-gpt-5_5--w01l1-lewis-1999-295c67e3--01-reading-guide.pdf`

The canonical exported bundle order is:

- `00-cover`
- `01-reading-guide`
- `02-active-reading`
- `03-abridged-version`
- `04-consolidation-sheet`
- `05-exam-bridge` only when explicitly enabled

This means reruns with the same provider/model for the same source overwrite the
same filenames, so file modification time is the easiest way to spot the newest
candidate set for that LLM.

Internal JSON artifacts live separately under a hidden provider/model/source folder:

- `review/.scaffolding/artifacts/<provider>-<model>/<source_id>/reading-scaffolds.json`

PDF rendering publishes source bundles defensively:

- PDFs render first in
  `review/.scaffolding/artifacts/<provider>-<model>/<source_id>/staging/`
- public `review/*.pdf` files are replaced only after the expected bundle is
  fully rendered and validated
- failed or interrupted renders should not leave new partial public bundles
- JSON is committed only after rendering succeeds, so existing JSON alone is not
  treated as completion when expected PDFs are missing

The manifest also records where the canonical baseline printout would normally
live for each source under the standard output root.

## Bootstrap a run

```bash
./.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/scripts/bootstrap_run.py \
  --run-name 2026-05-problem-driven-pilot \
  --lectures W01L1
```

This writes:

- `evaluation/printout_review/runs/2026-05-problem-driven-pilot/manifest.json`
- `evaluation/printout_review/runs/2026-05-problem-driven-pilot/notes/*.md`

and plans candidate output under:

- `evaluation/printout_review/review/`

## Dry-run candidate generation

```bash
./.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/scripts/generate_candidates.py \
  --manifest notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/runs/2026-05-problem-driven-pilot/manifest.json \
  --dry-run \
  --no-pdf
```

## Generate one candidate set

```bash
./.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/scripts/generate_candidates.py \
  --manifest notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/runs/2026-05-problem-driven-pilot/manifest.json \
  --source-id w01l1-lewis-1999-295c67e3 \
  --no-pdf
```

## Parallel candidate generation

For multi-source provider runs, prefer the parallel runner over ad hoc shell
backgrounding. It keeps one master state file and one per-source manifest per
worker while still delegating actual generation to `generate_candidates.py`.

```bash
./.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/scripts/run_parallel_candidates.py \
  start \
  --manifest notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/runs/2026-05-problem-driven-pilot/manifest.json \
  --provider gemini \
  --model gemini-3.1-pro-preview \
  --workers 3 \
  --force
```

Useful parallel commands:

- `start`
  Create `parallel-run.json`, create per-source manifests under
  `runs/<run-name>/parallel/<source_id>/`, then run incomplete sources.
- `resume`
  Recompute completion from manifests and files, then run only incomplete
  source bundles. Semantic options such as provider, model, source selection,
  `--force`, `--no-pdf`, and `--include-exam-bridge` must match the original
  run; change `--workers` only.
- `status`
  Print source, PDF, and worker status without changing anything.
- `verify`
  Like `status`, but exits non-zero if the run is incomplete.
- `cancel`
  Requests cancellation in `parallel-run.json`, signals the parent runner when
  it is alive, and terminates recorded worker process groups. The scheduler does
  not start more sources after cancellation is requested.

The runner intentionally does not replace `generate_candidates.py`; it is only
a small orchestration layer for safer parallelism.

## Generate with another provider/model

The review generator now supports both `gemini` and `openai` providers while
keeping the same downstream normalization and PDF pipeline.

OpenAI auth lookup order is:

1. `OPENAI_API_KEY`
2. local Oskar secret-store entry
3. Bitwarden lookup via `bws`

PDF rendering requires a local toolchain:

- `pandoc`
- one LaTeX PDF engine: `xelatex`, `lualatex`, or `pdflatex`
- `pdfinfo` for the final page-count pass used by headers/footers

OpenAI runs against scanned PDFs may additionally require:

- `ocrmypdf`

Example OpenAI run:

```bash
./.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/scripts/generate_candidates.py \
  --manifest notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/runs/2026-05-problem-driven-pilot/manifest.json \
  --source-id w01l1-lewis-1999-295c67e3 \
  --provider openai \
  --model gpt-5.5 \
  --no-pdf
```

Useful flags:

- `--provider`
  Choose `gemini` or `openai`. Default is `gemini`.
- `--model`
  Override the provider-specific default model. Defaults are currently
  `gemini-3.1-pro-preview` for Gemini and `gpt-5.5` for OpenAI.
- `--force`
  Overwrite the source's stable candidate artifact set for that provider/model
  with a fresh from-scratch generation.
- `--rerender-existing`
  Re-render the source's stable candidate filenames from its existing internal
  candidate JSON, but only when that JSON already comes from a fresh
  from-scratch candidate. Seeded legacy artifacts are rejected and must be
  replaced with `--force`.
- `--variant-prompt`
  Override the prompt overlay markdown for one run.
- `--source-id`
  Generate only a subset of the run entries.
- `--include-exam-bridge`
  Render the optional `05-exam-bridge` file for that run. Default candidate
  bundles stop at `04-consolidation-sheet`.
- `--no-pdf`
  Skip PDF rendering and write Markdown only to the internal
  `review/.scaffolding/artifacts/<provider>-<model>/<source_id>/rendered_markdown/`
  area. The shared
  user-facing `review/` directory stays PDF-only. Any previously rendered
  printout PDFs for that source/provider/model artifact set are removed so
  stale visual output cannot be mistaken for the current no-PDF artifact set.
- `--preflight-only`
  Check provider auth/API reachability and the local render toolchain without
  generating candidates.
- `--fail-fast`
  Stop on the first per-source error. By default, batch runs continue through
  all selected sources, record partial failures, and exit non-zero at the end
  if anything failed.

Batch-run manifests now update during execution:

- selected entries are marked `pending` at run start
- OpenAI runs use explicit request timeouts, OCR timeouts for scanned PDFs,
  and visible retry logging for transient transport failures
- provider generation attempts record `attempt_count`, `transient_error_count`,
  and `last_transient_error` when available
- each source writes its own final status as soon as it finishes
- long provider runs print per-source progress lines to stdout

This avoids stale old statuses from looking like fresh results when a batch
dies halfway through.

## Development workflow

Treat the printout pipeline as:

- `JSON -> Markdown -> PDF`

Default review loop:

- inspect JSON first when the issue is structural or schema-related
- inspect Markdown first when the issue is textual, editorial, or prompt-related
- inspect PDF when the change can affect rendering, or when a substantial
  change is ready for sign-off

In practice, that means:

- content-only prompt work should usually be reviewed in JSON or Markdown first
- layout-sensitive work must still be checked in PDF
- final sign-off on substantial printout changes should still include PDF inspection

Typical PDF-required cases:

- spacing
- typography
- page breaks
- answer-space sizing
- diagram space
- headers/footers
- completion-marker placement

## Working rule

This is the candidate review path for the canonical engine.

- do not point review output at the main production output root
- compare candidate printouts against the baseline artifacts recorded in the
  manifest
- treat baseline artifacts as comparison material only, never as seed material
- canonical printouts must always be generated fresh from source
- capture exact prompts per run so results are reproducible
- active_reading should solve the reading-guide subproblems with abridged_reader open
- active-reading and consolidation tasks must be solvable from the abridged
  reader alone
- judge learner fit first, not only schema validity

Before signing off on main/review integration, run the repository-level gate:

```bash
uv run python scripts/validate_personlighedspsykologi_printout_integration.py \
  --registry-check \
  --review-parity \
  --review-pdf-parity \
  --pdf-text \
  --min-canonical-bundles 20
```

This gate is renderer-only for cached review artifacts. It checks schema-v3
canonical metadata, registry preference for `printouts/`, checkbox removal, JSON
normalization parity, Markdown parity, and PDF text/page-count parity against the
current main output.

## Status

This workspace currently supports:

- bootstrapping run manifests with baseline and candidate paths
- generating canonical problem-driven printout PDFs
- recording exact prompt captures per source
- promoting accepted candidate PDFs into main output when rerendering is not needed
- renderer-only parity validation between cached review JSON artifacts and main
  PDFs

It does not yet include an automated judge script. For now, review is manual or
ad hoc.
