# NotebookLM podcast helper

Command-line tooling that talks to the NotebookLM Enterprise API to create, monitor, and download podcast-style “audio overviews” for the shows under `shows/`.

## Usage
1. Copy `config.example.yaml` to `config.yaml` and fill in the Google Cloud project number, Notebook IDs, Drive folders, and service-account file. The CLI also understands overrides via env vars such as `NOTEBOOKLM_PROJECT_NUMBER` or `NOTEBOOKLM_SERVICE_ACCOUNT`.
2. Queue a new episode:  
   ```bash
   python -m notebooklm_app.cli create --show social-psychology
   ```
   The command stores a JSON run log under `shows/social-psychology/notebooklm/runs/` and waits until the overview is ready (unless `--skip-wait` is passed).
3. Download the generated MP3 locally:  
   ```bash
   python -m notebooklm_app.cli download --show social-psychology
   ```
4. Push the MP3 back into Google Drive so the existing feed automation can ingest it:  
   ```bash
   python -m notebooklm_app.cli sync-drive --show social-psychology
   ```

Additional helpers:

- `python -m notebooklm_app.cli status --show social-psychology --json` prints the raw NotebookLM payload.
- The CLI falls back to defaults in `config.yaml` for episode focus/language but allows overrides per invocation.

Implementation details live in this package; high-level ops notes are in `TECHNICAL.md`.
