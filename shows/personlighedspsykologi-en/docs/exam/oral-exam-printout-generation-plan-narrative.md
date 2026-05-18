# Plan for manglende printouts til narrativ mundtlig eksamen

Denne plan er en arbejdsplan for printout-produktion. Den ændrer ikke den rene
læseprioritering i `oral-exam-printout-priority-narrative.md`.

Planen er lavet efter oprydningen hvor nye test-genererede printouts blev fjernet igen,
og hvor 3-delt legacy-output ikke længere tæller som dækket.

## Grundregel

Kør ikke ny live-generation før systemet igen er markeret klart.

Et printout tæller kun som dækket, hvis der findes et komplet 5-delt bundle:

- `00-cover`
- `01-reading-guide`
- `02-active-reading`
- `03-abridged-version`
- `04-consolidation-sheet`

Ældre 3-delt legacy-output skal ikke bruges som statusgrundlag.

## Readiness-gates

Før live-generation:

1. Kør relevante printout-engine tests.
2. Kør dry-run for den konkrete gruppe.
3. Kør én enkelt kilde som smoke test.
4. Bekræft at outputtet har alle fem PDF-dele.
5. Scan derefter status igen før næste gruppe.

Hvis en kilde fejler validering, så stop gruppen og ret systemet før næste batch.

## Aktuel status

Aktiv prioriteret liste:

- 36 tekster i alt.
- 19 tekster har komplet brugbart printout-output.
- 17 tekster mangler komplet 5-delt printout.
- Kontrastbaseline er dækket og skal ikke prioriteres nu.
- W11L2 narrative tekster er ikke en ny printout-opgave, fordi de allerede er eksamensanker.

## Gruppe 1: Lav først

Disse er både højest prioriterede fagligt og mangler printout.

1. W10L2: Foucault (1997)  
   `w10l2-foucault-1997-92cd121d`
2. W11L1: Grundbog kapitel 11 - Postpsykologisk subjektiveringsteori  
   `w11l1-grundbog-kapitel-11-postpsykologisk-subjektiveri-3557aeb2`
3. W06L1: Grundbog kapitel 04 - Fænomenologisk personlighedspsykologi  
   `w06l1-grundbog-kapitel-4-f-nomenologisk-personlighedsp-1afa74d2`

Bemærk: W06L1 Grundbog kapitel 04 var tidligere legacy-dækket, men legacy-output er nu
slettet og skal erstattes af et komplet 5-delt bundle.

## Gruppe 2: Lav derefter

Disse er næste aktive læsegruppe.

1. W06L1: Moeskær Hansen & Roald (2022)  
   `w06l1-moesk-r-hansen-and-roald-2022-b7aec462`
2. W06L1: Spinelli (2005)  
   `w06l1-spinelli-2005-b2f76e93`
3. W10L1: Mitchell (2015)  
   `w10l1-mitchell-2015-bc690b36`
4. W10L1: Bjerrum Nielsen & Rudberg (2006)  
   `w10l1-bjerrum-nielsen-and-rudberg-2006-39335ee6`

## Gruppe 3: Lav hvis der er tid

Disse er relevante, men skal ikke blokere gruppe 1 og 2.

1. W05L2: Grundbog kapitel 07 - Nyere psykoanalytiske teorier  
   `w05l2-grundbog-kapitel-7-nyere-psykoanalytiske-teorier-fda84b6a`
2. W07L1: Jacobsen (2021)  
   `w07l1-jacobsen-2021-26129bff`
3. W04L1: Gammelgaard (2007)  
   `w04l1-gammelgaard-2007-bcbdbec2`
4. W05L1: Ricoeur (1981)  
   `w05l1-ricoeur-1981-19a5343f`
5. W04L2: Laplanche (1970)  
   `w04l2-laplanche-1970-968862d5`
6. W05L1: Gammelgaard (2010)  
   `w05l1-gammelgaard-2010-e6baff8b`
7. W05L2: Køppe (1992)  
   `w05l2-k-ppe-1992-9a474402`

## Gruppe 4: Bro- og overblik

Lav disse sidst eller kun selektivt.

1. W04L2: Lacan (1966)  
   `w04l2-lacan-1966-2d720f56`
2. W04L1: Freud (1973/1933)  
   `w04l1-freud-1973-1933-98cd9920`
3. W05L2: Andkjær Olsen & Køppe (1991a + 1991b)  
   `w05l2-andkj-r-olsen-and-k-ppe-1991a-1991b-720b5d8e`

## Allerede dækket i den aktive liste

Disse skal ikke genereres igen, medmindre der bevidst laves en ny kvalitetsrunde:

- W09L1: Grundbog kapitel 10 - Kritisk psykologi
- W08L2: Holzkamp (1982)
- W12L1: Grundbog kapitel 08 - Personlighed, subjektivitet og historicitet
- W09L1: Holzkamp (2013)
- W12L1: Elias (2000)
- W08L2: Tolman (2009)
- W08L1: Lamiell (2021)
- W07L2: Giorgi (2005)
- W08L1: Laux et al (2010)
- W07L2: Evans (1975)
- W09L1: Dreier (1999)
- W01L2: Koutsoumpis (2025)
- W02L2: Bleidorn et al. (2022)
- W01L1: Grundbog kapitel 01 - Introduktion til personlighedspsykologi
- W02L1: Columbus & Strandsbjerg (2025)
- W02L2: Li & Wilt (2025)
- W03L1: Lu, Benet-Martínez & Wang (2023)
- W02L1: Zettler et al. (2020)
- W01L2: Phan et al. (2024)

## Kommandoform når systemet er klart

Brug eksplicitte `--source-id`-kald i stedet for en løs lecture-batch, så der ikke startes
uønsket produktion.

Dry-run for gruppe 1:

```bash
python3 scripts/build_personlighedspsykologi_printouts.py \
  --provider gemini \
  --source-family reading \
  --dry-run \
  --source-id w10l2-foucault-1997-92cd121d \
  --source-id w11l1-grundbog-kapitel-11-postpsykologisk-subjektiveri-3557aeb2 \
  --source-id w06l1-grundbog-kapitel-4-f-nomenologisk-personlighedsp-1afa74d2
```

Live-generation for samme gruppe må først køres efter readiness-gates:

```bash
python3 scripts/build_personlighedspsykologi_printouts.py \
  --provider gemini \
  --source-family reading \
  --continue-on-error \
  --source-id w10l2-foucault-1997-92cd121d \
  --source-id w11l1-grundbog-kapitel-11-postpsykologisk-subjektiveri-3557aeb2 \
  --source-id w06l1-grundbog-kapitel-4-f-nomenologisk-personlighedsp-1afa74d2
```
