# Preprocessing System

Dette dokument beskriver den nuvaerende preprocessing-arkitektur for
`personlighedspsykologi` og den planlagte modning af systemet foer bred
output-produktion.

Canonical navn:

- `Source Intelligence Layer`

Dette dokument beskriver altsaa den del af `Freudd Content Engine`, der skal
skabe de bedst mulige betingelser for laeringsmateriale ved at bygge et rigere
preprocesseret source-lag foer course context, prompt assembly og egentlig
generation.

## Nuvaerende lag

Preprocessing bestaar i dag af tre forskellige lag:

1. Deterministisk kursus- og lecture-kontekst
   - `shows/personlighedspsykologi-en/content_manifest.json`
   - `shows/personlighedspsykologi-en/slides_catalog.json`
   - `shows/personlighedspsykologi-en/docs/overblik.md`
   - `notebooklm_queue/course_context.py`
2. Manuelle summary-caches
   - `shows/personlighedspsykologi-en/reading_summaries.json`
   - `shows/personlighedspsykologi-en/weekly_overview_summaries.json`
3. Valgfrie LLM-sidecars
   - `*.analysis.md` for enkeltkilder
   - `week.analysis.md` for lecture-level reading bundles
   - auto-meta bruger Gemini via `prompt_config.json`, naar det er aktiveret

Det vigtigste nuvaerende princip er, at promptsystemet er blevet
course-aware, men at den course-aware del stadig mest er en kompileret
kontekstnote, ikke et rigt preprocesseret knowledge layer.

## Hvad systemet kan nu

- situere en lecture i semesterforloebet via `content_manifest.json` og
  `overblik.md`
- injicere eksplicitte roller for readings, forelaesningsslides og
  seminarslides i prompts
- genbruge samme lecture-kontekst paa tvacrs af audio og report/study-guide
  outputs
- bruge manuelle summaries som stabil kursusforstaaelse
- bruge per-source og weekly Gemini-sidecars som ekstra fortolkningslag

## Hvad der stadig mangler

Systemet er endnu ikke et modent preprocesseringssystem. De vigtigste huller er:

- kursusoverblikket er kun indirekte kildeinformeret; det er ikke bygget fra
  alle source files som et samlet semestermateriale
- der findes endnu ikke et kanonisk begrebs-/teorilag som f.eks.
  `course_glossary.json` eller `course_theory_map.json`
- source weighting findes ikke endnu; laengde, centralitet og type bruges kun
  svagt eller slet ikke som signaler
- staleness er ikke hash-baseret; summaries og sidecars invalideres ikke
  automatisk, hvis en PDF aendres
- weekly auto-meta er stadig readings-first; lecture/seminar slide-indhold er
  ikke preprocesseret ind i en egentlig lecture bundle

Vigtig nuancering: `course_context.py` er deterministisk og model-fri. Det
goer promptlaget mere robust, men betyder ogsaa, at kvaliteten stadig er
begracnset af de metadata og summaries, der allerede findes.

## Ny baseline: source catalog

Foerste nye artifact i den modne preprocessing-arkitektur er:

- `shows/personlighedspsykologi-en/source_catalog.json`

Formaalet er at faa et stabilt, deterministisk file-level lag med:

- source identity pr. reading/slide
- lecture-tilknytning
- sha256 for staleness-sporbarhed
- sideantal, tekstmaengde og token-estimat
- sprog-heuristik
- source-type og simple prioritetssignaler
- markering af manuel summary-dackning og eksisterende prompt-sidecars

Kataloget er lokalt bygget fra de raa source files og er derfor mere end en
manifest-view. Det er den nye base for senere weighting, invalidation og
lecture-bundle bygning.

Build-kommando:

```bash
./.venv/bin/python scripts/build_personlighedspsykologi_source_catalog.py
```

## Kendte graenser

- GitHub Actions kan ikke i dag rebuild’e `source_catalog.json`, fordi workflowet
  ikke har adgang til de raa lokale kursusfiler i OneDrive/source tree.
- Kataloget er derfor i foerste version et deterministisk lokalt build-artifact,
  som committes til repoet.
- `W03L2` har fortsat en manifest-markeret missing reading (`Bach & Simonsen
  (2023)`), og kataloget skal bevare den som missing i stedet for at opfinde en
  filmapping.
- `overblik.md` bruges fortsat som theme/course-arc input, men er endnu ikke et
  egentligt source-derived semester-resume.

## Naeste modne lag

Den planlagte raekkefoelge er:

1. `source_catalog.json`
2. `lecture_bundle.json` pr. lecture
3. `course_glossary.json`
4. `course_theory_map.json`
5. hash-baseret stale/invalidation-model
6. slide-informed weekly preprocessing og bedre source weighting

Det betyder, at outputs godt kan bygges nu, men at den mest modne version af
systemet foerst opnaar sit egentlige loft, naar lecture bundles og et
course-level concept layer er pa plads.
