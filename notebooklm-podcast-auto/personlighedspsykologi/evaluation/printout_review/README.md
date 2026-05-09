# Printout Review Workspace

This folder is the sidecar evaluation lane for experimental printout variants.

Its current purpose is to let us generate and inspect problem-driven reading
printouts without touching the canonical printout output tree under:

`notebooklm-podcast-auto/personlighedspsykologi/output/<lecture>/printouts/<source_id>/`

## Current use

The first review track is:

- `problem_driven_v1`

It keeps the intended schema-v3 printout shape, but changes the learner-facing
behavior to emphasize:

- a mission to solve
- a problem map up front
- a self-contained abridged reader
- guided problem-solving from the abridged reader
- recall after the solve phase
- visible progress
- model-building payoffs
- a stronger final challenge

Current render preference for this lane:

- completion markers stay on by default
- `exam_bridge` stays opt-in and is omitted unless the run explicitly enables it

All candidate printouts in this lane must be generated fresh from the source
with the current prompt and engine. Seeded or scaffold-recycled candidate
artifacts are not valid review candidates.

## Why This Lives Here

The production printout path and the experimental printout path are not the
same thing.

For now, this workspace deliberately carries its own experimental printout
engine under `scripts/` so we can test learner-fit changes without turning the
production printout path into a second moving target.

## Folder layout

- `prompts/problem-driven-v1.md`
  The editable prompt overlay for the current experiment.
- `CODEBASE-GUIDE.md`
  Dense architecture guide for coding LLMs working on this workspace.
- `scripts/printout_engine.py`
  The local experimental printout engine used only by this workspace.
- `scripts/bootstrap_run.py`
  Creates a run manifest and review-note skeletons from selected sources.
- `scripts/generate_candidates.py`
  Generates experimental candidate printouts into the shared flat review root.
- `review/`
  Shared user-facing PDF drop zone for all candidate printouts.
- `runs/<run-name>/manifest.json`
  Canonical manifest for one printout review run.
- `runs/<run-name>/notes/`
  Manual review notes for each selected source.
- `runs/<run-name>/prompts/`
  Exact prompt captures used for candidate generation.
- `review/.scaffolding/<source_id>/`
  Hidden per-source JSON and Markdown artifacts used by the shared review root.

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

Internal JSON artifacts live separately under a hidden per-source folder:

- `review/.scaffolding/<source_id>/reading-scaffolds.json`

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
  `review/.scaffolding/<source_id>/rendered_markdown/` area. The shared
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

This is an evaluation path, not the canonical production path.

- do not point candidate output at the canonical live printout root
- compare candidate printouts against the baseline artifacts recorded in the
  manifest
- treat baseline artifacts as comparison material only, never as seed material
- candidate printouts must always be generated fresh from source
- capture exact prompts per run so results are reproducible
- active_reading should solve the reading-guide subproblems with abridged_reader open
- active-reading and consolidation tasks must be solvable from the abridged
  reader alone
- judge learner fit first, not only schema validity

## Status

This workspace currently supports:

- bootstrapping run manifests with baseline and candidate paths
- generating sidecar problem-driven printout candidates
- recording exact prompt captures per source
- keeping all experimental generation code under the review workspace

It does not yet include an automated judge script. For now, review is manual or
ad hoc.
