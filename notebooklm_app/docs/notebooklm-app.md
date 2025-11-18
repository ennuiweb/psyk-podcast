# NotebookLM Automation App

Notebook + source management still flows through the [tmc/nlm](https://github.com/tmc/nlm) CLI, while audio overview creation now uses the NotebookLM Enterprise Discovery Engine API via `gcloud`. The repo keeps the bash wrapper thin, but you need both nlm cookies and a gcloud access token tied to your project/region.

## High-level goals

- Provision short-lived notebooks (one per source file) automatically.
- Upload local sources from `notebooklm_app/sources/`, request audio overviews, download the `.wav`, and tear everything down so the next run starts from a clean slate.
- Keep the tooling local and independent from the RSS/Drive pipelines.

## nlm workflow (`notebooklm_app/scripts/notebooklm_batch.sh`)

1. **Auth once**: copy an authenticated NotebookLM request as cURL from Chrome DevTools and run `pbpaste | notebooklm_app/scripts/nlm_auth_from_curl.sh`. This normalises the `Cookie:` header, calls `nlm auth`, and writes `~/.nlm/env` with the cookies/token the script needs.
2. **Config**: copy `notebooklm_app/nlm.env.example` → `nlm.env` and tweak source/output directories, episode focus, language, concurrency, etc.
3. **Sources**: drop `.md`, `.txt`, or other supported documents into `notebooklm_app/sources/`.
4. **Run**: execute `notebooklm_app/scripts/notebooklm_batch.sh`. For each file the script:
   - calls `nlm create` to obtain a fresh notebook id;
   - runs `nlm add <id> <file>` and records the returned source id;
   - POSTs to `https://<endpoint>-discoveryengine.googleapis.com/v1alpha/projects/<project>/locations/<region>/notebooks/<id>/audioOverviews` with a `Bearer $(gcloud auth print-access-token)` header plus the selected source ids/episode focus/language;
   - polls `nlm --direct-rpc audio-download` until the WAV is ready, moves it into `notebooklm_app/outputs/`, and (by default) converts it to MP3 via `ffmpeg`;
   - feeds `y` into `nlm rm-source`, `nlm audio-rm`, and `nlm rm` so sources/audio/notebooks disappear.

`MAX_CONCURRENCY` bounds how many of those jobs run in parallel (default `2`). The log prefix `filename|worker-N` keeps interleaved output readable, and the final summary reports how many jobs succeeded or failed.

## Authentication reminders

- The DevTools cURL → `nlm auth` flow is still the most reliable way to refresh cookies for NotebookLM RPCs.
- Google Cloud auth is required as well: run `gcloud auth login` (or `gcloud auth application-default login`), set `GCLOUD_PROJECT_NUMBER`, `GCLOUD_LOCATION`, and optionally `GCLOUD_ENDPOINT_LOCATION` inside `nlm.env`, and make sure the project has NotebookLM Enterprise enabled so `gcloud auth print-access-token` succeeds.
- If `nlm` ever prints “authentication required”, redo the cURL piping step and rerun the script.
- If the audio request fails with HTTP 401/403, refresh your `gcloud` login or confirm you’re pointing at the right project/location.

## Known gaps

- The Discovery Engine API is still `v1alpha`. We rely on exponential backoff, but you may still hit throttling or transient 5xx responses during peak hours.
- `nlm rm-source`, `nlm audio-rm`, and `nlm rm` prompt for confirmation. The script pipes `y` automatically—if nlm changes the prompt text we’ll need to update the helper.
