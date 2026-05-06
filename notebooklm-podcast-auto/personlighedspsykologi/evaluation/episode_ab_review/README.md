# Episode A/B Review Workspace

This folder is the working area for manual and AI-assisted quality checks of
prompt changes across matched before/after episodes.

The intended evaluation flow is:

1. Bootstrap a balanced sample of existing baseline episodes.
2. Transcribe the baseline audio with one fixed STT system.
3. Generate new episodes after prompt changes land.
4. Transcribe the new audio with the same STT system.
5. Compare each matched pair against the source material with the rubric in
   [judge_prompt.md](./judge_prompt.md).

## Folder layout

- `runs/<run-name>/manifest.json`
  The canonical sample manifest for one review run.
- `runs/<run-name>/transcripts/before/`
  Baseline STT transcripts.
- `runs/<run-name>/transcripts/after/`
  Candidate STT transcripts after the new prompts are generated.
- `runs/<run-name>/stt_prompts/before/`
  Captured STT prompts used for baseline transcription.
- `runs/<run-name>/stt_prompts/after/`
  Captured STT prompts used for candidate transcription.
- `runs/<run-name>/prompts/before/`
  Optional resolved prompt captures for the baseline episodes.
- `runs/<run-name>/prompts/after/`
  Optional resolved prompt captures for the candidate episodes.
- `runs/<run-name>/notes/`
  Per-sample manual listening notes.
- `runs/<run-name>/judgments/`
  Per-sample AI comparison reports.

## Bootstrap a run

```bash
python3 notebooklm-podcast-auto/personlighedspsykologi/scripts/bootstrap_episode_ab_review.py \
  --run-name 2026-04-before-baseline \
  --episode-output-root '/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive upload/podcast output personlighedsspyk' \
  --weekly-count 2 \
  --reading-count 2 \
  --slide-count 2 \
  --short-count 2
```

This creates a balanced before-only sample from
`shows/personlighedspsykologi-en/episode_inventory.json` and enriches it with
source context from:

- `shows/personlighedspsykologi-en/reading_summaries.json`
- `shows/personlighedspsykologi-en/weekly_overview_summaries.json`
- `shows/personlighedspsykologi-en/slides_catalog.json`

When `--episode-output-root` is provided, the manifest also records the local
baseline MP3 path for each selected sample when it can be resolved under
`<episode-output-root>/output/W##L#/`.

## Transcribe the baseline set

The recommended first-pass STT backend is ElevenLabs Scribe v2 because the
podcasts have two hosts and Scribe v2 supports speaker diarization.

Requirements:

- `ELEVENLABS_API_KEY`
- `requests` installed in the active environment

Command:

```bash
python3 notebooklm-podcast-auto/personlighedspsykologi/scripts/transcribe_episode_ab_review.py \
  --manifest notebooklm-podcast-auto/personlighedspsykologi/evaluation/episode_ab_review/runs/2026-04-before-baseline/manifest.json \
  --side baseline
```

Behavior:

- ElevenLabs runs on the original local MP3 to preserve audio quality
- `scribe_v2` is called with `diarize=true` and `num_speakers=2`
- keyterms are derived from source filenames, summaries, and key points
- the script writes:
  - speaker-labeled transcript text to `transcripts/<side>/<sample>.txt`
  - plain transcript text to `transcripts/<side>/<sample>.plain.txt`
  - transcript metadata to `transcripts/<side>/<sample>.json`
  - the exact STT prompt to `stt_prompts/<side>/<sample>.txt`
- the manifest is updated with transcription status and provenance fields

OpenAI remains available as a fallback:

```bash
python3 notebooklm-podcast-auto/personlighedspsykologi/scripts/transcribe_episode_ab_review.py \
  --manifest notebooklm-podcast-auto/personlighedspsykologi/evaluation/episode_ab_review/runs/2026-04-before-baseline/manifest.json \
  --side baseline \
  --backend openai
```

OpenAI mode requires `OPENAI_API_KEY`, `ffmpeg`, and `ffprobe`.

## Generate the candidate set

Candidate episodes should be generated into the review run, not into the normal
published output root. Use `--review-manifest` to filter generation to the same
matched samples as the baseline set.

Required before a real candidate run:

- NotebookLM auth/profile must work as usual.
- The default Personlighedspsykologi candidate prompt path now uses the Course
  Understanding context plus compact podcast substrates. Legacy automatic
  meta-prompting is disabled in `prompt_config.json` for this path.
- `GEMINI_API_KEY` or `GOOGLE_API_KEY` is only needed if you intentionally
  re-enable `meta_prompting.automatic` to materialize `*.analysis.md`
  sidecars. In that mode, PDFs are sent directly to Gemini and missing upload
  or processing support is a hard failure.
