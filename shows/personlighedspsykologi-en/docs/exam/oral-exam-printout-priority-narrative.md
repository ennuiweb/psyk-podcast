# Prioriteret printoutlæsning til mundtlig eksamen

Denne fil opdateres af `scripts/build_personlighedspsykologi_exam_priority_plan.py`. Den dokumenterer både planen og den præcise vurderingsmetode, så prioriteringen kan genberegnes, når kursusartefakterne ændrer sig.

Der bruges ingen faste kalenderdatoer. Arbejd i relative læsedage og prioritetspakker.

## Implementeret plan

Målet er at prioritere ikke-narrative tekster, fordi narrativ psykologi allerede er gennemgået. W11L2 bevares som eksamensanker i datasættet, men fjernes fra aktiv ny-læsning.

Pipeline-designet løser den vigtigste svaghed i den tidligere manuelle plan: prioriteringen styres af faglig eksamensværdi frem for om et materiale allerede findes i en bestemt teknisk outputform. Derfor viser planen kun hvornår en tekst bør ind i læsearbejdet.

## Datagrundlag

- `shows/personlighedspsykologi-en/exam_priority_config.narrative.json`
- `shows/personlighedspsykologi-en/source_weighting.json`
- `shows/personlighedspsykologi-en/course_concept_graph.json`
- `shows/personlighedspsykologi-en/source_intelligence/course_synthesis.json`
- `shows/personlighedspsykologi-en/source_intelligence/revised_lecture_substrates`

## Vurderingsmetode

For hver læsetekst beregnes én synlig prioritetsscore:

- `academic_score`: kildevægtning, anchor/major-status, teori- og begrebsrelevans, distinktionsstøtte, kursussyntese og revised lecture-substrate signaler.

Den synlige plan bruger derfor faglig prioritet og relativ læserytme.

## Scorekomponenter

- `source_weight`: eksisterende repo-vægtning fra `source_weighting.json`.
- `theory_bonus` og `term_bonus`: narrativ relevans, socialkonstruktionisme, subjektivering, kritisk psykologi, mening, historicitet og baseline-kontraster.
- `direct_distinction_bonus`: støtte til centrale mundtlige akser i `course_concept_graph.json`.
- `lecture_context_bonus`: signaler som `narrative psychology`, `subjectivation`, `historicity`, `agency`, `discourse` og `deconstruction` i revised lecture substrates.

## Start her

Disse tekster har størst eksamensværdi for at kunne tale om narrativ psykologi gennem kontrast, forudsætning og metaperspektiv.

| Prioritet | Tekst | Faglig score | Hvorfor |
|---|---|---:|---|
| 1 | W10L2: Foucault (1997) | 467 | anchor (104 i kildevægtning); teori: sociocultural_poststructural_approaches, critical_psychology; begreb: subjectivation; distinktion: inner essence vs subjectivation, individual problem vs structural condition |
| 2 | W11L1: Grundbog kapitel 11 - Postpsykologisk subjektiveringsteori | 464 | anchor (109 i kildevægtning); teori: sociocultural_poststructural_approaches, critical_psychology; begreb: subjectivation; distinktion: inner essence vs subjectivation, individual problem vs structural condition |
| 3 | W09L1: Grundbog kapitel 10 - Kritisk psykologi | 432 | anchor (102 i kildevægtning); teori: sociocultural_poststructural_approaches, critical_psychology; begreb: critical_psychology; distinktion: individual problem vs structural condition, person vs variable profile |
| 4 | W08L2: Holzkamp (1982) | 405 | anchor (97 i kildevægtning); teori: sociocultural_poststructural_approaches, critical_psychology; begreb: critical_psychology; distinktion: individual problem vs structural condition, person vs variable profile |
| 5 | W12L1: Grundbog kapitel 08 - Personlighed, subjektivitet og historicitet | 403 | anchor (109 i kildevægtning); teori: narrative_psychology, comparative_theory_analysis, dynamic_personality_development; begreb: stability_and_change; distinktion: trait vs state |
| 6 | W09L1: Holzkamp (2013) | 383 | anchor (91 i kildevægtning); teori: sociocultural_poststructural_approaches, critical_psychology; begreb: critical_psychology; distinktion: person vs variable profile |
| 7 | W12L1: Elias (2000) | 369 | anchor (101 i kildevægtning); teori: narrative_psychology, comparative_theory_analysis, dynamic_personality_development; begreb: stability_and_change; lektionssignal: subjectivation, historicity, orientation points |
| 8 | W06L1: Grundbog kapitel 04 - Fænomenologisk personlighedspsykologi | 364 | anchor (112 i kildevægtning); teori: narrative_psychology, phenomenological_psychology, humanistic_psychology; begreb: meaning_making, first_person_perspective; distinktion: inner depth vs lived experience |

## Læs derefter

