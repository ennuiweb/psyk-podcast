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

Designprincip:

- systemet skal fungere som et dekomponeret alternativ til en hypotetisk model,
  der kunne laese og forstaa hele kurset i ett pass
- derfor skal `Source Intelligence Layer` understoette:
  - bottom-up flow fra kilder til lecture/course artifacts
  - top-down flow fra course arc og theory structure tilbage til lokal
    prioritering
  - sideways flow mellem lectures, begreber og teorier
- det maa ikke blive til fri rekursiv prompt-suppe; flowet skal ske gennem
  eksplicitte og auditerbare artifacts

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
- bygge et course-level glossary- og theory-lag oven paa lecture bundles
- spore hash-baserede dependencies for de vigtigste `Source Intelligence`
  artifacts

## Hvad der stadig mangler

Systemet er endnu ikke et fuldt modent preprocesseringssystem. De vigtigste
huller er:

- kursusoverblikket er kun indirekte kildeinformeret; det er ikke bygget fra
  alle source files som et samlet semestermateriale
- source weighting findes nu som artifact, men endnu ikke som et egentligt
  downstream styringslag i prompt selection
- staleness findes nu som et hash-baseret index, men endnu ikke som et
  automatisk rebuild-/blokkeringslag
- det nuvaerende distinction-/concept-graph-lag er stadig foerste generation og
  endnu ikke dybt nok til at bære mere avanceret selection alene
- weekly auto-meta er stadig readings-first; lecture/seminar slide-indhold er
  ikke preprocesseret ind i en egentlig lecture bundle

Vigtig nuancering: `course_context.py` er deterministisk og model-fri. Det
goer promptlaget mere robust, men betyder ogsaa, at kvaliteten stadig er
begracnset af de metadata og summaries, der allerede findes.

## Ny baseline: file, lecture og course-level artifacts

De foerste nye artifacts i den modne preprocessing-arkitektur er:

- `shows/personlighedspsykologi-en/source_catalog.json`
- `shows/personlighedspsykologi-en/source_intelligence_policy.json`
- `shows/personlighedspsykologi-en/lecture_bundles/index.json`
- `shows/personlighedspsykologi-en/lecture_bundles/W##L#.json`
- `shows/personlighedspsykologi-en/source_intelligence_seed.json`
- `shows/personlighedspsykologi-en/course_glossary.json`
- `shows/personlighedspsykologi-en/course_theory_map.json`
- `shows/personlighedspsykologi-en/source_intelligence_staleness.json`
- `shows/personlighedspsykologi-en/source_weighting.json`
- `shows/personlighedspsykologi-en/course_concept_graph.json`

Formaalet er at faa et stabilt, deterministisk file-level lag med:

- source identity pr. reading/slide
- lecture-tilknytning
- sha256 for staleness-sporbarhed
- sideantal, tekstmaengde og token-estimat
- sprog-heuristik
- source-type og simple prioritetssignaler
- course-tunet evidensrolle pr. source (`reading_grounded`,
  `textbook_framing`, `lecture_framed`, `seminar_applied`,
  `exercise_clarified`)
- markering af manuel summary-dackning og eksisterende prompt-sidecars

Kataloget er lokalt bygget fra de raa source files og er derfor mere end en
manifest-view. Det er den nye base for weighting, invalidation og
lecture-bundle bygning.

Den nye policy-fil er vigtig, fordi dette subsystem skal vaere tunet til netop
`personlighedspsykologi`:

- `grundbog` behandles her som conceptual framing snarere end bare endnu en
  reading
- forelaesningsslides behandles som framing- og emphasis-evidence
- seminarslides behandles som application-/diskussionsevidence
- exerciseslides behandles som clarification-/training-evidence

Kanonisk rebuild-kommando:

```bash
./.venv/bin/python scripts/build_personlighedspsykologi_source_intelligence.py
```

Manuelle del-kommandoer, hvis et bestemt lag skal rebuildes isoleret:

