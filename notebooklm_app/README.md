# NotebookLM local helper

Command-line tooling that talks to the NotebookLM Enterprise **Podcast API** to create, monitor, and download narrated podcasts. Everything stays on the local filesystem—no coupling to the Drive/RSS automation elsewhere in this repo.

## Usage
1. Copy `config.example.yaml` to `config.yaml` and set the Google Cloud project ID, default language/length, workspace root, and service-account file (env vars like `NOTEBOOKLM_PROJECT_ID`, `NOTEBOOKLM_LANGUAGE`, or `NOTEBOOKLM_WORKSPACE_ROOT` act as overrides).
2. Define one or more `profiles` with titles/descriptions plus a list of `contexts` (inline text, text files, or binary blobs). Profiles keep per-show prompts while sharing the same GCP project + credentials.
3. Queue a new podcast for a profile:  
   ```bash
   python -m notebooklm_app.cli create --profile social-psychology
   ```
   The CLI logs each request/response under `notebooklm_app/workspace/<profile>/notebooklm/runs/` by default. Add `--context-text` / `--context-file`, `--focus`, or `--length` to override the profile defaults per run.
4. Check the operation status or download the finished MP3:  
   ```bash
   python -m notebooklm_app.cli status --profile social-psychology
   python -m notebooklm_app.cli download --profile social-psychology --wait
   ```
   Files land in `.../notebooklm/downloads/` unless `--output` points elsewhere.

Additional helpers:

- `python -m notebooklm_app.cli status --profile social-psychology --json` prints the raw operation payload.
- `python -m notebooklm_app.cli download --profile social-psychology --operation <name>` lets you fetch a specific historical run.

Implementation details live entirely in this package; the rest of the repository remains untouched when using this tool.
