# NotebookLM Flashcard Lab

This workspace is for generating alternative flashcard candidates from processed
`personlighedspsykologi` data. It is deliberately not the canonical Freudd
flashcard source.

The canonical Freudd deck is generated deterministically from:

- `shows/personlighedspsykologi-en/student_synthesis/exam_theory_matrix.json`
- `shows/personlighedspsykologi-en/flashcards/eksamensmatrix-personlighedspsykologi.json`

NotebookLM should only see processed Markdown packs exported from those files.
Do not upload the original student-note PDFs/DOCX files for this workflow.

## Notebook Set

The planned lab uses five notebooks:

- `global-calibration-synthesis`
- `measurement-development-pathology`
- `psychoanalysis-experience-humanism`
- `critical-sociocultural-narrative`
- `oral-exam-comparison-workshop`

The recommended first pilot is `critical-sociocultural-narrative`, because it
stresses the parts of the course where comparison, critique, and exam traps add
the most value.

## Workflow

Export processed packs:

```bash
./.venv/bin/python scripts/export_personlighedspsykologi_notebooklm_flashcard_packs.py --pilot-only
```

Upload the generated Markdown files in the selected `runs/<run-id>/packs/<slug>/`
folder to NotebookLM, generate flashcards there, then download the flashcards as
JSON.

Normalize downloaded NotebookLM output:

```bash
./.venv/bin/python scripts/normalize_personlighedspsykologi_notebooklm_flashcards.py \
  --run-id <run-id> \
  --notebook-slug critical-sociocultural-narrative \
  --input-json <downloaded-flashcards.json>
```

The normalizer writes local candidate JSON and review Markdown under
`runs/<run-id>/candidates/`. Those run outputs are gitignored.

When NotebookLM auth and quota are healthy, the pilot can also be run
end-to-end:

```bash
./.venv/bin/python scripts/run_personlighedspsykologi_notebooklm_flashcard_pilot.py
```

Use `--dry-run` first to inspect the planned NotebookLM commands without
creating a notebook or uploading sources.

## Current Pilot

The first live pilot run is:

- run ID: `pilot-20260525-critical-sociocultural-narrative`
- notebook ID: `6ba89f27-181a-44df-97e2-15f801974bb7`
- raw NotebookLM flashcards: 80
- normalized status counts: 60 `candidate`, 19 `needs_review`, 1
  `auto_rejected`

The run output is local review material and remains ignored by git.

## Review Contract

- Do not import NotebookLM cards directly into Freudd.
- Treat every NotebookLM card as a candidate until reviewed.
- Reject cards that leak student names, local paths, or source-note provenance.
- Reject or edit generic definition cards that do not improve the current deck.
- Keep accepted alternatives in a separate variants deck unless a later task
  explicitly merges them into the canonical matrix deck.
