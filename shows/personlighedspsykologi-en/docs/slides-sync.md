# Personlighedspsykologi Slides Mapping (Manual Only)

Slides skal mappes manuelt. Mapping må ikke auto-udledes af scripts, filnavne, dato-tokens eller regex-heuristik.

## Kilder til manuel mapping

- Forelæsningsslides:  
  `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Personlighedspsykologi/Forelæsningsrækken`
- Seminar-slides:  
  `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Personlighedspsykologi/Seminarhold/Slides`
- Øvelses-slides:  
  `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Personlighedspsykologi/Øvelseshold`
- Planlægnings-PDF (øvelser):  
  `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Personlighedspsykologi/Semesterplan for øvelseshold - opdateret d. 03.02.pdf`
- Planlægnings-PDF (forelæsning + seminar):  
  `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Personlighedspsykologi/Forelæsnings- og seminarholdsplan 2026.pdf`
- Freudd lecture-key reference: `shows/personlighedspsykologi-en/docs/reading-file-key.md`

## Underkategorier

Underkategori sættes manuelt per fil:

- `lecture` -> `slides fra forelæsning`
- `seminar` -> `slides fra seminarhold`
- `exercise` -> `slides fra øvelseshold`

Hvis en fil ligger i "forkert" mappe ift. undervisningsplanen, er undervisningsplanen + menneskelig vurdering facit.

## Sådan mappes en fil

1. Fastlæg `lecture_key` (`W##L#`) ved at krydstjekke undervisningsplan/PDF og `reading-file-key.md`.
2. Fastlæg `subcategory` (`lecture|seminar|exercise`) manuelt.
3. Fastlæg `title` (kort, læsbar titel i UI).
4. Fastlæg `source_filename` (filnavn som uploades under slide-rooten).
5. Tilføj entry manuelt i `shows/personlighedspsykologi-en/slides_catalog.json`.

## Personlighedspsykologi-specifik regel

Mapping skal laves forskelligt per underkategori:

- `lecture`:
  Brug `Forelæsnings- og seminarholdsplan 2026.pdf` plus `reading-file-key.md`.
  Filnavne med forelæsningsnummer kan bruges som hint, men planen er facit.
- `seminar`:
  Brug `Forelæsnings- og seminarholdsplan 2026.pdf` plus `reading-file-key.md`.
  Match seminar-emne til den tilhørende Freudd-forelæsning manuelt.
- `exercise`:
  Brug altid `Semesterplan for øvelseshold - opdateret d. 03.02.pdf` som primær facitliste.
  Match øvelses-emne og/eller angivne tekster i planen til `reading-file-key.md`.
  Filnavne og løbenumre i øvelses-slides må ikke bruges som selvstændig mapping-kilde.

## Kendte exercise-mappings

Følgende mappings er verificeret mod øvelsesplanen:

- `1. Intro og træk.pdf` -> `W02L1`
  Begrundelse: øvelsesplanen angiver `Introduktion & Trækteori` med `Zettler et al. (2020)`, og `Zettler et al. (2020)` ligger i `reading-file-key.md` under `W02L1`.
- `2. Psykoanalyse 1 og intro (1).pdf` -> `W05L1`
  Begrundelse: slide-indholdet er `Psykoanalyse I`/`Gammelgaard (2010)`, og `Gammelgaard (2010)` ligger i `reading-file-key.md` under `W05L1`.

Når nye øvelses-slides kommer:

1. Find emnet/teksten i øvelsesplanen.
2. Find samme tekst/emne i `reading-file-key.md`.
3. Brug den `W##L#` som lecture mapping.
4. Sæt `matched_by` til `manual`.

Eksempel:

```json
{
  "slide_key": "w11l2-seminar-forsvarsmekanismer-1234abcd",
  "lecture_key": "W11L2",
  "subcategory": "seminar",
  "title": "Seminar: Forsvarsmekanismer",
  "source_filename": "Seminar Forsvarsmekanismer.pdf",
  "relative_path": "W11L2/seminar/Seminar Forsvarsmekanismer.pdf",
  "matched_by": "manual"
}
```

## Upload destination

- Catalog: `shows/personlighedspsykologi-en/slides_catalog.json`
- Filer på server: `/var/www/slides/personlighedspsykologi/<W##L#>/<subcategory>/<source_filename>`

## Vigtige driftsregler

- `scripts/sync_personlighedspsykologi_slides_to_droplet.py` må ikke bruges til automatisk mapping.
- Portalen tillader direkte `Åben slide` for `lecture`-slides offentligt; `seminar`/`exercise` kræver elevated access eller `is_staff`/`is_superuser`.
- Hvis en underkategori ikke har slides for den aktive forelæsning, skal den ikke vises i UI.
