# NotebookLM Automation App

The batch script now speaks directly to the NotebookLM Enterprise Discovery Engine API via `gcloud`. It creates notebooks, uploads local files, requests audio overviews, and records clickable NotebookLM URLs so you can open each job manually—no `nlm` DevTools cookies required.

## High-level goals

- Provision short-lived notebooks (one per source file) automatically.
- Upload local sources from `notebooklm_app/sources/`, request audio overviews, and log the resulting NotebookLM URLs so you can listen/review directly in the UI.
- Keep the tooling local and independent from the RSS/Drive pipelines.

## API workflow (`notebooklm_app/scripts/notebooklm_batch.sh`)

1. **Auth once**: run `gcloud auth login --enable-gdrive-access` with the Google identity tied to your NotebookLM Enterprise project. (Optionally run `gcloud auth application-default login --enable-gdrive-access` if you use ADC elsewhere.)
2. **Config**: copy `notebooklm_app/nlm.env.example` → `nlm.env` and set `GCLOUD_PROJECT_NUMBER`, `GCLOUD_LOCATION`, episode focus, language, concurrency, etc.
3. **Sources**: drop `.md`, `.txt`, or other supported documents into `notebooklm_app/sources/`.
4. **Run**: execute `notebooklm_app/scripts/notebooklm_batch.sh`. For each file the script:
   - `POST`s to `.../notebooks` (per the [Create notebooks API](https://docs.cloud.google.com/gemini/enterprise/notebooklm-enterprise/docs/api-notebooks)) to obtain a fresh `notebookId`;
   - uploads the file via `.../notebooks/<id>/sources:uploadFile` and records the returned `sourceId`;
   - `POST`s to `.../notebooks/<id>/audioOverviews` with your episode focus/language and source ids;
   - assembles `https://notebooklm.cloud.google.com/<location>/notebook/<id>?project=<project>` links and appends them to `notebooklm_app/outputs/notebook_urls.log` so you can click straight into each notebook to download/listen to the audio.
   - Optionally `DELETE`s the audio overview, uploaded source, and notebook if you launch the script with `AUTO_CLEANUP=1` (the default leaves notebooks intact so you can review them).

`MAX_CONCURRENCY` bounds how many of those jobs run in parallel (default `2`). The log prefix `filename|worker-N` keeps interleaved output readable, and the final summary reports how many jobs succeeded or failed. Notebook creation, source uploads, and audio overview requests each include exponential backoff plus response-snippet logging so transient API errors (401/429/5xx) are retried automatically before surfacing as failures.

## Authentication reminders

- Keep `gcloud auth login --enable-gdrive-access` fresh—the script shells out to `gcloud auth print-access-token` for each API call.
- Set `GCLOUD_PROJECT_NUMBER`, `GCLOUD_LOCATION`, and optionally `GCLOUD_ENDPOINT_LOCATION` in `notebooklm_app/nlm.env` so the script hits the right Discovery Engine host.
- HTTP 401/403 responses usually mean the CLI session expired or you pointed at the wrong project/location; rerun the `gcloud auth` command above and try again.

## Known gaps

- Audio downloads still require the NotebookLM UI; the script only logs clickable notebook URLs until the API exposes a `download` method.
- The Discovery Engine API is still `v1alpha`; throttling and transient 5xx responses happen, so the script leans on exponential backoff but can still fail.
- `notebooks.sources.uploadFile` can only ingest one file at a time—batch sources (Docs/Slides/web/video) still require `sources:batchCreate`, which we haven’t automated yet.