```bash
./.venv/bin/python scripts/build_personlighedspsykologi_source_catalog.py
./.venv/bin/python scripts/build_personlighedspsykologi_lecture_bundles.py
./.venv/bin/python scripts/build_personlighedspsykologi_semantic_artifacts.py
./.venv/bin/python scripts/build_personlighedspsykologi_source_weighting.py
./.venv/bin/python scripts/build_personlighedspsykologi_concept_graph.py
```

## Lecture bundles

Det nye lecture-bundle-lag er et deterministisk mellemartifact bygget fra:

- `source_catalog.json`
- `content_manifest.json`
- lokale `*.analysis.md` sidecars
- lokale `week.analysis.md` sidecars

Hver lecture bundle samler:

- lecture-identitet og kursusposition
- lecture-summary og manifest warnings
- grouped sources for readings, lecture slides, seminar slides og exercise
  slides
- simple source-prioritetsvurderinger
- course-specifik evidensrolle pr. source
- summary coverage og analysis coverage
- week-level analysis sidecars
- likely core / supporting sources

Formaalet er at give `Prompt Assembly Layer` og senere course-level artifacts et
rigere, stabilt lecture-level knowledge object end blot summary-prosa og flade
context-noter.

## Course-level semantics

Det nye course-level semantic lag bestaar af:

- `source_intelligence_seed.json` som auditerbar ontologi/seed-fil
- `source_intelligence_policy.json` som course-specifik fortolkningspolitik
- `course_glossary.json` som term-lag med lecture/source grounding
- `course_theory_map.json` som theory cluster-lag med relationer
- `source_intelligence_staleness.json` som hash-baseret dependency-index
- `source_weighting.json` som deterministisk source-rangeringslag
- `course_concept_graph.json` som foerste sideways artifact

Glossary-laget giver:

- kanoniske begreber med aliases
- lecture-tilknytning og evidence
- evidence-origin labels fra de sources, der bærer et term
- linked terms og linked theories
- simple salience-signaler

Theory-map-laget giver:

- theory clusters paa tvacrs af forelaesninger
- core terms pr. teori
- representative source ids
- representative evidence origins
- relationer mellem teorier

Concept-graph-laget giver:

- term- og theory-nodes i samme artifact
- tvacrgaaende edges mellem begreber, teorier og shared lectures
- eksplicitte distinctions som kursusspacndinger
- supporting evidence origins for distinction-supporting sources
- et foerste sideways lag paa tvacrs af semesteret

Staleness-laget giver:

- sha256 for inputs og outputs
- explicit dependency-lister for glossary og theory map
- et foerste fundament for senere automatisk invalidation

Weighting-laget giver:

- en eksplicit scoreramme for lecture sources
- kombination af bottom-up og top-down signaler
- et bedre grundlag for senere prompt selection

Det er ogsaa begyndt at blive brugt downstream:

- `course_context.py` kan nu injecte kompakt semantic guidance fra glossary,
  theory map, weighting og concept graph ind i den deterministiske lecture
  context note

## Kendte graenser

- GitHub Actions kan ikke i dag rebuild’e `source_catalog.json`, fordi workflowet
  ikke har adgang til de raa lokale kursusfiler i OneDrive/source tree.
- Katalog, lecture bundles og de nye course-level semantic artifacts er derfor i
  foerste version deterministiske lokale build-artifacts, som committes til
  repoet.
- `W03L2` har fortsat en manifest-markeret missing reading (`Bach & Simonsen
  (2023)`), og baade katalog og lecture bundle skal bevare den som missing i
  stedet for at opfinde en filmapping.
- `overblik.md` bruges fortsat som theme/course-arc input, men er endnu ikke et
  egentligt source-derived semester-resume.

## Naeste modne lag

Den planlagte raekkefoelge er:

1. `source_catalog.json`
2. `lecture_bundle.json` pr. lecture
3. `course_glossary.json`
4. `course_theory_map.json`
5. hash-baseret stale/invalidation-model
6. source weighting som egentligt styringslag
7. dybere distinction graph / cross-lecture concept graph
8. slide-informed weekly preprocessing
9. automatic stale enforcement

Det betyder, at outputs godt kan bygges nu, men at den mest modne version af
systemet foerst opnaar sit egentlige loft, naar weighting, concept graph og
automatisk staleness enforcement er pa plads.
