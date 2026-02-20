# Gamifiication

Lean implementation of the **Gamified SRS Pipeline** from `Gamified SRS Pipeline.md`.

## What is implemented
- **Phase 1 (Ingestion)**: source text/PDF -> card extraction (`openai` or `mock`) -> `addNotes` in AnkiConnect.
- **Phase 2 (Sync)**: nightly review count from Anki -> pass/fail evaluation -> Habitica score up/down calls.
- **Phase 3 (Renderer)**: unit mastery state rendering to either HTML (`Jinja2`) or Obsidian Canvas JSON.
- **State model**: local `semester_state.json` as lightweight course state, with Anki as source of truth.

## Files
- `sync.py` - orchestrator CLI.
- `config.py` - typed config loader and validation.
- `anki_client.py` - AnkiConnect API client.
- `habitica_client.py` - Habitica API client.
- `ingest.py` - source parsing + LLM extraction + note payload creation.
- `state.py` - state initialization/merge/status derivation/atomic writes.
- `renderers.py` - HTML and canvas renderers.
- `config.example.json` - starter config.
- `templates/path.html.j2` - default Duolingo-like path template.

## Setup
Use a virtual environment (macOS/Homebrew Python often blocks global `pip install` via PEP 668):
```bash
python3 -m venv .venv
source .venv/bin/activate
```

1. Copy config:
```bash
cp gamifiication/config.example.json gamifiication/config.local.json
```
2. Update:
- `habitica.task_id`
- deck/model/fields/tags if your Anki setup differs.
  - If `habitica.task_id` stays as `REPLACE_*`, Habitica writes are skipped and logged as a sync error.
3. Set env vars:
```bash
export HABITICA_USER_ID="..."
export HABITICA_API_TOKEN="..."
export OPENAI_API_KEY="..."
```
4. Ensure dependencies are installed (`requests` already in repo requirements; add optional ones as needed):
```bash
pip install Jinja2 pypdf
```

## Commands
### 1) Engine smoke test (spec next-step)
```bash
python gamifiication/sync.py --config gamifiication/config.local.json check-anki
```

### 2) Ingest notes
```bash
python gamifiication/sync.py --config gamifiication/config.local.json ingest --input /path/to/source.txt
```

Dry run:
```bash
python gamifiication/sync.py --config gamifiication/config.local.json ingest --input /path/to/source.txt --dry-run
```

Smoke test (no Anki writes, no API key required):
```bash
python gamifiication/sync.py --config gamifiication/config.example.json ingest --provider mock --input \"Gamified SRS Pipeline.md\" --max-cards 2 --dry-run
```

### 3) Run nightly sync
```bash
python gamifiication/sync.py --config gamifiication/config.local.json sync
```

Dry run:
```bash
python gamifiication/sync.py --config gamifiication/config.local.json sync --dry-run
```

### 4) Re-render state manually
```bash
python gamifiication/sync.py --config gamifiication/config.local.json render
```

## Cron at 9:00 PM local time
```cron
0 21 * * * cd /Users/oskar/repo/podcasts && /usr/bin/python3 gamifiication/sync.py --config gamifiication/config.local.json sync >> gamifiication/sync.log 2>&1
```

## Guardrails implemented
- No frontend framework dependency.
- API-only integration points (AnkiConnect + Habitica REST).
- Graceful degradation:
  - If Habitica credentials/API fail, Anki/state still proceed and errors are recorded in `last_sync_errors`.
  - If OpenAI is unavailable, `--provider mock` allows fallback card generation.
  - If renderer fails, sync still completes and records the error.

## Known constraints
- Habitica scoring API supports up/down events, not exact numeric XP/HP writes. This implementation translates review counts to a configurable number of score events.
- PDF extraction requires `pypdf`.
- HTML renderer requires `Jinja2`.

## Troubleshooting
- `error: The 'requests' package is required ...`
  - Install dependencies in the active environment: `pip install -r requirements.txt`.
