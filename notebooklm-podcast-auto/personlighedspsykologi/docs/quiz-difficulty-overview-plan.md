# Easy Overview Plan: Easy, Medium, Hard Quizzes

## Goal
Generate `easy`, `medium`, and `hard` quiz HTML files for all English audio episodes in `notebooklm-podcast-auto/personlighedspsykologi/output`, while keeping the existing `shows/personlighedspsykologi-en` flow stable.

## Current baseline (2026-02-18)
- Audio episodes in output (`*.mp3` with `type=audio`): `82`
- Quiz HTML files in output (`*.html` with `type=quiz`): `8`
- Existing quiz difficulty coverage: `medium` only
- Lecture folders present: `W1L1` through `W12L1` (22 `W#L#` folders total)

## Scope
- In scope:
  - Add missing quiz outputs for all existing audio episodes.
  - Use the same generation/download/sync workflow already used for `shows/personlighedspsykologi-en`.
  - Keep filename config tags (`difficulty=easy|medium|hard`) for traceability.
- Out of scope (v1):
  - Changing feed descriptions to show 3 quiz URLs per episode.
  - Replacing current single-link `quiz_links.json` schema.

## Plan
1. Set `quiz.difficulty` to `all` in prompt config.
2. Generate quiz requests for every `W#L#` folder in one pass.
3. Download all quiz HTML artifacts.
4. Validate coverage (`audio count == quiz count`) per difficulty.
5. Keep feed mapping stable on `medium` (same behavior as today).
6. Optionally add easy/hard mappings in separate files as a follow-up.

## Execution commands
Run from repo root.

### 1) Set multi-difficulty generation
In `notebooklm-podcast-auto/personlighedspsykologi/prompt_config.json`:
- `quiz.difficulty: "all"`

### 2) Resolve lecture list from current output
```bash
LECTURES=$(find notebooklm-podcast-auto/personlighedspsykologi/output -maxdepth 1 -type d -name 'W*L*' -exec basename {} \; | sort -V | paste -sd, -)
echo "$LECTURES"
```

### 3) Generate quiz artifacts for all difficulties
```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py \
  --weeks "$LECTURES" \
  --content-types quiz \
  --profile default
```

### 4) Download quiz HTML files
```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py \
  --weeks "$LECTURES" \
  --content-types quiz \
  --format html
```

### 5) Validate coverage by difficulty
```bash
python3 - <<'PY'
from pathlib import Path

root = Path("notebooklm-podcast-auto/personlighedspsykologi/output")
audio = [p for p in root.rglob("*.mp3") if "type=audio" in p.name and "[EN]" in p.name]
print("audio_expected", len(audio))
for level in ("easy", "medium", "hard"):
    quizzes = [p for p in root.rglob("*.html") if "type=quiz" in p.name and f"difficulty={level}" in p.name and "[EN]" in p.name]
    print(level, len(quizzes))
PY
```

## Mapping and feed compatibility (same as `shows/personlighedspsykologi-en`)
- Current `quiz_links.json` supports one quiz URL per audio file.
- Keep that file on `medium` in v1 to avoid feed behavior changes.
- Use difficulty filtering when syncing links (implemented):
  - `python3 scripts/sync_quiz_links.py --quiz-difficulty medium --dry-run`
  - `python3 scripts/sync_quiz_links.py --quiz-difficulty medium`
- Optional follow-up: generate `quiz_links_easy.json` and `quiz_links_hard.json` for external UI usage.

## Done criteria
- `easy`, `medium`, and `hard` HTML quiz files exist for every English `type=audio` episode.
- Coverage check reports equal counts per difficulty.
- `shows/personlighedspsykologi-en/quiz_links.json` remains stable and medium-based.
- Existing feed generation command still works unchanged:
  - `python3 podcast-tools/gdrive_podcast_feed.py --config shows/personlighedspsykologi-en/config.local.json`
