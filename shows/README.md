# Shows

Each subdirectory contains config and assets for a single podcast feed. The CI workflow iterates over the list of shows and regenerates each feed from Google Drive.

- `social-psychology` – live show wired to Google Drive and GitHub Actions.
- `intro-vt` – Intro + VT series; keep the Drive folder ID current and the workflow will publish automatically.

Add new shows by creating a sibling directory that mirrors this structure, then add the folder name to the matrix in `.github/workflows/generate-feed.yml` and to the Apps Script `CONFIG.drive.folderIds` list.
