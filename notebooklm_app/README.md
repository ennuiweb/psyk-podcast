# NotebookLM automation (gcloud API)

https://docs.cloud.google.com/gemini/enterprise/notebooklm-enterprise/docs/api-notebooks-sources

Notebook provisioning, source uploads, audio overview creation, and cleanup now run entirely through the NotebookLM Enterprise Discovery Engine REST API using `gcloud` access tokens. All you need is a configured Google Cloud project with NotebookLM Enterprise enabled plus local text/markdown sources—the bash script handles every notebook/source/audio lifecycle call in one pass.

## Quick start

1. **Install and authenticate gcloud**
   ```bash
   brew install --cask google-cloud-sdk   # or download from cloud.google.com/sdk
   gcloud components install beta alpha  # optional but keeps CLI tooling complete
   gcloud auth login --enable-gdrive-access
   ```
   Use the same Google account that has NotebookLM Enterprise access. `--enable-gdrive-access` is required if you plan to upload Google Docs/Slides later via `sources:batchCreate`.
2. **Create an env file**
   - Copy `notebooklm_app/nlm.env.example` to `notebooklm_app/nlm.env` (or export `NOTEBOOKLM_ENV`).
   - Fill in `GCLOUD_PROJECT_NUMBER`, `GCLOUD_LOCATION`, optional `GCLOUD_ENDPOINT_LOCATION`, and tune episode focus, poll intervals, concurrency, etc.
3. **Load sources**
   - Drop `.md`, `.txt`, or any supported document into `notebooklm_app/sources/`.
4. **Run the batch script**
   ```bash
   notebooklm_app/scripts/notebooklm_batch.sh
   ```
   The script POSTs to the NotebookLM Enterprise API to create notebooks, uploads each local file via `notebooks.sources.uploadFile`, requests an audio overview, and logs a clickable NotebookLM URL for each job inside `notebooklm_app/outputs/notebook_urls.log` so you can open the generated overviews manually.

## Requirements