Disse tekster kommer lige efter startpakken og udbygger praksis, agens, historicitet, erfaring og kritisk sammenligning.

| Prioritet | Tekst | Faglig score | Hvorfor |
|---|---|---:|---|
| 1 | W08L2: Tolman (2009) | 361 | anchor (91 i kildevægtning); teori: sociocultural_poststructural_approaches, critical_psychology; begreb: critical_psychology; distinktion: person vs variable profile |
| 2 | W08L1: Lamiell (2021) | 360 | anchor (98 i kildevægtning); teori: critical_psychology, critical_personalism, trait_and_assessment_psychology; begreb: critical_personalism; distinktion: person vs variable profile |
| 3 | W07L2: Giorgi (2005) | 354 | anchor (98 i kildevægtning); teori: narrative_psychology, phenomenological_psychology, humanistic_psychology; begreb: meaning_making; distinktion: growth vs deficit |
| 4 | W06L1: Moeskær Hansen & Roald (2022) | 336 | anchor (104 i kildevægtning); teori: narrative_psychology, phenomenological_psychology, humanistic_psychology; begreb: meaning_making; distinktion: inner depth vs lived experience |
| 5 | W06L1: Spinelli (2005) | 336 | anchor (104 i kildevægtning); teori: narrative_psychology, phenomenological_psychology, humanistic_psychology; begreb: meaning_making; distinktion: inner depth vs lived experience |
| 6 | W08L1: Laux et al (2010) | 304 | major (88 i kildevægtning); teori: critical_psychology, critical_personalism, trait_and_assessment_psychology; begreb: critical_personalism; lektionssignal: narrative psychology, orientation points, agency |
| 7 | W07L2: Evans (1975) | 301 | anchor (101 i kildevægtning); teori: phenomenological_psychology, humanistic_psychology; begreb: first_person_perspective; distinktion: growth vs deficit |
| 8 | W09L1: Dreier (1999) | 295 | major (81 i kildevægtning); teori: critical_psychology, dynamic_personality_development; begreb: person_situation_interplay; lektionssignal: subjectivation, orientation points, agency |
| 9 | W10L1: Mitchell (2015) | 288 | anchor (96 i kildevægtning); teori: sociocultural_poststructural_approaches; distinktion: individual problem vs structural condition; lektionssignal: narrative psychology, subjectivation, historicity |
| 10 | W10L1: Bjerrum Nielsen & Rudberg (2006) | 285 | anchor (93 i kildevægtning); teori: sociocultural_poststructural_approaches; distinktion: individual problem vs structural condition; lektionssignal: narrative psychology, subjectivation, historicity |

## Udbyg hvis der er tid

Disse tekster er stadig relevante, men bør først tages efter de to første faser.

| Prioritet | Tekst | Faglig score | Hvorfor |
|---|---|---:|---|
| 1 | W05L2: Grundbog kapitel 07 - Nyere psykoanalytiske teorier | 228 | anchor (98 i kildevægtning); teori: psychoanalytic_personality_theory; distinktion: inner depth vs lived experience, growth vs deficit; lektionssignal: subjectivation, historicity, orientation points |
| 2 | W07L1: Jacobsen (2021) | 222 | anchor (98 i kildevægtning); teori: phenomenological_psychology, humanistic_psychology; lektionssignal: narrative psychology, historicity, orientation points |
| 3 | W04L1: Gammelgaard (2007) | 219 | anchor (93 i kildevægtning); teori: psychoanalytic_personality_theory; distinktion: growth vs deficit; lektionssignal: narrative psychology, historicity, orientation points |
| 4 | W05L1: Ricoeur (1981) | 199 | anchor (93 i kildevægtning); teori: psychoanalytic_personality_theory; lektionssignal: narrative psychology, historicity, orientation points |
| 5 | W04L2: Laplanche (1970) | 193 | anchor (93 i kildevægtning); teori: psychoanalytic_personality_theory; lektionssignal: historicity, orientation points, agency |
| 6 | W05L1: Gammelgaard (2010) | 181 | major (87 i kildevægtning); teori: psychoanalytic_personality_theory; lektionssignal: narrative psychology, historicity, orientation points |
| 7 | W01L2: Koutsoumpis (2025) | 180 | major (80 i kildevægtning); teori: trait_and_assessment_psychology; begreb: personality_assessment; lektionssignal: orientation points, deconstruction, critical |
| 8 | W05L2: Køppe (1992) | 180 | anchor (90 i kildevægtning); teori: psychoanalytic_personality_theory; lektionssignal: subjectivation, historicity, orientation points |

## Kontrastbaseline

Tidlige træk-, assessment- og biosociale tekster skal primært bruges som kontrast til narrativ psykologi, ikke som dybdelæsningskerne.

