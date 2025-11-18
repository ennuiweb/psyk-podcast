# Current Issue Vlog – NotebookLM Batch Script

**Timestamp:** 2025-11-18 10:06 UTC

## Summary
- Verified manually that the NotebookLM Enterprise APIs are healthy by calling them via curl.
- `POST https://global-discoveryengine.googleapis.com/v1alpha/projects/743883644627/locations/global/notebooks` returns the expected JSON, e.g. notebook `50cc637f-0e18-4f44-972d-98433117c5ce`.
- `POST .../notebooks/<id>/sources:uploadFile` also succeeds immediately when targeting that notebook id.

## Implication for the Script
- Failures inside `notebooklm_batch.sh` are not due to API or auth; they stem from how the script captures/parses responses.
- Next work: fix `create_notebook` / `upload_source` logic so they read the body correctly (no more blank JSON or swallowed payloads) and leverage the same endpoints that work via curl.


## Follow-up – 2025-11-18 11:05 UTC
- Confirmed again that both notebook creation and `sources:uploadFile` succeed via curl when using fresh notebook IDs.
- Derived a fool-proof plan: refactor `json_api_request`, `create_notebook`, and `upload_source` to capture/validate API bodies, add guarded JSON parsing with helpful diagnostics, and keep exponential backoff for all HTTP 401/429/5xx responses.
- Next steps are to implement that plan in `notebooklm_batch.sh` so scripted runs match the curl baseline.

### Detailed Fix Plan (carryover)
1. Refactor `json_api_request` to return body via stdout for 2xx responses while preserving status/body/error globals for diagnostics. Log sanitized snippets when non‑2xx and avoid discarding payloads.
2. Harden `create_notebook`: verify `body_starts_with_json`, parse JSON with guarded Python (surface parse errors), keep exponential backoff, and log HTTP status + body snippets for every failure before retrying.
3. Apply the same robustness to `upload_source`: capture bodies, validate JSON before parsing `sourceId`, tighten logging, and reuse the retry/backoff knobs.
4. Improve `request_audio_overview` logging to include HTTP status/body snippets so transient errors are obvious in the logs.
5. Update failure handling in `process_file` to include HTTP status + snippet when notebook creation or source upload fails, and ensure cleanup only runs when resources exist.
6. Validate everything with `MAX_CONCURRENCY=1` after `gcloud auth login --enable-gdrive-access`, watching `notebooklm_app/outputs/notebook_urls.log` to confirm successful notebook IDs.
7. Document the curl sanity checks and new logging behavior in README so future debugging follows the same playbook.

## Resolution – 2025-11-18 12:40 UTC
- Finished the batch-script refactor: `json_api_request` now stores every HTTP body/status/error centrally (and only emits JSON when requested), `create_notebook` consumes that captured body for JSON parsing, and `upload_source` mirrors the same capture/retry semantics so `sourceId` parsing no longer sees blank strings.
- `request_audio_overview`, cleanup helpers, and the `process_file` failure paths now log HTTP codes plus 400-character body snippets for every retryable failure, matching the curl diagnostics gathered earlier.
- Added a README section that explains how to run the manual `curl` notebook + upload sanity checks and clarifies the new logging output, so future debugging sessions can reproduce the same baseline quickly.
