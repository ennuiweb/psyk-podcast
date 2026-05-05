# Preprocessing System

Dette dokument beskriver den nuvaerende preprocessing-arkitektur for
`personlighedspsykologi` og den planlagte modning af systemet foer bred
output-produktion.

Canonical navn:

- `Source Intelligence Layer`

Dette er kerne-artifactlaget inde i `Course Understanding Pipeline`. Dokumentet
beskriver altsaa den del af `Freudd Content Engine`, der skal skabe de bedst
mulige betingelser for laeringsmateriale ved at bygge et rigere preprocesseret
source-lag, som `Course Context Layer` senere kan selektere og kompilere fra,
foer prompt assembly og egentlig generation.

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

## Strategisk skift: Gemini som semantic engine

Den vigtigste skelnen fremover er:

- preprocessing bygger course-substratet
- prompt tuning bestemmer, hvordan en bestemt generator bruger substratet

For eksamensnaer produktion er preprocessing hovedopgaven. Promptarbejde er
vigtigt, men det maa ikke blive erstatningen for faktisk course-forstaaelse.

Den foretrukne vej er derfor nu en Gemini-tung rekursiv preprocessing-model,
hvor Python primært er rails:

- Python laver inventory, batching, caching, retries, schema validation,
  staleness og artifact writing
- Gemini 3.1 Pro laver den semantiske fortolkning af kilder, lectures,
  course arc og relationer
- NotebookLM prompts faar kun en kompakt valgt substrate-slice

Maalet er ikke at bygge flest mulige scripts. Maalet er et substrate, der er
klart bedre end den simple baseline: upload source files og brug en simpel
prompt.

## Rekursiv course-preprocessing

Den naeste modne version skal bygges i fem passes:

1. Source pass
2. Lecture pass
3. Course pass
4. Downward revision pass
5. Output substrate pass

Source pass:

- sender hver tilgaengelig reading og slide deck som faktisk source file til
  Gemini Files API
- skriver structured source cards
- markerer claims, centrale begreber, distinctions, theory role,
  misunderstandings, source role og provenance

Lecture pass:

- samler source cards for en lecture
- inkluderer som default de faktiske raw source files igen, saa Gemini kan
  laese readings/slides direkte ved lecture-level syntese
- skriver lecture substrates med lecture question, source roles,
  reading/slide relationer, centrale tensions og must-carry ideas

Course pass:

- laeser alle lecture substrates
- skriver course arc, glossary, theory map, distinction map og sideways
  relations

Downward revision pass:

- genbesoeger hver lecture substrate med course passet i view
- markerer hvad der faktisk betyder mest lokalt, naar hele kursusbevaegelsen
  er kendt

Output substrate pass:

- skriver kompakte generation substrates
- for dette task er podcast substrates i scope
- setup af alle andre outputfamilier er ikke core scope endnu

Foerste konkrete ikke-podcast consumer efter dette er nu printable reading
scaffolds:

- `scripts/build_personlighedspsykologi_reading_scaffolds.py`
- output: `notebooklm-podcast-auto/personlighedspsykologi/output/<lecture>/scaffolding/<source_id>/`
- artifacts: `reading-scaffolds.json` plus tre PDF/Markdown-filer:
  `01-abridged-guide`, `02-unit-test-suite`, `03-cloze-scaffold`
- denne vej sender altid den faktiske source PDF til Gemini 3.1 Pro via Files
  API; lokal kode maa kun vaelge, hashe, cache og rendere output
- source cards, revised lecture substrates og course synthesis bruges som
  prioriteringssubstrat, ikke som erstatning for at Gemini laeser selve
  kilden

Guardrails:

- alle LLM artifacts skal schema-validates
- alle artifacts skal have input source ids og dependency hashes
- missing sources skal blive explicit missing, ikke udfyldes af inference
- claims skal saa vidt muligt markeres som source-grounded, slide-framed eller
  synthetic course interpretation
