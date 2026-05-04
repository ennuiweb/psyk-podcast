# Shows

Each subdirectory contains config and assets for a single podcast feed. The CI workflow iterates over the list of shows in its matrix (paused feeds are noted below) and regenerates each feed from the configured storage backend (`storage.provider`).

- `social-psychology` – live show currently wired to Google Drive and GitHub Actions.
- `personlighedspsykologi-en` - Personlighedspsykologi (F26) feed; now R2-backed under the legacy workflow, with workflow-managed Drive-to-R2 import constrained to the currently published inventory; quiz links use deterministic short IDs under `/q/`.
- `bioneuro` - Bio / Neuropsychology feed.
- `intro-vt` – Intro + VT Deep Dives - Hold 1 - 2024 series; keep the configured storage source current and the workflow will publish automatically.
- `intro-vt-tss` – Intro + VT Tekst til tale - 1. sem 2024 TTS feed scaffolding (CI currently paused).
- `social-psychology-tts` – Socialpsykologi Oplæst - 1. sem 2024 TTS feed scaffolding (CI currently paused).
- `personal` – Private archive feed; now R2-backed under the legacy workflow, with the resumable Drive-to-R2 importer as the canonical ingest path.
- `berlingske` – Berlingske narrated articles feed sourced from the downloader manifest (CI paused).

Add new shows by creating a sibling directory that mirrors this structure, then add the folder name to the matrix in `.github/workflows/generate-feed.yml`. Only Drive-backed shows also need an Apps Script `CONFIG.drive.folderIds` entry.

## Cover artwork style

All shows share a simple, reproducible square cover that scales cleanly for podcast apps. When adding a new show, keep these rules so the artwork stays consistent:

- **Canvas**: 3000×3000 px, solid background in the show’s primary colour (`RGB`).
- **Foreground arc**: a lower semicircle/ellipse that spans the width of the canvas; use the primary colour darkened ~25 % for subtle depth.
- **Typography**: Arial Bold (320 pt) for the title, centred horizontally near the upper third; Arial Regular for supporting lines (≈160 pt for the subtitle, ≈150 pt for metadata).
- **Colour roles**: title in near-white (`#F8FAFC`), subtitle in a bright accent tint of the palette, metadata in a muted grey-green (`#86A092`). Adjust only the primary/accent colours when giving each show its identity.
- **Layout rhythm**: keep roughly 140 px between title/subtitle and 100 px between subtitle/metadata. Reserve the top ~35 % for text so the lower arc stays visible.
- **Automation**: the artwork can be regenerated with Pillow. See `shows/intro-vt/assets/cover.png`’s generation script in this repo history (or reuse the Python snippet in the conversation) and swap the colour constants to match the show.

Save the final PNG as `shows/<show>/assets/cover.png`. Preview at full size to confirm text contrast meets accessibility expectations before publishing.
