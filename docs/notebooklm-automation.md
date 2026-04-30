# NotebookLM Automation

## Scope

This document covers the repo-level NotebookLM automation layout and the subject wrappers that depend on it.

Current migration program:

- The cross-cutting implementation plan for moving NotebookLM orchestration to a Hetzner-owned queue and moving published audio off Google Drive lives in [notebooklm-queue-r2-migration.md](notebooklm-queue-r2-migration.md).

Current operational note:

- Shared NotebookLM generation now tries to reclaim per-account notebook capacity on `CREATE_NOTEBOOK` failures by deleting the oldest owned notebook on that account and retrying once before profile rotation takes over.

## Layout

- `notebooklm-podcast-auto/personlighedspsykologi/` - Personlighedspsykologi wrapper scripts, docs, tests, and evaluation assets.
- `notebooklm-podcast-auto/bioneuro/` - Bioneuro wrapper scripts and output flow.
- `notebooklm-podcast-auto/notebooklm-py/` - tracked submodule with the underlying client, docs, and test surface.
- `notebooklm_queue/` - queue-core package for the Hetzner migration path: durable job store, state machine, lock handling, and CLI.
- `scripts/notebooklm_queue.py` - local wrapper that re-execs into `.venv` and exposes the queue CLI.

## Primary commands

Personlighedspsykologi:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py --week W01L1 --dry-run
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/sync_reading_summaries.py --validate-only --validate-weekly
```

Bioneuro:

```bash
./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/bioneuro/scripts/generate_week.py --week W1L1 --dry-run
```

## Output and mirrors

Default output roots:

- `notebooklm-podcast-auto/personlighedspsykologi/output`
- `notebooklm-podcast-auto/bioneuro/output`

Mirror helper:

- `scripts/mirror_output_dirs.py`
- `scripts/notebooklm_queue.py`

Examples:

```bash
python3 scripts/mirror_output_dirs.py --subject bioneuro --dry-run
python3 scripts/mirror_output_dirs.py --subject personlighedspsykologi --dry-run
python3 scripts/mirror_output_dirs.py --subject all
```

Pre-push currently mirrors both subjects, but mirror failures are warning-only.

Queue-core note:

- the first queue-core implementation now exists, but it is intentionally only the control-plane foundation
- current scope is durable job persistence, idempotent enqueue, state transitions, show locks, indexes, adapter-based discovery, and a management CLI
- current scope now also includes real queue-owned generate/download execution for supported shows, with per-run manifests and state transitions up to `awaiting_publish`
- current scope now also includes publish-bundle preparation: `prepare-publish` validates the local week output, blocks on leftover request logs or missing required artifacts, persists a publish manifest, and advances successful jobs to `approved_for_publish`
- storage root defaults to `/var/lib/podcasts/notebooklm-queue` and can be overridden with `NOTEBOOKLM_QUEUE_STORAGE_ROOT` or `--storage-root`
- supported discovery adapters currently cover `bioneuro` and `personlighedspsykologi-en`
- `run-dry` resolves the exact generate/download commands for the next queued lecture without touching NotebookLM or publication state
- `run-once` claims or resumes a job, executes the real generate/download wrappers, persists a run manifest under the queue storage root, and moves successful jobs to `awaiting_publish`
- `prepare-publish` claims or resumes a job in `awaiting_publish`, scans the canonical output directory for that lecture, writes a durable publish manifest under the queue storage root, and moves successful jobs to `approved_for_publish`
- object upload, repo metadata rebuild, and Hetzner service deployment still belong to later migration phases

Queue CLI examples:

```bash
./.venv/bin/python scripts/notebooklm_queue.py discover --repo-root . --show-slug bioneuro
./.venv/bin/python scripts/notebooklm_queue.py --storage-root /tmp/notebooklm-queue discover --repo-root . --show-slug bioneuro --enqueue
./.venv/bin/python scripts/notebooklm_queue.py --storage-root /tmp/notebooklm-queue run-dry --repo-root . --show-slug bioneuro
./.venv/bin/python scripts/notebooklm_queue.py --storage-root /tmp/notebooklm-queue run-once --repo-root . --show-slug bioneuro
./.venv/bin/python scripts/notebooklm_queue.py --storage-root /tmp/notebooklm-queue prepare-publish --repo-root . --show-slug bioneuro
```

Important operational note:

- `notebooklm-podcast-auto/personlighedspsykologi/output` must be a real directory, not a macOS Alias file. Alias files break the shared mirror step and create noisy pre-push warnings.
- `scripts/mirror_output_dirs.py` reflects the current local Drive-mount era. It should be treated as transitional infrastructure for subjects that have not yet migrated to object storage.

## Personlighedspsykologi source rules

The canonical reading source is the absolute OneDrive Readings root:

- `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Personlighedspsykologi/Readings`

Relevant sync utilities:

- `scripts/sync_personlighedspsykologi_reading_file_key.py`
- `scripts/sync_personlighedspsykologi_readings_to_droplet.py`
- `notebooklm-podcast-auto/personlighedspsykologi/scripts/migrate_onedrive_sources.py`

## Manual summary policy

Hand-authored summary sources:

- `shows/personlighedspsykologi-en/reading_summaries.json`
- `shows/personlighedspsykologi-en/weekly_overview_summaries.json`

`sync_reading_summaries.py` validates and scaffolds, but it is not the source of final summary prose.

## Related docs

- [../shows/personlighedspsykologi-en/docs/README.md](../shows/personlighedspsykologi-en/docs/README.md)
- [../shows/bioneuro/docs/README.md](../shows/bioneuro/docs/README.md)
- [../notebooklm-podcast-auto/notebooklm-py/docs/README.md](../notebooklm-podcast-auto/notebooklm-py/docs/README.md)
- [README.md](README.md)
