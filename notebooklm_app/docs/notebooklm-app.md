# NotebookLM Automation App

The batch script now speaks directly to the NotebookLM Enterprise Discovery Engine API via `gcloud`. It creates notebooks, uploads local files, requests/monitors audio overviews, downloads the resulting audio, and removes every resource afterwards—no `nlm` DevTools cookies required.

## High-level goals

- Provision short-lived notebooks (one per source file) automatically.
- Upload local sources from `notebooklm_app/sources/`, request audio overviews, download the `.wav`, and tear everything down so the next run starts from a clean slate.
- Keep the tooling local and independent from the RSS/Drive pipelines.

## API workflow (`notebooklm_app/scripts/notebooklm_batch.sh`)

1. **Auth once**: run `gcloud auth login --enable-gdrive-access` with the Google identity tied to your NotebookLM Enterprise project. (Optionally run `gcloud auth application-default login --enable-gdrive-access` if you use ADC elsewhere.)
2. **Config**: copy `notebooklm_app/nlm.env.example` → `nlm.env` and set `GCLOUD_PROJECT_NUMBER`, `GCLOUD_LOCATION`, episode focus, language, concurrency, etc.
3. **Sources**: drop `.md`, `.txt`, or other supported documents into `notebooklm_app/sources/`.
4. **Run**: execute `notebooklm_app/scripts/notebooklm_batch.sh`. For each file the script:
   - `POST`s to `.../notebooks` to obtain a fresh `notebookId`;
   - uploads the file via `.../notebooks/<id>/sources:uploadFile` and records the returned `sourceId`;
   - `POST`s to `.../notebooks/<id>/audioOverviews` with your episode focus/language and source ids;
   - polls `GET .../audioOverviews/default` until it exposes a download URL or embedded audio payload, saves the audio under `notebooklm_app/outputs/`, and (by default) converts it to MP3 via `ffmpeg`;
   - `DELETE`s the audio overview, uploaded source, and notebook so every run starts fresh.

`MAX_CONCURRENCY` bounds how many of those jobs run in parallel (default `2`). The log prefix `filename|worker-N` keeps interleaved output readable, and the final summary reports how many jobs succeeded or failed.

## Authentication reminders

- Keep `gcloud auth login --enable-gdrive-access` fresh—the script shells out to `gcloud auth print-access-token` for each API call.
- Set `GCLOUD_PROJECT_NUMBER`, `GCLOUD_LOCATION`, and optionally `GCLOUD_ENDPOINT_LOCATION` in `notebooklm_app/nlm.env` so the script hits the right Discovery Engine host.
- HTTP 401/403 responses usually mean the CLI session expired or you pointed at the wrong project/location; rerun the `gcloud auth` command above and try again.

## Known gaps

- The Discovery Engine API is still `v1alpha`; throttling and transient 5xx responses happen, so the script leans on exponential backoff but can still fail.
- `notebooks.sources.uploadFile` can only ingest one file at a time—batch sources (Docs/Slides/web/video) still require `sources:batchCreate`, which we haven’t automated yet.
