# Social Psychology Docs

This directory contains the retained planning material for the Social Psychology
show. Published audio now comes from Cloudflare R2, while the legacy GitHub
Actions workflow still imports source files from Drive before regenerating the
feed.

| File | Purpose |
|---|---|
| `overblik.md` | Internal overview of source material, readings, and study structure. |
| `reading-file-key.md` | Canonical reading key used for mapping and important-reading context. |
| `regeneration-plan.md` | Proposed canonical rebuild plan for cleaning the historical feed. |
| `_Pensumliste.pdf` | Official syllabus source. |
| `___Undervisningsplan med prioriterede tekster.pdf` | Official teaching plan / prioritized reading source. |
| `deepdive*.png` | Historical artwork/design assets. |

Operational note:

- `storage.provider = "r2"` is now live for the show.
- `publication.owner = "legacy_workflow"` remains unchanged.
- Drive is still the source-side ingest path for the workflow-managed import.
- Do not treat `regeneration-plan.md` as implemented until a canonical
  inventory has been frozen and the historical source folders have been
  cleaned.