- prompts maa ikke faa hele artifact-stakken, kun den valgte substrate-slice

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
- den downstream brug skal vaere konservativ: artifacts skal foerst og fremmest
  forbedre selection, ikke bloate den endelige NotebookLM-prompt

## Nuvaerende beslutninger for prompt-side selection

Foelgende defaults gaelder nu, indtil der er en god grund til at aendre dem:

- `Source Intelligence Layer` maa gerne vaere rigere end prompt-overfladen
- final podcast prompts skal bruge faa, hoejvaerdisignaler frem for mange
  mellemvaerdige signaler
- reading prompts skal prioritere `reading_grounded` og `textbook_framing`
  evidence
- lecture-slide prompts skal prioritere `lecture_framed` evidence
- seminar-slide prompts skal prioritere `seminar_applied` evidence
- short prompts skal vaere ekstra aggressive i trimming

Det betyder konkret, at semantic guidance i `course_context.py` nu skal vaelge
selektivt i stedet for bare at dumpe de hoejest rangerede artifacts. Maalet er
et tyndt prompt-surface med bedre selection, ikke et tykkere prompt-surface.

For `short` betyder det nu ogsaa:

- local course arc i stedet for generisk semester-arc
- kun target reading i reading map for reading-baserede short prompts
- ingen redundant theory-frame, hvis det blot gentager et valgt tradition-term
- ingen ekstra grounding-regler inde i course-context-noten, hvis de allerede
  gentages downstream i prompt-frameworket

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

1. Gemini source cards for alle tilgaengelige readings og slide decks
2. Gemini lecture substrates pr. lecture
3. Gemini course synthesis fra alle lecture substrates
4. downward revision af lecture substrates ud fra course synthesis
5. compact podcast substrates til NotebookLM generation
6. prompt integration, der bruger podcast substrate uden at bloate prompts
7. automatic stale enforcement for LLM-derived artifacts

Det betyder, at outputs godt kan bygges nu, men at den faerdige
preprocessing-version for eksamensformaal foerst er paa plads, naar hvert
tilgaengeligt source file har vaeret gennem Gemini source passet, hver lecture
har et revised lecture substrate, og podcasts kan genereres fra en kompakt
podcast substrate i stedet for kun fra generisk prompt-kontekst.

## Implementation plan for testing readiness

Foer vi kan teste podcastgenerering ordentligt paa den nye preprocessing-model,
skal foelgende kode- og artifact-lag bygges.

Status 2026-05-05:

- kodevejen for hele den rekursive model er nu implementeret
- Gemini key lookup virker nu via environment variabler og fallback til den
  lokale Memory Bridge secret store (`google.gemini.api_key`); secret value er
  ikke gemt i repoet
- `--preflight-only` lykkes nu for `gemini-3.1-pro-preview` med den lokale
  secret-store key
- foerste live `W05L1,W06L1` batch har skrevet 9 source cards, 2 lecture
  substrates, 1 partial course synthesis, 2 revised lecture substrates og 2
  podcast substrates
- `google-genai` er tilfoejet til root `requirements.txt` og installeret i
  den lokale `.venv`
- `shows/personlighedspsykologi-en/source_intelligence/index.json` er den
  aktuelle coverage/staleness status for LLM-artifacts
- nuvaerende coverage er 9 source cards, 2 lecture substrates, 1 partial
  course synthesis, 2 revised lecture substrates og 2 podcast substrates for
  testbatchen `W05L1,W06L1`
- stale count er 0 for den nuvaerende artifact set

### 1. Shared Gemini preprocessing client

Implementeret som et lille shared client-lag, ikke en stor
framework-abstraktion.

Placering:

- `notebooklm_queue/gemini_preprocessing.py`

Ansvar:

- laese `GEMINI_API_KEY` eller `GOOGLE_API_KEY` fra environment
- uploade PDF/source files til Gemini files API
- kalde `gemini-3.1-pro-preview` med `thinking_level=high`
- bevare Gemini 3 standard-temperature i stedet for at saenke den
- bruge `response_mime_type="application/json"` plus stage-specifikke
  `response_json_schema` kontrakter