- Do not paste API keys into committed files. Prefer exporting the key in the
  shell for the current session or loading it from a local secret manager.

Dry-run first:

```bash
python3 notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py \
  --weeks W12L1,W11L2,W10L2,W09L1 \
  --content-types audio \
  --review-manifest notebooklm-podcast-auto/personlighedspsykologi/evaluation/episode_ab_review/runs/2026-04-before-baseline/manifest.json \
  --output-root notebooklm-podcast-auto/personlighedspsykologi/evaluation/episode_ab_review/runs/2026-04-before-baseline/candidate_output \
  --dry-run \
  --print-resolved-prompts \
  --no-print-downloads
```

Expected plan for the current baseline run is eight candidate audio episodes:

- 2 `weekly_readings_only`
- 2 `single_reading`
- 2 `single_slide`
- 2 `short`

Candidate generation is resumable. Existing outputs and request logs are
skipped by default. The wrapper-level `--generator-timeout` defaults to `420`
seconds; if `generate_podcast.py` times out after writing a request log with an
`artifact_id`, `generate_week.py` treats that artifact as queued and continues.

Real generation:

```bash
python3 notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py \
  --weeks W12L1,W11L2,W10L2,W09L1 \
  --content-types audio \
  --review-manifest notebooklm-podcast-auto/personlighedspsykologi/evaluation/episode_ab_review/runs/2026-04-before-baseline/manifest.json \
  --output-root notebooklm-podcast-auto/personlighedspsykologi/evaluation/episode_ab_review/runs/2026-04-before-baseline/candidate_output
```

Then wait/download from the request logs in the candidate output root:

```bash
python3 notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py \
  --weeks W12L1,W11L2,W10L2,W09L1 \
  --content-types audio \
  --output-root notebooklm-podcast-auto/personlighedspsykologi/evaluation/episode_ab_review/runs/2026-04-before-baseline/candidate_output
```

After the MP3 files exist, sync their local paths into the manifest:

```bash
python3 notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_episode_ab_review_candidates.py \
  --manifest notebooklm-podcast-auto/personlighedspsykologi/evaluation/episode_ab_review/runs/2026-04-before-baseline/manifest.json \
  --candidate-output-root notebooklm-podcast-auto/personlighedspsykologi/evaluation/episode_ab_review/runs/2026-04-before-baseline/candidate_output
```

Then transcribe the candidate side with the same STT backend:

```bash
python3 notebooklm-podcast-auto/personlighedspsykologi/scripts/transcribe_episode_ab_review.py \
  --manifest notebooklm-podcast-auto/personlighedspsykologi/evaluation/episode_ab_review/runs/2026-04-before-baseline/manifest.json \
  --side candidate
```

## Judge the matched pairs

Use Gemini to compare each baseline/candidate transcript pair against the
actual source files and the rubric in `judge_prompt.md`.

Requirements:

- `GEMINI_API_KEY` or `GOOGLE_API_KEY`
- `google-genai` installed in the active environment
- all source files referenced by the manifest must resolve locally

Command:

```bash
python3 notebooklm-podcast-auto/personlighedspsykologi/scripts/judge_episode_ab_review.py \
  --manifest notebooklm-podcast-auto/personlighedspsykologi/evaluation/episode_ab_review/runs/2026-04-before-baseline/manifest.json
```

Behavior:

- uploads the relevant source PDFs/slides directly to Gemini
- uses `gemini-3.1-pro-preview` by default
- writes exact judge prompts to `judge_prompts/<sample>.txt`
- writes per-sample reports to `judgments/<sample>.md`
- writes aggregate results to `judgments/SUMMARY.md` and
  `judgments/summary.json`
- updates the manifest with judgment status, model, winner, confidence, and
  report path
- retries transient Gemini failures such as 500/503/429 before marking a sample
  as failed

## Working rule

Do not judge transcript A against transcript B in isolation.
Always compare both against the relevant source files and the episode type:

- `single_reading`: distinctions, argument structure, exam lens
- `single_slide`: lecture reconstruction, sequence logic, critical gaps
- `weekly_readings_only`: cross-reading synthesis, tensions, shared problem
- `short`: compression quality without losing crucial distinctions

## Current status

Current local run:

- `runs/2026-04-before-baseline/` is local and ignored by git.
- Baseline side has 8/8 ElevenLabs Scribe v2 transcripts completed.
- Candidate side has 8/8 generated MP3s and 8/8 ElevenLabs Scribe v2
  transcripts completed.
- Gemini judgment has 8/8 reports completed. All eight samples favored the
  candidate with high confidence in the current run.