- [`gcloud`](https://cloud.google.com/sdk/docs/install) authenticated against the Google Cloud project that hosts NotebookLM Enterprise (run `gcloud auth login --enable-gdrive-access`).
- `bash`, `curl`, `file`, and `awk` on macOS/Linux (part of the stock developer toolchain).
- `python3` (or `python`) for building JSON payloads, parsing status responses, and writing the notebook URL log.
- Optional: `UPLOAD_MIME_OVERRIDE` in `nlm.env` if you need to force a MIME type when uploading unusual extensions.

## Script internals

- For each source the script executes the following pipeline:
  1. `POST https://${GCLOUD_ENDPOINT_LOCATION}-discoveryengine.googleapis.com/${GCLOUD_DISCOVERY_API_VERSION}/projects/${GCLOUD_PROJECT_NUMBER}/locations/${GCLOUD_LOCATION}/notebooks` (per the [Create notebooks API](https://docs.cloud.google.com/gemini/enterprise/notebooklm-enterprise/docs/api-notebooks)) → capture the returned `notebookId`.
  2. `POST https://${GCLOUD_ENDPOINT_LOCATION}-discoveryengine.googleapis.com/upload/${GCLOUD_DISCOVERY_API_VERSION}/projects/${GCLOUD_PROJECT_NUMBER}/locations/${GCLOUD_LOCATION}/notebooks/<id>/sources:uploadFile` (with `--data-binary @file`) → upload the local markdown/text file and record the `sourceId`.
  3. `POST https://${GCLOUD_ENDPOINT_LOCATION}-discoveryengine.googleapis.com/${GCLOUD_DISCOVERY_API_VERSION}/projects/${GCLOUD_PROJECT_NUMBER}/locations/${GCLOUD_LOCATION}/notebooks/<id>/audioOverviews` with `generationOptions` (source IDs + episode focus + language) → kick off the audio overview job.
  4. Generate a UI URL of the form `https://notebooklm.cloud.google.com/<location>/notebook/<id>?project=<project>` and append it to `notebooklm_app/outputs/notebook_urls.log` so you can open each overview manually once NotebookLM finishes rendering the audio.
  5. Optionally `DELETE` the default audio, uploaded sources, and notebook if you set `AUTO_CLEANUP=1`; by default, notebooks remain available for manual review.
- Google hasn't exposed an audio download endpoint yet, so the log file is the hand-off: click through each entry to preview or export the audio within the NotebookLM UI.
- Jobs run through a bounded worker pool (`MAX_CONCURRENCY`, default `2`). Each worker prefixes log lines with `<filename>|worker-N`, which keeps interleaved output readable.
- Notebook creation, source uploads, and audio overview requests all include exponential backoff and response-snippet logging so transient `401/429/50x` errors are retried automatically before surfacing as failures.
- Every API call includes `gcloud auth print-access-token` output inline; if auth fails, the logs explain which `gcloud auth` command to rerun.

## Configuration knobs (`nlm.env`)

| Variable | Default | Purpose |
| --- | --- | --- |
| `SOURCES_DIR` / `OUTPUT_DIR` | `notebooklm_app/sources` / `notebooklm_app/outputs` | Input/output locations |
| `NOTEBOOK_TITLE_PREFIX` | `NotebookLM Batch` | Prepended to every temp notebook title |
| `EPISODE_FOCUS` / `LANGUAGE_CODE` | See example | Passed to the Discovery Engine API as `episodeFocus` and `languageCode` |
| `GCLOUD_PROJECT_NUMBER` / `GCLOUD_LOCATION` | _required_ | NotebookLM Enterprise project + region used for audio requests |
| `GCLOUD_ENDPOINT_LOCATION` | inherits `GCLOUD_LOCATION` | Hostname prefix for `*-discoveryengine.googleapis.com` (override if the endpoint differs from the region) |
| `GCLOUD_DISCOVERY_API_VERSION` | `v1alpha` | Discovery Engine API version path segment |
| `GCLOUD_ACCESS_TOKEN_CMD` | `gcloud auth print-access-token` | Override if you need a custom token minting command |
| `GCLOUD_AUTHUSER` | empty | Optional `authuser` query parameter appended to NotebookLM URLs |
| `MAX_CONCURRENCY` | `2` | Number of notebooks processed in parallel |
| `NOTEBOOK_URL_LOG` | `notebooklm_app/outputs/notebook_urls.log` | File that receives the clickable NotebookLM links |
| `AUTO_CLEANUP` | `0` | Set to `1` to delete notebooks/sources/audio after logging |
| `NOTEBOOK_CREATE_MAX_RETRIES` / `NOTEBOOK_CREATE_RETRY_DELAY` / `NOTEBOOK_CREATE_RETRY_BACKOFF` | `4 / 5 / 2` | Exponential backoff settings for the notebook creation API |
| `SOURCE_UPLOAD_MAX_RETRIES` / `SOURCE_UPLOAD_RETRY_DELAY` / `SOURCE_UPLOAD_RETRY_BACKOFF` | `4 / 5 / 2` | Exponential backoff settings for file uploads |
| `AUDIO_CREATE_MAX_RETRIES` / `AUDIO_CREATE_RETRY_DELAY` / `AUDIO_CREATE_RETRY_BACKOFF` | `4 / 5 / 2` | Controls retries when calling the audio overview API |
| `UPLOAD_MIME_OVERRIDE` | empty | Force a MIME type when calling `notebooks.sources.uploadFile` |
| `PYTHON_BIN` | `python3` | Override if `python3` lives elsewhere or under a different name |

## Authentication notes

- Run `gcloud auth login --enable-gdrive-access` with the Google identity that owns the NotebookLM Enterprise project. This authorises both the Discovery Engine API and optional Drive-backed content.
- If you rely on Application Default Credentials elsewhere, `gcloud auth application-default login --enable-gdrive-access` keeps ADC in sync with the same account.
- `notebooklm_app/nlm.env` (or `NOTEBOOKLM_ENV`) should define `GCLOUD_PROJECT_NUMBER`, `GCLOUD_LOCATION`, and optionally `GCLOUD_ENDPOINT_LOCATION` so the script can build the proper Discovery Engine URLs.
- Every API call shells out to `gcloud auth print-access-token` (or your custom `GCLOUD_ACCESS_TOKEN_CMD`), so keep the CLI session fresh if you see HTTP 401/403 responses.

## Debugging and curl sanity checks

- When diagnosing failures, first run the same Notebook + upload API calls via `curl` to confirm the backend is healthy. This isolates environment/auth issues from bash bugs.
- Notebook creation check:
  ```bash
  TOKEN="$(gcloud auth print-access-token)"
  curl -sS -X POST "https://${GCLOUD_ENDPOINT_LOCATION}discoveryengine.googleapis.com/${GCLOUD_DISCOVERY_API_VERSION}/projects/${GCLOUD_PROJECT_NUMBER}/locations/${GCLOUD_LOCATION}/notebooks" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"title":"debug notebook"}'
  ```
- Source upload check (replace `NOTEBOOK_ID` with the ID returned above):
  ```bash
  curl -sS -X POST --data-binary @path/to/file.md \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "X-Goog-Upload-File-Name: file.md" \
    -H "X-Goog-Upload-Protocol: raw" \
    -H "Content-Type: text/markdown" \
    "https://${GCLOUD_ENDPOINT_LOCATION}discoveryengine.googleapis.com/upload/${GCLOUD_DISCOVERY_API_VERSION}/projects/${GCLOUD_PROJECT_NUMBER}/locations/${GCLOUD_LOCATION}/notebooks/${NOTEBOOK_ID}/sources:uploadFile"
  ```
- `notebooklm_batch.sh` echoes the HTTP status and a 400-character snippet from the API body whenever an API call fails or returns malformed JSON, so your terminal output now mirrors whatever `curl` showed.
