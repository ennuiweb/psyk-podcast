# NotebookLM automation (nlm-first)

[tmc/nlm](https://github.com/tmc/nlm) still powers notebook + source management (create, upload, download, cleanup), but audio overview creation now flows through Google’s NotebookLM Enterprise Discovery Engine API via `gcloud`. You need valid nlm cookies _and_ a configured Google Cloud project/region so the script can trade your `gcloud auth print-access-token` output for audio overviews.

## Quick start

1. **Install nlm**
   ```bash
   go install github.com/tmc/nlm/cmd/nlm@latest
   ```
2. **Authenticate via DevTools cURL**
   - In Chrome, open NotebookLM → DevTools → Network, filter for `_batch`, right-click a signed-in request, and choose **Copy → Copy as cURL (bash)**.
   - Paste that command into the helper script (which normalises `Cookie:` casing automatically) and feed it into nlm:
     ```bash
     pbpaste | notebooklm_app/scripts/nlm_auth_from_curl.sh
     ```
     (You can always re-run this when cookies expire.)
   - If you rely on nlm’s browser automation instead, export your preferred Chrome profile once so every `nlm auth` invocation picks it up automatically:
     ```bash
     # ~/.zshrc
     export NLM_BROWSER_PROFILE="${NLM_BROWSER_PROFILE:-Profile 1}"
     ```
     Replace `"Profile 1"` with whichever profile actually has NotebookLM cookies.
   - Prefer Chrome Canary? Point nlm at its binary so the launcher uses the right app bundle:
     ```bash
     export NLM_BROWSER_PATH="${NLM_BROWSER_PATH:-/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary}"
     ```
   - Signed into NotebookLM as a non-primary Google account? Set the desired account index (0, 1, 2, …) so every RPC/cookie exchange lines up:
     ```bash
     export NLM_AUTHUSER="${NLM_AUTHUSER:-2}"
     ```
3. **Create an env file**
   - Copy `notebooklm_app/nlm.env.example` to `notebooklm_app/nlm.env` and adjust paths, episode focus, poll intervals, etc.
4. **Drop sources**
   - Place `.md`, `.txt`, or other documents under `notebooklm_app/sources/`.
5. **Run the batch script**
   ```bash
   notebooklm_app/scripts/notebooklm_batch.sh
   ```
   The script spins up temporary notebooks via nlm, adds your sources, creates audio overviews, downloads `.wav` files, converts them to `.mp3` (unless you opt out), and then removes every source/notebook it created.

## Requirements

- [`nlm`](https://github.com/tmc/nlm) available on your `PATH` (or point `NLM_BIN` at it).
- `bash`, `file`, and `awk` on macOS/Linux (all part of the default developer toolchain).
- [`gcloud`](https://cloud.google.com/sdk/docs/install) authenticated against the Google Cloud project that hosts NotebookLM Enterprise. Export `GCLOUD_PROJECT_NUMBER`, `GCLOUD_LOCATION`, and (optionally) `GCLOUD_ENDPOINT_LOCATION` in `nlm.env` so the script can hit the right Discovery Engine endpoint.
- `python3` (or `python`) for the tiny helper that renders the Discovery Engine JSON payload.
- [`ffmpeg`](https://ffmpeg.org/) for the automatic WAV→MP3 conversion (install via `brew install ffmpeg`). Set `OUTPUT_AUDIO_FORMAT=wav` if you want to skip conversion.
- Optional: `UPLOAD_MIME_OVERRIDE` in `nlm.env` if you need to force a MIME type when uploading from unusual extensions.

## Script internals

- For each source the script executes the following pipeline:
  1. `nlm create "<title>"` → capture the notebook id.
  2. `nlm add <id> <file>` → upload the local markdown/text file and record the returned source id.
  3. `curl -X POST "https://${GCLOUD_ENDPOINT_LOCATION}-discoveryengine.googleapis.com/${GCLOUD_DISCOVERY_API_VERSION}/projects/${GCLOUD_PROJECT_NUMBER}/locations/${GCLOUD_LOCATION}/notebooks/<id>/audioOverviews" -H "Authorization:Bearer $(gcloud auth print-access-token)" -d '{"sourceIds":[{"id":"<source>"}],"episodeFocus":"…","languageCode":"…"}'` → ask the NotebookLM Enterprise API for an audio overview.
  4. Poll `nlm --direct-rpc audio-download <id> <temp.wav>` until audio is ready, move the file to `outputs/<filename>.wav`, and optionally convert it to MP3 via `ffmpeg` (controlled by `OUTPUT_AUDIO_FORMAT`, `MP3_BITRATE`, and `KEEP_WAV`).
  5. `nlm rm-source`, `nlm audio-rm`, and `nlm rm` (piped a “y” answer) clean up every resource before the notebook id is forgotten.
- Jobs run through a bounded worker pool (`MAX_CONCURRENCY`, default `2`). Each worker prefixes log lines with `<filename>|worker-N`, which keeps interleaved output readable.
- `POLL_INTERVAL` and `POLL_TIMEOUT` control how frequently we retry `nlm audio-download`. Set `POLL_TIMEOUT=0` to wait indefinitely for very long generations.
- All nlm stderr/stdout is captured: authentication failures bubble up immediately with instructions to rerun the DevTools cURL flow.

## Configuration knobs (`nlm.env`)

| Variable | Default | Purpose |
| --- | --- | --- |
| `SOURCES_DIR` / `OUTPUT_DIR` | `notebooklm_app/sources` / `notebooklm_app/outputs` | Input/output locations |
| `NOTEBOOK_TITLE_PREFIX` | `NotebookLM Batch` | Prepended to every temp notebook title |
| `EPISODE_FOCUS` / `LANGUAGE_CODE` | See example | Passed to the Discovery Engine API as `episodeFocus` and `languageCode` |
| `GCLOUD_PROJECT_NUMBER` / `GCLOUD_LOCATION` | _required_ | NotebookLM Enterprise project + region used for audio requests |
| `GCLOUD_ENDPOINT_LOCATION` | inherits `GCLOUD_LOCATION` | Hostname prefix for `*-discoveryengine.googleapis.com` (override if the endpoint differs from the region) |
| `GCLOUD_DISCOVERY_API_VERSION` | `v1alpha` | Discovery Engine API version path segment |
| `MAX_CONCURRENCY` | `2` | Number of notebooks processed in parallel |
| `OUTPUT_AUDIO_FORMAT` | `mp3` | Use `wav` to skip ffmpeg conversion |
| `MP3_BITRATE` | `128k` | Bitrate for MP3 exports |
| `KEEP_WAV` | `0` | Set to `1` to retain the original WAV |
| `UPLOAD_MIME_OVERRIDE` | empty | Force a MIME type when calling `nlm add` |
| `NLM_BIN` | `nlm` | Override if the binary lives outside `PATH` |
| `PYTHON_BIN` | `python3` | Override if `python3` lives elsewhere or under a different name |

## Authentication tip (fastest path)

Instead of letting nlm drive a browser, always copy a signed-in NotebookLM request as cURL and pipe it into the helper script:

```bash
pbpaste | notebooklm_app/scripts/nlm_auth_from_curl.sh
```

The helper lowercases the `Cookie:` header automatically and pipes the result to `nlm auth`, which writes `~/.nlm/env`. Re-auth takes seconds whenever cookies expire.

Separately, run `gcloud auth login` (or `gcloud auth application-default login`) against the Google Cloud project that hosts NotebookLM Enterprise, then export `GCLOUD_PROJECT_NUMBER`, `GCLOUD_LOCATION`, and (if needed) `GCLOUD_ENDPOINT_LOCATION` in `notebooklm_app/nlm.env`. The script shells out to `gcloud auth print-access-token` for every audio overview request, so the CLI must already be authenticated.

## Rebuilding the patched nlm binary

We currently rely on a custom `tmc/nlm` build that reads `NLM_AUTHUSER` so multi-account Google sessions work. Pulling upstream with `go install github.com/tmc/nlm/cmd/nlm@latest` will overwrite that binary. To rebuild the patched version:

1. Copy the module source out of Go’s module cache so you can edit it locally.
   ```bash
   NLM_SRC=~/src/nlm-authuser
   rm -rf "$NLM_SRC"
   mkdir -p "$(dirname "$NLM_SRC")"
   cp -R "$(go env GOPATH)/pkg/mod/github.com/tmc/nlm@"* "$NLM_SRC"
   ```
2. Apply the `NLM_AUTHUSER` patches (already in this repo under `notebooklm_app/scripts` if you need to diff) or re-run your preferred patch command.
3. Rebuild and install.
   ```bash
   cd "$NLM_SRC"
   go install ./cmd/nlm
   ```
4. Verify with `which nlm` or `nlm --help`; the binary in `~/go/bin/nlm` should now honor `NLM_AUTHUSER`.

Whenever you reinstall from upstream, repeat the steps above to bring back the multi-account support.
