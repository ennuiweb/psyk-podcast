# Bioneuro Slides Mapping (Manual Only)

Slides til bioneuro skal mappes manuelt. Der må ikke bruges scripts til at auto-aflede `lecture_key` eller `subcategory`.

## Kilder til manuel mapping

- Primær lecture-key reference: `shows/bioneuro/docs/freudd-reading-file-key.md`
- Semesterplaner og holdplaner for bioneuro (de lokale plan-dokumenter for den aktuelle undervisningsrunde)
- De faktiske slidefiler fra underviser/holdmapper

## Underkategorier

Vælg underkategori manuelt per slide:

- `lecture` for forelæsningsslides
- `seminar` for seminarholdsslides
- `exercise` for øvelsesholdsslides

Hvis en filplacering og plan ikke stemmer overens, er undervisningsplanen + manuel vurdering facit.

## Mapping-proces

1. Find korrekt `lecture_key` i `freudd-reading-file-key.md` (`W##L#`).
2. Match hver slidefil manuelt til `lecture_key`.
3. Sæt `subcategory` manuelt (`lecture|seminar|exercise`).
4. Sæt en læsbar `title` og stabil `source_filename`.
5. Skriv entry manuelt i fagets `slides_catalog.json`.

Eksempel:

```json
{
  "slide_key": "w03l1-lecture-neurofysiologi-8f21ab44",
  "lecture_key": "W03L1",
  "subcategory": "lecture",
  "title": "Neurofysiologi",
  "source_filename": "Neurofysiologi.pdf",
  "relative_path": "W03L1/lecture/Neurofysiologi.pdf",
  "matched_by": "manual"
}
```

## Drift og validering

- Upload slidefiler til `/var/www/slides/<subject>/<W##L#>/<subcategory>/<source_filename>`.
- Verificer at hver `relative_path` i kataloget findes fysisk på serveren.
- Verificer i portal-UI at tomme underkategorier ikke vises.