| Prioritet | Tekst | Faglig score | Hvorfor |
|---|---|---:|---|
| 1 | W02L2: Bleidorn et al. (2022) | 382 | anchor (104 i kildevægtning); teori: narrative_psychology, comparative_theory_analysis, dynamic_personality_development; begreb: stability_and_change, personality_traits; distinktion: trait vs state |
| 2 | W01L1: Grundbog kapitel 01 - Introduktion til personlighedspsykologi | 371 | anchor (103 i kildevægtning); teori: narrative_psychology, comparative_theory_analysis, dynamic_personality_development; begreb: stability_and_change; distinktion: trait vs state |
| 3 | W02L1: Columbus & Strandsbjerg (2025) | 319 | anchor (91 i kildevægtning); teori: narrative_psychology, dynamic_personality_development, trait_and_assessment_psychology; begreb: personality_states, personality_traits; lektionssignal: subjectivation, orientation points, agency |
| 4 | W02L2: Li & Wilt (2025) | 318 | major (88 i kildevægtning); teori: narrative_psychology, critical_psychology, dynamic_personality_development; begreb: person_situation_interplay, personality_traits; lektionssignal: narrative psychology, orientation points, agency |
| 5 | W03L1: Lu, Benet-Martínez & Wang (2023) | 241 | anchor (97 i kildevægtning); teori: narrative_psychology, biosocial_personality_perspectives; begreb: culture_and_personality; lektionssignal: orientation points, meaning, critical |
| 6 | W02L1: Zettler et al. (2020) | 237 | anchor (97 i kildevægtning); teori: trait_and_assessment_psychology; lektionssignal: subjectivation, orientation points, agency |

## Bro- og overblikstekster

Disse tekster har faglig værdi, men bør læses selektivt eller efter de højere prioriterede kategorier.

| Prioritet | Tekst | Faglig score | Hvorfor |
|---|---|---:|---|
| 1 | W04L2: Lacan (1966) | 169 | major (81 i kildevægtning); teori: psychoanalytic_personality_theory; lektionssignal: historicity, orientation points, agency |
| 2 | W04L1: Freud (1973/1933) | 166 | major (80 i kildevægtning); lektionssignal: narrative psychology, historicity, orientation points |
| 3 | W01L2: Phan et al. (2024) | 163 | major (83 i kildevægtning); lektionssignal: orientation points, deconstruction, critical |
| 4 | W05L2: Andkjær Olsen & Køppe (1991a + 1991b) | 151 | major (83 i kildevægtning); lektionssignal: subjectivation, historicity, orientation points |

## Allerede dækket eksamensanker

Narrative tekster holdes synlige som sammenligningsanker, men de er ikke en ny læseopgave i denne plan.

| Prioritet | Tekst | Faglig score | Hvorfor |
|---|---|---:|---|
| 1 | W11L2: Grundbog kapitel 09 - Narrative teorier | 503 | anchor (119 i kildevægtning); teori: narrative_psychology, comparative_theory_analysis, dynamic_personality_development; begreb: narrativity, culture_and_personality, stability_and_change; distinktion: inner essence vs subjectivation, trait vs state |
| 2 | W11L2: Bruner (1999) | 500 | anchor (110 i kildevægtning); teori: narrative_psychology, comparative_theory_analysis, phenomenological_psychology; begreb: narrativity, meaning_making, culture_and_personality; distinktion: inner essence vs subjectivation |
| 3 | W11L2: McAdams & Pals (2006) | 490 | anchor (104 i kildevægtning); teori: narrative_psychology, comparative_theory_analysis, dynamic_personality_development; begreb: narrativity, culture_and_personality, personality_traits; distinktion: inner essence vs subjectivation, trait vs state |
| 4 | W11L2: Raggatt (2002) | 355 | anchor (101 i kildevægtning); teori: narrative_psychology, comparative_theory_analysis, dynamic_personality_development; begreb: stability_and_change; distinktion: trait vs state |

## Relativ læserytme

Brug 12 relative læsedage uden faste datoer:

| Læsedage | Fokus | Output |
|---|---|---|
| 1-3 | Start her | De stærkeste broer og kontraster til narrativ psykologi |
| 4-6 | Læs derefter | Sammenligningsmatrix mod narrativ psykologi |
| 7-8 | Udbyg hvis der er tid | Agens/praksis/mening koblet til de fire orienteringspunkter |
| 9 | Kontrastbaseline | Træk, stabilitet og assessment som modpol |
| 10 | Bro- og overblikstekster | Fyld svage huller uden perfektionisme |
| 11 | Mundtlig syntese | Tre stærke sammenligninger på tværs af teorier |
| 12 | Prøvefremlæggelse | 8-10 minutters svar med narrativ psykologi som centrum |

## Reproducerbarhed

Genskab planen med:

```bash
python3 scripts/build_personlighedspsykologi_exam_priority_plan.py
```

Spring rendering af onepage-PDF'en over med:

```bash
python3 scripts/build_personlighedspsykologi_exam_priority_plan.py --no-pdf
```
