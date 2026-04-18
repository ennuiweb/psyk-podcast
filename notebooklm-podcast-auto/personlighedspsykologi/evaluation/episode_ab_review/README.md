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

## Working rule

Do not judge transcript A against transcript B in isolation.
Always compare both against the relevant source files and the episode type:

- `single_reading`: distinctions, argument structure, exam lens
- `single_slide`: lecture reconstruction, sequence logic, critical gaps
- `weekly_readings_only`: cross-reading synthesis, tensions, shared problem
- `short`: compression quality without losing crucial distinctions

## Current status

This workspace is intentionally before-first:

- the manifest supports baseline-only episodes now
- candidate fields stay empty until the new episodes exist
- the same manifest can then be completed rather than rebuilt
