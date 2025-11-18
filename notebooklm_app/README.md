# NotebookLM automation (gcloud API)

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
   The script POSTs to the NotebookLM Enterprise API to create notebooks, uploads each local file via `notebooks.sources.uploadFile`, requests an audio overview, polls the default audio resource until it supplies a download URL/embedded payload, and tears everything down when finished.

## Requirements

- [`gcloud`](https://cloud.google.com/sdk/docs/install) authenticated against the Google Cloud project that hosts NotebookLM Enterprise (run `gcloud auth login --enable-gdrive-access`).
- `bash`, `curl`, `file`, and `awk` on macOS/Linux (part of the stock developer toolchain).
- `python3` (or `python`) for building JSON payloads and parsing status responses.
- [`ffmpeg`](https://ffmpeg.org/) for the optional WAV→MP3 conversion (set `OUTPUT_AUDIO_FORMAT=wav` to skip).
- Optional: `UPLOAD_MIME_OVERRIDE` in `nlm.env` if you need to force a MIME type when uploading unusual extensions.

## Script internals

- For each source the script executes the following pipeline:
  1. `POST https://${GCLOUD_ENDPOINT_LOCATION}-discoveryengine.googleapis.com/${GCLOUD_DISCOVERY_API_VERSION}/projects/${GCLOUD_PROJECT_NUMBER}/locations/${GCLOUD_LOCATION}/notebooks` → capture the returned `notebookId`.
  2. `POST https://${GCLOUD_ENDPOINT_LOCATION}-discoveryengine.googleapis.com/upload/${GCLOUD_DISCOVERY_API_VERSION}/projects/${GCLOUD_PROJECT_NUMBER}/locations/${GCLOUD_LOCATION}/notebooks/<id>/sources:uploadFile` (with `--data-binary @file`) → upload the local markdown/text file and record the `sourceId`.
  3. `POST https://${GCLOUD_ENDPOINT_LOCATION}-discoveryengine.googleapis.com/${GCLOUD_DISCOVERY_API_VERSION}/projects/${GCLOUD_PROJECT_NUMBER}/locations/${GCLOUD_LOCATION}/notebooks/<id>/audioOverviews` with the selected `sourceIds`, episode focus, and language → kick off the audio overview job.
  4. Poll `GET https://${GCLOUD_ENDPOINT_LOCATION}-discoveryengine.googleapis.com/${GCLOUD_DISCOVERY_API_VERSION}/projects/${GCLOUD_PROJECT_NUMBER}/locations/${GCLOUD_LOCATION}/notebooks/<id>/audioOverviews/default` until it exposes a download URL or embedded audio payload, fetch the audio file into `outputs/<filename>.wav`, and optionally convert it to MP3 via `ffmpeg` (controlled by `OUTPUT_AUDIO_FORMAT`, `MP3_BITRATE`, and `KEEP_WAV`).
  5. `DELETE` the default audio, uploaded sources, and notebook so each run leaves the environment clean.
- Jobs run through a bounded worker pool (`MAX_CONCURRENCY`, default `2`). Each worker prefixes log lines with `<filename>|worker-N`, which keeps interleaved output readable.
- `POLL_INTERVAL` and `POLL_TIMEOUT` control how frequently we retry `GET .../audioOverviews/default`. Set `POLL_TIMEOUT=0` to wait indefinitely for very long generations.
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
| `MAX_CONCURRENCY` | `2` | Number of notebooks processed in parallel |
| `OUTPUT_AUDIO_FORMAT` | `mp3` | Use `wav` to skip ffmpeg conversion |
| `MP3_BITRATE` | `128k` | Bitrate for MP3 exports |
| `KEEP_WAV` | `0` | Set to `1` to retain the original WAV |
| `UPLOAD_MIME_OVERRIDE` | empty | Force a MIME type when calling `notebooks.sources.uploadFile` |
| `PYTHON_BIN` | `python3` | Override if `python3` lives elsewhere or under a different name |

## Authentication notes

- Run `gcloud auth login --enable-gdrive-access` with the Google identity that owns the NotebookLM Enterprise project. This authorises both the Discovery Engine API and optional Drive-backed content.
- If you rely on Application Default Credentials elsewhere, `gcloud auth application-default login --enable-gdrive-access` keeps ADC in sync with the same account.
- `notebooklm_app/nlm.env` (or `NOTEBOOKLM_ENV`) should define `GCLOUD_PROJECT_NUMBER`, `GCLOUD_LOCATION`, and optionally `GCLOUD_ENDPOINT_LOCATION` so the script can build the proper Discovery Engine URLs.
- Every API call shells out to `gcloud auth print-access-token` (or your custom `GCLOUD_ACCESS_TOKEN_CMD`), so keep the CLI session fresh if you see HTTP 401/403 responses.
