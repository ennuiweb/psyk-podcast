# Podcast Tools Codebase Guide
This guide is for coding LLMs working in `podcast-tools/`.
This directory contains the feed and media toolchain that turns generated audio plus show config into publishable podcast outputs.

## 1. Business purpose
`podcast-tools/` is the publication-format layer for the repo.
It takes generated audio and supporting metadata and turns them into:
- RSS feeds
- episode inventory files
- quiz-link sidecars
- media uploads/ingest flows
- Drive/R2 storage interactions

If `notebooklm_queue/` decides what to publish, `podcast-tools/` decides how those published artifacts are represented and exposed.

## 2. Directory structure
Important files:
- `gdrive_podcast_feed.py`
- `storage_backends.py`
- `sync_drive_quiz_links.py`
- `transcode_drive_media.py`
- `ingest_manifest_to_drive.py`
- `show_config_policy.py`
- `tests/`

## 3. The file you should fear first
Source: `podcast-tools/gdrive_podcast_feed.py`

Despite the name, this file is much larger than “generate a feed”.
It owns a surprising amount of business logic:
- inventory assembly
- feed XML generation
- public URL handling
- content filtering
- summary/quiz block injection
- category and title formatting
- regeneration identity integration
- publication-state carry-forward
- sorting rules
- tail bundle synthesis

Snippet:
```python
# podcast-tools/gdrive_podcast_feed.py
from regeneration_identity import logical_episode_id
from storage_backends import build_storage_backend, resolve_storage_provider
```

That import pair is revealing.
This file sits at the intersection of:
- naming identity rules
- storage provider abstraction
- publication formatting

It is a high-risk integration hub.

## 4. Storage abstraction
Source: `podcast-tools/storage_backends.py`

This file is one of the cleanest in the directory.
It provides a real abstraction boundary.

Snippet:
```python
# podcast-tools/storage_backends.py
class StorageBackend(Protocol):
    provider: str
    def list_media_files(...): ...
    def build_folder_path(...): ...
    def ensure_public_access(...): ...
    def build_public_url(...): ...
```

Concrete implementations:
- `DriveStorageBackend`
- `R2StorageBackend`

This is where provider branching should happen.
If you find Drive/R2 conditionals leaking elsewhere, that is a code smell.

## 5. Config-driven provider selection
Also in `storage_backends.py`:
```python
def build_storage_backend(config: Dict[str, Any]) -> StorageBackend:
    provider = resolve_storage_provider(config)
    if provider == "drive":
        return DriveStorageBackend(config)
    if provider == "r2":
        return R2StorageBackend(config)
```

This is one of the core contracts between `shows/<show>/config*.json` and the toolchain.
If provider resolution changes, many scripts are affected.

## 6. Why `gdrive_podcast_feed.py` is error-prone
It mixes:
- transport concerns
- filename parsing
- feed formatting
- show-specific config interpretation
- doc/summary heuristics
- publication policy

This is not an idiomatic small-module design.
It works, but it creates a large blast radius for changes.

Typical regression pattern:
- you change a naming rule for titles
- this silently changes filtering, quiz links, or inventory ordering downstream

## 7. Quiz-link sync
Source: `podcast-tools/sync_drive_quiz_links.py`

This script recursively walks Drive and produces `quiz_links.json`.
It relies heavily on filename conventions and fallback derivation logic.

That means quiz-link bugs are often naming bugs, not API bugs.

## 8. Media transcode
Source: `podcast-tools/transcode_drive_media.py`

This script handles:
- source media discovery
- ffmpeg transcode
- target format normalization
- Drive-side upload/update behavior

It is operationally important because later feed logic assumes media has already been normalized into allowed output formats.

## 9. Manifest ingest
Source: `podcast-tools/ingest_manifest_to_drive.py`

This is the inverse-ish path:
manifest-driven upload into Drive plus metadata recording.
When uploads and feed inventory disagree, inspect this script and the storage backend before touching feed rendering.

## 10. Show config policy shim
Source: `podcast-tools/show_config_policy.py`

This file is small but important.
It extracts policy information from show config for CI/workflow use:
- storage provider
- publication owner
- output variables

This is a “small file with high leverage” because multiple automation layers trust it.

## 11. Call chain: typical feed rebuild
The typical flow is:
1. a show config is loaded
2. `build_storage_backend(...)` resolves Drive or R2
3. media inventory is listed and normalized
4. filtering/sorting/summary enrichment is applied
5. RSS XML and inventory JSON are written

When debugging a bad feed, walk that chain in order.

## 12. The data model is partly in filenames
This subsystem relies heavily on:
- config tags embedded in names
- filename prefixes/suffixes
- regex classification
- title block conventions

That is one of the least idiomatic parts of the repo.
It is not accidental.
It is how the system maps generated audio back to lecture/source semantics.

So:
- do not “clean up” naming logic casually
- do not normalize titles without checking filter/identity effects

## 13. Common failure classes
- wrong provider chosen from config
- public URL construction mismatch
- feed item ordering drift
- title formatting regression
- doc/summary block misattachment
- quiz-link resolution drift
- inventory/feed disagreement after upload state changes

## 14. Safe change strategy
When changing `podcast-tools/`:
1. identify whether the bug is storage, inventory, formatting, or naming
2. inspect `storage_backends.py` first for provider concerns
3. treat `gdrive_podcast_feed.py` as a monolith with hidden coupling
4. preserve existing filename contracts unless all dependent tools are updated
5. test both JSON inventory and final RSS behavior mentally

If you are unsure where to start, start with `gdrive_podcast_feed.py` for output bugs and `storage_backends.py` for provider bugs.

