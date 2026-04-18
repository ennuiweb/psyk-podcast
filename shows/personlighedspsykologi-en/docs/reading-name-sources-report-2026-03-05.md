# Reading Name Sources Report (2026-03-05)

## Scope
This note documents how reading titles are chosen today, and how we now store both naming variants (Forelaesningsplan + Pensumliste) for later review.

Source PDFs used:
- `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Personlighedspsykologi/Pensumliste 2026.pdf`
- `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Personlighedspsykologi/Forelæsningsplan 2026 Personlighedspsykologi.pdf`

## Current Runtime Behavior
For each reading bullet in `reading-file-key.md`:
- Left side of `- ... -> ...` is the canonical `reading_title` used in Freudd Portal UI/progress/mapping.
- Right side is the `source_filename` used for reading file resolution/download.

So the runtime title is whichever label is written on the left side in the reading key.

## Implemented Format
For all non-`Grundbog kapitel` readings, we now store both names directly under each bullet:

```md
- Example title -> Example file.pdf
  Forelaesningsplan: ...
  Pensumliste: ...
```

Rules:
- `Grundbog kapitel` lines are exempt (no extra metadata lines).
- These two indented lines are documentation-only.
- Existing parsers ignore them and still only parse bullet lines.

## Files Updated
- `shows/personlighedspsykologi-en/docs/reading-file-key.md`
- historical secondary mirror path removed; canonical repo mirror is `shows/personlighedspsykologi-en/docs/reading-file-key.md`

## Compatibility Verification
Checked after update:
- `freudd_portal` manifest rebuild still succeeds.
- `sync_personlighedspsykologi_readings_to_droplet.py` parsing still works (same entry count/order expectations).
- Canonical reading titles for runtime are unchanged by metadata lines.

## Related Earlier Fix (same session)
W05L2 chapter naming issue was fixed to:
- `Grundbog kapitel 07 - Nyere psykoanalytiske teorier`

Result:
- Quizzes and podcasts stayed attached.
- Reading PDF link stayed functional.

## Deployment / Ops Status
- Freudd deploy completed on droplet.
- Smoke checks: login `200`, progress redirect `301` (gunicorn + public endpoint).
- Feed workflow completed successfully:
  - Run: `22725417219`
  - URL: `https://github.com/ennuiweb/psyk-podcast/actions/runs/22725417219`
  - Commit: `0dcd02a256ce3d17451c27ec21fe98351f9ecce4`
