# Spotify Transcripts Codebase Guide
This guide is for coding LLMs working in `spotify_transcripts/`.
This subsystem is relatively clean compared with other parts of the repo.
Its job is to acquire Spotify episode transcripts, normalize them, and store them as stable repo-side artifacts.

## 1. Business purpose
Some study and content workflows benefit from transcript access.
This package turns Spotify transcript availability into local durable artifacts:
- raw payloads
- normalized JSON
- VTT
- show-level exports
- verification reports

It is not part of feed publication directly.
It is an acquisition and normalization subsystem.

## 2. Directory structure
Important files:
- `cli.py`
- `service.py`
- `discovery.py`
- `playwright_client.py`
- `normalizer.py`
- `store.py`
- `exporter.py`
- `verifier.py`
- `models.py`
- `paths.py`

## 3. Operator entrypoint
Source: `spotify_transcripts/cli.py`

This is a clean CLI surface and a good place to start.

Snippet:
```python
# spotify_transcripts/cli.py
from .service import build_show_queue, run_show_queue, sync_show_transcripts
from .store import TranscriptStore
from .verifier import verify_show_transcripts
```

Supported commands:
- `login`
- `auth-status`
- `report`
- `queue-build`
- `queue-report`
- `queue-run`
- `export-show`
- `verify-show`
- `sync`

This package is easier to reason about than the queue or feed layers because the command surface is comparatively coherent.

## 4. Discovery
Source: `spotify_transcripts/discovery.py`

Discovery maps repo-side show metadata into transcript acquisition sources.
It primarily combines:
- `shows/<show>/episode_inventory.json`
- `shows/<show>/spotify_map.json`

This produces per-episode `EpisodeSource` objects with:
- episode key
- title
- Spotify URL
- Spotify episode ID

If a show has missing mappings, downstream acquisition will block correctly, but the root cause is here.

## 5. Orchestration
Source: `spotify_transcripts/service.py`

This file contains the real sync logic.

Snippet:
```python
# spotify_transcripts/service.py
def sync_show_transcripts(...):
    ...
    entry, outcome = process_episode_source(...)
    ...
    store.save_manifest(...)
```

Core responsibilities:
- process one episode source
- retry acquisition
- normalize successful payloads
- persist manifest state
- build and run local queues

This is the first file to inspect when behavior is wrong but Playwright itself appears healthy.

## 6. Per-episode processing
`process_episode_source(...)` is the central unit of work.
It handles:
- missing mapping
- skip already-downloaded behavior
- retries
- raw payload write
- normalization
- VTT write
- failure accounting

This function is the schema and state firewall for the subsystem.

## 7. Playwright boundary
Source: `spotify_transcripts/playwright_client.py`

This file automates the real web interaction:
- persistent browser profile
- login storage state
- transcript acquisition
- auth/market/no-transcript/network classification

This is intentionally separate from orchestration.
If the browser interaction breaks, debug here before touching `service.py`.

## 8. Normalization firewall
Source: `spotify_transcripts/normalizer.py`

This file protects the rest of the repo from Spotify payload drift.

It turns raw Spotify transcript payloads into:
- normalized JSON
- normalized segment structure
- VTT text

If Spotify changes their payload shape, `TranscriptSchemaError` should be raised here rather than allowing malformed downstream state.

That is the correct design.
Preserve it.

## 9. Durable storage
Source: `spotify_transcripts/store.py`

This file is clean and important.
It owns show-local artifact layout, typically under:
- `spotify_transcripts/raw/`
- `spotify_transcripts/normalized/`
- `spotify_transcripts/vtt/`
- `spotify_transcripts/exports/`
- `manifest.json`
- `queue.json`

It uses atomic write patterns.
That makes it safer than several other file-heavy subsystems in the repo.

## 10. Export and verify
Sources:
- `exporter.py`
- `verifier.py`

`exporter.py` combines normalized transcripts into a show-level deliverable.
`verifier.py` checks integrity/completeness for one show.

These are downstream of acquisition and normalization.
If they fail, do not immediately assume acquisition failed; inspect normalized artifacts first.

## 11. Call chain: full sync
Typical flow:
1. `cli.py:main`
2. `discovery.load_show_sources(...)`
3. `service.sync_show_transcripts(...)`
4. `process_episode_source(...)`
5. `playwright_client.download_episode_transcript(...)`
6. `normalizer.normalize_transcript_payload(...)`
7. `store.write_*` and `store.save_manifest(...)`

This chain is straightforward and should stay that way.

## 12. Common failure classes
- missing Spotify map entry
- login/auth state expired
- no transcript exists for an episode
- market restrictions
- Spotify payload schema drift
- Playwright/browser dependency issue

This subsystem is comparatively robust because those cases are explicitly classified.

## 13. Non-idiomatic or noteworthy traits
- persistent browser profile is part of the product contract
- queue and manifest are file-backed, not DB-backed
- schema drift is treated as a first-class failure mode
- some status behavior is encoded as named constants rather than richer state objects

These are acceptable tradeoffs here.

## 14. Safe change strategy
When changing this subsystem:
1. identify whether the issue is mapping, browser auth, transcript fetch, normalization, or storage
2. preserve schema-firewall behavior in `normalizer.py`
3. preserve manifest semantics in `store.py`
4. keep `service.py` orchestration logic explicit, not magical

If you are unsure where to start, start with `cli.py`, then `service.py`, then `playwright_client.py` or `normalizer.py` depending on failure type.

