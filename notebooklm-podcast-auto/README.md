# NotebookLM Auto Podcast

This folder automates podcast generation using `notebooklm-py` and a small wrapper script.

## Setup

1. Create a virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies from the local clone in `./notebooklm-py`.

```bash
pip install -r requirements.txt
playwright install chromium
```

3. Authenticate once (opens a browser).

```bash
notebooklm login
```

If you need multiple accounts, save separate storage files:

```bash
notebooklm login --storage ~/.notebooklm/work_storage_state.json
notebooklm login --storage ~/.notebooklm/personal_storage_state.json
```

## Run

Provide sources by URL or file path. Use `sources.txt` for batches.
By default, the script starts generation and exits (non-blocking). Use `--wait` to block and download the MP3.
Use `--skip-existing` to avoid re-generating an MP3 if the output file already exists.
When `--reuse-notebook` is used, the script skips re-uploading sources that already exist in the notebook.
If artifact generation fails, a `.request.error.json` is written next to the output (no request log is created).

```bash
python3 generate_podcast.py --sources-file sources.txt --notebook-title "Auto Podcast" --output output/podcast.mp3 --wait
```

## Sources File Format

One entry per line. Blank lines and lines starting with `#` are ignored.

Valid forms:

- `url:https://example.com/article`
- `file:/absolute/path/to/doc.pdf`
- `text:Title|Content`
- Bare URL or file path (auto-detected)

## Examples

```bash
python3 generate_podcast.py \
  --source https://en.wikipedia.org/wiki/Artificial_intelligence \
  --instructions "make it engaging" \
  --audio-format deep-dive \
  --audio-length default \
  --output output/ai-podcast.mp3 \
  --wait
```

## Notes

- Auth data is stored under `~/.notebooklm/` unless you pass `--storage`.
- If generation fails due to rate limits, wait a few minutes and re-run.

## Profiles

You can use named auth profiles instead of passing `--storage` every time.
Create a `profiles.json` that maps profile names to storage files (a starter is in `profiles.json`).
By default, the script looks for `profiles.json` in the current directory, then next to `generate_podcast.py`.
Use `--profiles-file` to point to a custom location.
If the `profiles.json` contains `default` (or only one profile), it will be auto-selected when no profile is passed.

Example `profiles.json` (see `profiles.json.example`):

```json
{
  "work": "/Users/you/.notebooklm/work_storage_state.json",
  "personal": "/Users/you/.notebooklm/personal_storage_state.json"
}
```

Usage:

```bash
python3 generate_podcast.py --profile work --sources-file sources.txt --output output/work.mp3 --wait
python3 generate_podcast.py --profiles-file /path/to/profiles.json --profile personal --output output/personal.mp3 --wait
```

List profiles:

```bash
python3 generate_podcast.py --list-profiles
python3 generate_podcast.py --profiles-file /path/to/profiles.json --list-profiles
```

Notes:
- `--storage` takes precedence and cannot be combined with `--profile`.

## Non-Blocking Flow

Default behavior returns immediately with a `task_id` (artifact ID). Use the CLI to wait and download later:

```bash
# Start generation (no wait, returns immediately)
python3 generate_podcast.py --sources-file sources.txt --notebook-title "Auto Podcast"

# Wait for completion and download
notebooklm artifact wait <task_id> -n <notebook_id>
notebooklm download audio output/podcast.mp3 -a <task_id> -n <notebook_id>
```

Polling options:
- `--initial-interval SECONDS` (preferred)
- `--poll-interval` is deprecated (kept for compatibility)

The non-blocking run writes a request log next to the output:
`output/podcast.mp3.request.json` with `notebook_id`, `artifact_id`, and resolved auth metadata (`auth`).
Failed runs write `output/podcast.mp3.request.error.json`.

## Troubleshooting

- `Storage file not found: ~/.notebooklm/storage_state.json` means you need to run `notebooklm login` or pass `--storage` to a valid file.
- If audio generation fails with `No artifact id returned`, rerun with `NOTEBOOKLM_LOG_LEVEL=DEBUG` to see the underlying RPC error or quota/rate-limit message.
