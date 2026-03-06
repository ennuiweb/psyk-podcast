# Bioneuro Slides Mapping (Manual Only)

Slides til `bioneuro` skal mappes manuelt. Scripts må ikke bruges til at aflede `lecture_key`, `subcategory` eller titel.

## Autoritative kilder

Brug disse kilder i denne rækkefølge:

1. `shows/bioneuro/docs/freudd-reading-file-key.md`
2. `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Bioneuro/Biological Psychology and Neuropsychology Spring 2026.xlsx`
3. De faktiske slidefiler i kilde-mapperne:
   - `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Bioneuro/Lectures`
   - `/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/Mine dokumenter 💾/psykologi/Bioneuro/Holdundervisning`

Hvis filnavn, mappeplacering og plan ikke siger det samme, er `freudd-reading-file-key.md` + Excel-planen facit.

## Underkategorier

- `lecture`: filer fra `Lectures/`
- `exercise`: filer fra `Holdundervisning/`
- `seminar`: bruges kun hvis der kommer en separat seminar-kilde. Der er ingen seminar-slides i de nuværende bioneuro-kilder.

Der må ikke oprettes tomme eller gættede `seminar`-entries.

## Mapping-regler for bioneuro

- Lecture slides mappes til den forelæsning i `freudd-reading-file-key.md`, som matcher planens tema og dato.
- Exercise slides mappes via Excel-planens "Excercise classes" kolonne, ikke via filnavnets løbenummer alene.
- `Holdundervisning/1 Introduktion - Hold 1.pdf` matcher `Class 1. Introduction to "Biological psychology and neuropsychology"` i uge 7 og knyttes derfor til `W01L1`.
- `Holdundervisning/2 Makroanatomi - Hold 1.pdf` matcher `Class 2. Macroscopic neuroanatomy` i uge 9 og knyttes derfor til `W02L1`.
- Hvis en holdslide nævner et andet hold på forsiden end i filnavnet, er temaet i Excel-planen og slideindholdet stadig facit for `lecture_key`. Det gælder aktuelt for `2 Makroanatomi - Hold 1.pdf`, som på forsiden nævner `BA Tilvalg`.
- Hvis flere hold senere får samme slideindhold, behold én catalog entry per faktisk slidefil, men hold `lecture_key` baseret på planens tema.

## Aktuelt verificerede mappings

| Kilde-fil | `lecture_key` | `subcategory` | Titel |
| --- | --- | --- | --- |
| `Lectures/BioNeuroLecture1_2026.pdf` | `W01L1` | `lecture` | `Introduction to course and topic` |
| `Lectures/BioNeuroLecture 2_2026_Neuroanatomy.pdf` | `W02L1` | `lecture` | `The Macro- and Microscopic Anatomy of the Nervous System` |
| `Lectures/BioNeuroLecture3_2026-02-20-BasicNeurophysiol-MSC.pdf` | `W03L1` | `lecture` | `Neurophysiology` |
| `Lectures/BioNeuroLecture4_2026_SV.pdf` | `W04L1` | `lecture` | `Neurochemistry & Neuropharmacology` |
| `Lectures/BioNeuroLecture 5 Hormones and the brain.pdf` | `W05L1` | `lecture` | `Hormones and the Brain` |
| `Holdundervisning/1 Introduktion - Hold 1.pdf` | `W01L1` | `exercise` | `Class 1. Introduction to Biological Psychology and Neuropsychology` |
| `Holdundervisning/2 Makroanatomi - Hold 1.pdf` | `W02L1` | `exercise` | `Class 2. Macroscopic Neuroanatomy` |

Alle entries i `shows/bioneuro/slides_catalog.json` skal have `matched_by: "manual"`.

## Katalog-proces

1. Kontrollér at filen faktisk er en slidefil og ikke en reading eller video.
2. Find korrekt `W##L#` i `freudd-reading-file-key.md`.
3. Brug Excel-planen til at bekræfte tema og holdtype.
4. Tilføj entry manuelt i `shows/bioneuro/slides_catalog.json`.
5. Upload filen til `/var/www/slides/bioneuro/<W##L#>/<subcategory>/<source_filename>`.
6. Verificér at portal-UI kun viser de underkategorier, der har mindst én slide.

## Drift

- Catalog: `shows/bioneuro/slides_catalog.json`
- Server root: `/var/www/slides/bioneuro`
- Subject config: `freudd_portal/subjects.json`

Når nye slides frigives senere på semesteret, skal de mappes manuelt efter samme proces. Der må ikke indføres auto-mapping som mellemled.
