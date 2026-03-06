# Slides Mapping Policy (Manual Only)

Denne policy er bindende for alle fag i repoet.

## Hård regel

- Mapping af slides til `lecture_key` (`W##L#`) og `subcategory` skal altid laves manuelt.
- Automatisk mapping via scripts, filnavnsmønstre, dato-tokens eller regex-heuristik er ikke tilladt.
- Scripts må kun bruges til validering, filkopiering eller upload af allerede manuelt mappede entries.

## Krav til catalog entries

`slides_catalog.json` entries skal mindst indeholde:

- `slide_key`
- `lecture_key`
- `subcategory` (`lecture`, `seminar`, `exercise`)
- `title`
- `source_filename`
- `local_relative_path`
- `relative_path`

Hvis feltet `matched_by` bruges, skal værdien være `manual`.

`local_relative_path` er den manuelle sti fra fagets lokale slide-root til kilde-PDF'en og bruges af generatoren til at oprette per-slide podcasts og quizzer. `relative_path` er serverstien under `/var/www/slides/<subject>/...` og bruges af portalen.

## Generering og kildeoptælling

- Slides tæller som kilder for per-source podcasts og per-source quizzer.
- Slides må derfor gerne få egne episode-/quiz-titler med descriptoren `Slide <subcategory>: <title>`.
- Slides må ikke tælle med i lecture-level `Alle kilder (undtagen slides)`-podcasts.
- `Alle kilder (undtagen slides)` skal fortsat kun bruge readings som uploadede notebook-kilder og som `sources=<n>`-optælling.

## Kvalitetstjek før deploy

1. Verificer at hver slide er mappet til korrekt `W##L#` ud fra officiel plan + fagets reading key.
2. Verificer at underkategorien er korrekt (`lecture`/`seminar`/`exercise`).
3. Verificer at `local_relative_path` matcher den faktiske lokale kildefil.
4. Verificer at `relative_path` matcher den faktiske filplacering på serveren.
5. Verificer at portalens lecture-side viser kun underkategorier med mindst én slide.

## Fag-specifik mapping

- Personlighedspsykologi: `shows/personlighedspsykologi-en/docs/slides-sync.md`
- Bioneuro: `shows/bioneuro/docs/slides-mapping.md`

## Portal path-resolution

- Portalen resolver slides per subject via `freudd_portal/subjects.json`.
- Hvert fag skal have sin egen `slides_catalog_path` og `slides_files_root`, hvis faget bruger slide-kataloget.
- `FREUDD_SUBJECT_SLIDES_CATALOG_PATH` og `FREUDD_SUBJECT_SLIDES_FILES_ROOT` er kun default fallback for fag uden eksplicit override.