- retrye transient failures
- skrive request metadata uden at gemme secrets
- returnere parsed JSON eller en tydelig fail-open/fail-closed status

Testdaekning:

- `tests/test_gemini_preprocessing.py`

### 2. Recursive artifact directories

LLM-derived artifacts skal ligge separat fra de deterministiske artifacts, saa
det er tydeligt hvad der er model-output.

Foreslaaet struktur:

```text
shows/personlighedspsykologi-en/source_intelligence/
  source_cards/
    <source_id>.json
  lecture_substrates/
    W##L#.json
  course_synthesis.json
  revised_lecture_substrates/
    W##L#.json
  podcast_substrates/
    W##L#.json
  index.json
```

`index.json` skrives af validatoren og viser coverage, completeness,
validation errors og stale artifacts.

### 3. Source-card builder

Script:

- `scripts/build_personlighedspsykologi_source_cards.py`

Inputs:

- `source_catalog.json`
- `source_intelligence_policy.json`
- raw source files

Outputs:

- `source_intelligence/source_cards/<source_id>.json`

Minimum schema:

- source identity and hashes
- source family and evidence origin
- central claims
- key concepts
- distinctions
- theory/tradition role
- likely misunderstandings
- relation to lecture
- quote/page targets if Gemini can infer them safely
- provenance and confidence

Testing target:

- run for `W05L1` and `W06L1` first
- then run all non-missing sources

Dry-run:

```bash
./.venv/bin/python scripts/build_personlighedspsykologi_source_cards.py --lectures W05L1,W06L1 --dry-run
```

### 4. Lecture-substrate builder

Script:

- `scripts/build_personlighedspsykologi_lecture_substrates.py`

Inputs:

- `lecture_bundles/`
- source cards for the lecture
- slide cards and reading cards together
- raw source files only when the source cards are insufficient

Outputs:

- `source_intelligence/lecture_substrates/W##L#.json`

Minimum schema:

- lecture question
- central learning problem
- source roles
- reading-to-reading relations
- slide-to-reading relations
- core concepts
- core tensions
- likely misunderstandings
- must-carry ideas
- missing-source status

Testing target:

- `W05L1`
- `W06L1`
- one early lecture
- one late lecture

### 5. Course-synthesis builder

Script:

- `scripts/build_personlighedspsykologi_course_synthesis.py`

Inputs:

- all lecture substrates
- existing deterministic glossary/theory/concept graph as supporting context,
  not as authority

Outputs:

- `source_intelligence/course_synthesis.json`

Minimum schema:

- course arc
- theory/tradition map
- concept map
- distinction map
- sideways relations
- lecture clusters
- top-down priorities
- known weak spots or missing-source caveats

### 6. Downward-revision builder

Script:

- `scripts/build_personlighedspsykologi_revised_lecture_substrates.py`

Inputs:

- `course_synthesis.json`
- each lecture substrate

Outputs:

- `source_intelligence/revised_lecture_substrates/W##L#.json`

Minimum schema:

- what matters more after seeing the whole course
- what should be de-emphasized locally
- strongest sideways connections
- top-down course relevance
- revised podcast priorities

### 7. Podcast-substrate builder

Script:

- `scripts/build_personlighedspsykologi_podcast_substrates.py`

Inputs:

- revised lecture substrates
- source cards
- source weighting
- course synthesis

Outputs:

- `source_intelligence/podcast_substrates/W##L#.json`

Minimum schema:

- weekly podcast substrate
- per-reading substrate
- per-slide substrate where useful
- short-podcast substrate
- compact selected concepts
- compact selected tensions
- explicit source-grounding notes

This artifact is the intended boundary into `Prompt Assembly Layer`. NotebookLM
prompts should consume this compact substrate rather than trying to assemble the
whole course-intelligence stack directly.

### 8. Canonical rebuild wrapper

The deterministic rebuild wrapper remains separate. The recursive LLM layer has
its own wrapper.

Canonical command:

```bash
./.venv/bin/python scripts/build_personlighedspsykologi_recursive_source_intelligence.py
```

Required flags:

- `--lectures W05L1,W06L1`
- `--all`
- `--force`
- `--skip-existing`
- `--dry-run`
- `--start-at source-cards|lecture-substrates|course-synthesis|revised-lecture-substrates|podcast-substrates`
- `--stop-after source-cards|lecture-substrates|course-synthesis|revised-lecture-substrates|podcast-substrates`
- `--continue-on-error`
- `--fail-on-missing-key`
- `--no-raw-lecture-source-uploads`
- `--preflight-only`
- `--skip-preflight`

Current dry-run smoke command:

```bash
./.venv/bin/python scripts/build_personlighedspsykologi_recursive_source_intelligence.py --lectures W05L1,W06L1 --dry-run
```

Safer first live pass:

```bash
./.venv/bin/python scripts/build_personlighedspsykologi_recursive_source_intelligence.py --lectures W05L1,W06L1 --stop-after source-cards --continue-on-error
```

After source-card inspection, resume downstream:

```bash
./.venv/bin/python scripts/build_personlighedspsykologi_recursive_source_intelligence.py --lectures W05L1,W06L1 --start-at lecture-substrates
```

Preflight command before uploading source PDFs:

```bash
./.venv/bin/python scripts/build_personlighedspsykologi_recursive_source_intelligence.py --preflight-only
```

Observed 2026-05-05 dry-run plan:

- `W05L1` + `W06L1`
- 9 source cards
- 2 lecture substrates
- 1 partial course synthesis
- 2 downward revisions
- 2 podcast substrates

Live run preconditions:

- `GEMINI_API_KEY`, `GOOGLE_API_KEY`, or local secret-store
  `google.gemini.api_key` must be available
- the key/project must have billing/quota for `gemini-3.1-pro-preview`
- Gemini calls use explicit high thinking and API-level JSON schema
  constraints; do not switch to thinking budgets for Gemini 3.x models
- keep `--skip-existing` unless intentionally rebuilding
- use `--force` only when stale artifacts should be replaced

Current live-run gate:

- `W05L1,W06L1` artifacts validate cleanly and podcast-substrate injection is
  enabled in `notebooklm-podcast-auto/personlighedspsykologi/prompt_config.json`
- next gate is podcast-output quality testing before scaling to more lectures
- no fallback model has been used, because that is a quality/cost decision

Validation command:

```bash
./.venv/bin/python scripts/check_personlighedspsykologi_recursive_artifacts.py --allow-partial
```

### 9. Prompt integration for podcast testing

Do not rewrite the whole prompt system first. Add one narrow integration path:

- if enabled and a podcast substrate exists for the lecture/output type, include a compact
  `Podcast substrate` section in the course-context note
- keep existing prompts as fallback
- add a config flag so substrate use can be enabled/disabled during A/B tests

Implemented in `notebooklm_queue/course_context.py` behind:

```json
{
  "course_context": {
    "podcast_substrate": {
      "enabled": true,
      "max_items": 4
    }
  }
}
```

The default in code remains disabled, but the Personlighedspsykologi
`prompt_config.json` now enables the substrate for generated test podcasts.

Testdaekning:

- `tests/notebooklm_queue/test_course_context.py`

### 10. Testing readiness criteria

The preprocessing system is ready for podcast quality testing when:

- `W05L1` and `W06L1` have source cards, lecture substrates, revised lecture
  substrates, and podcast substrates
- one early and one late lecture have the same artifact coverage
- validators confirm schema shape, hashes, and missing-source handling
- dry-run prompts show compact substrate injection
- generated test podcasts are at least not worse than the simple baseline

For the first production-ish pass, `W03L2` remains allowed as partial because
of the known missing source.

Current blocker:

- the code path and Gemini preflight are ready for the first real test batch,
  but generated LLM artifacts still need to be created and reviewed
