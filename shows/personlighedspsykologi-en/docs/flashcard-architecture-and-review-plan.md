# Flashcard Architecture And Review Plan

Created: 2026-05-26

## Purpose

This plan defines how `personlighedspsykologi` flashcards should be structured,
reviewed, and promoted after the student-synthesis matrix and NotebookLM
candidate runs.

The immediate goal is not to generate more cards. The immediate goal is to
make card review systematic enough that the original matrix deck, existing
NotebookLM variant decks, and the full all-cluster NotebookLM candidate pool
can be compared for quality, coverage, wording, and exam usefulness.

## Source Model

The high-performing student notes are best understood as repeated theory-sheet
matrices, not as simple topic lists and not as only orientation-point tables.

Primary theory rows:

- trækpsykologi
- psykoanalyse
- eksistentiel psykologi
- fænomenologisk psykologi
- humanistisk psykologi
- kritisk psykologi
- socialkonstruktionisme
- poststrukturalisme
- narrativ teori

Repeated knowledge slots:

- hovedpointe
- faghistorisk kontekst
- syn på personlighed, person, or subjektivitet
- main thinkers
- centrale begreber
- metode and evidence style
- orienteringspunkter: essens/kontekst, determination, agency, historicitet
- muligheder and begrænsninger
- cross-theory similarities and differences

The course matrix adds a few row abstractions that are still useful for Freudd:

- `dynamic_personality_development`
- `biosocial_personality_perspectives`
- `personality_functioning_and_pathology`
- `critical_personalism`
- `comparative_theory_analysis`

These added rows should not erase the student-note structure. They should be
handled as course-matrix extensions or cross-cutting rows.

## Target Architecture

Review and generation should use a two-axis model:

1. theory or tradition
2. card family

The review unit is therefore not just "is this card good?" but:

> Does this card improve the `theory x card_family` grid for oral-exam
> preparation?

## Theory Axis

Use these normalized review topics:

| Topic | Matrix rows | Notes |
|---|---|---|
| `traekpsykologi` | `trait_and_assessment_psychology`, `dynamic_personality_development`, `biosocial_personality_perspectives` | Keep traits, stability/change, WTT, behavioral genetics, and evolution together unless a later review shows overload. |
| `personlighedsfunktion-og-patologi` | `personality_functioning_and_pathology` | Course-matrix row, not strongly native to the two original notes. Treat as course-required supplement. |
| `psykoanalyse` | `psychoanalytic_personality_theory` | Include Freud plus French/German distinctions where they change the card's meaning. |
| `faenomenologi-eksistens-humanisme` | `phenomenological_psychology`, `existential_psychology`, `humanistic_psychology` | Shared concern with experience, meaning, subjectivity, growth, and anti-reductionism. |
| `kritisk-psykologi-og-personalisme` | `critical_psychology`, `critical_personalism` | Practice, participation, conditions, action possibilities, and person-level critique. |
| `socialkonstruktion-poststrukturalisme-narrativ` | `sociocultural_poststructural_approaches`, `narrative_psychology` | Language, discourse, power, subjectivation, relation, story, and cultural meaning. |
| `sammenlignende-eksamenssyntese` | `comparative_theory_analysis`, multi-row cards | Cross-theory cards, axis overview cards, and oral-exam answer construction. |

## Card-Family Axis

Every card should be classifiable into one primary family.

| Family | Learner job | Good card pattern |
|---|---|---|
| `hovedpointe` | Recall the tradition's core claim in one exam-usable move. | "Hvad er hovedpointen i trækpsykologi?" |
| `historisk-kontekst` | Place the tradition historically without turning the card into trivia. | "Hvilket problem reagerer humanistisk psykologi mod?" |
| `personbegreb` | State the model of person, personality, self, or subjectivity. | "Hvilket personbegreb ligger i psykoanalyse?" |
| `begrebsmekanisme` | Explain how a central concept works inside the theory. | "Hvilken funktion har Big Five i trækpsykologiens personlighedsforståelse?" |
| `taenkerdistinktion` | Distinguish thinkers when the distinction matters for theory use. | "Hvordan forskyder Lacan/Laplanche psykoanalysen i forhold til Freud?" |
| `metode-evidens` | Recall what kind of evidence, method, or analysis the tradition trusts. | "Hvorfor passer faktoranalyse til trækpsykologi?" |
| `orienteringspunkt` | Place a theory on one orientation axis. | "Hvor placerer narrativ psykologi agency?" |
| `akse-sammenligning` | Compare theories along one orientation axis. | "Hvordan adskiller trækpsykologi og kritisk psykologi sig på essens/kontekst?" |
| `mulighed-begraensning` | Recall what the theory makes possible and what it hides. | "Hvad gør poststrukturalisme synligt, som trækpsykologi risikerer at skjule?" |
| `teori-sammenligning` | Compare two or more traditions in an exam-ready way. | "Hvordan kan humanistisk og eksistentiel psykologi sammenlignes?" |
| `eksamenstrap` | Correct an attractive but wrong simplification. | "Hvorfor er socialkonstruktionisme ikke bare 'alt er frit valgt'?" |
| `svar-konstruktion` | Train how to build an oral-exam answer. | "Hvordan kan du bygge et svar om agency på tværs af tre teorier?" |

The existing Freudd categories can remain learner-facing groupings for now, but
the review taxonomy should be more precise than the visible categories.

Mapping to current Freudd categories:

| Review family | Current category |
|---|---|
| `hovedpointe`, `historisk-kontekst`, `personbegreb`, `taenkerdistinktion` | `personbegreb` |
| `begrebsmekanisme` | `personbegreb` or `metode-og-evidens`, depending on concept |
| `metode-evidens` | `metode-og-evidens` |
| `orienteringspunkt`, `akse-sammenligning` | `orienteringspunkter` |
| `mulighed-begraensning` | `styrker-og-begraensninger` |
| `teori-sammenligning` | `sammenligninger` |
| `eksamenstrap` | `eksamenstraps` |
| `svar-konstruktion` | `sammenligninger` or `eksamenstraps` |

## Coverage Targets

The goal is not equal card counts everywhere. The goal is useful retrieval
coverage.

Minimum target per primary tradition:

- 1 `hovedpointe`
- 1 `personbegreb`
- 2-4 `begrebsmekanisme`
- 1 `metode-evidens`
- 4 `orienteringspunkt`, one per axis
- 1 `mulighed-begraensning`
- 1 `eksamenstrap`
- 2 high-value comparison cards

Additional target for dense traditions:

- trækpsykologi: cards for Big Five/HEXACO, WTT, stability/change,
  factor analysis, biological/cultural explanation
- psykoanalyse: cards for Freud, Lacan/Laplanche, unconscious, repression,
  drive, subject decentering, clinical method
- social/post/narrative: cards that separate social constructionism,
  poststructuralism, and narrative psychology instead of collapsing them into
  generic "language creates reality" cards
- critical psychology: cards for conditions, participation, action
  possibilities, expansive/restrictive agency, and method/practice standpoint

Maximum pressure:

- avoid flooding Freudd with many near-duplicate concept cards
- prefer one excellent comparison card over three parallel shallow cards
- keep answer backs short enough for practice, normally 1-4 sentences or 2-4
  bullets

## Quality Rubric

Each candidate card should be scored against these criteria.

Use a 0-2 scale unless a later implementation needs finer grading:

- `source_fidelity`: does the card fit the validated matrix and student-note
  synthesis without inventing claims?
- `exam_utility`: would this help Oskar answer an oral-exam question?
- `atomicity`: does the card ask one thing, not three hidden questions?
- `specificity`: does it avoid generic definition-only wording?
- `wording_quality`: is the Danish clear, compact, and learnable?
- `coverage_value`: does it fill a gap in the `theory x family` grid?
- `duplicate_risk`: does it meaningfully differ from existing Freudd cards?
- `category_fit`: does its visible Freudd category and internal family fit?
- `safety`: no student names, local paths, source IDs, or note-provenance leak.

Decision labels:

- `promote`: strong, fills a real slot, little editing needed
- `promote_after_edit`: useful but needs wording, shortening, or precision
- `merge_with_existing`: better as a rewrite or addition to an existing card
- `keep_as_reference`: useful insight but not a flashcard yet
- `reject`: duplicate, vague, unsafe, wrong, too broad, or too low value

## Comparison Inputs

Historical review inputs compared four card pools:

1. archived canonical matrix/Gemini-style deck:
   `shows/personlighedspsykologi-en/flashcards/archive/retired-live-decks-2026-05-26/eksamensmatrix-personlighedspsykologi.json`
2. archived first NotebookLM variants deck:
   `shows/personlighedspsykologi-en/flashcards/archive/retired-live-decks-2026-05-26/notebooklm-varianter-personlighedspsykologi.json`
3. archived independent NotebookLM variants deck:
   `shows/personlighedspsykologi-en/flashcards/archive/retired-live-decks-2026-05-26/notebooklm-uafhaengige-varianter-personlighedspsykologi.json`
4. full all-cluster NotebookLM candidates:
   `notebooklm-podcast-auto/personlighedspsykologi/flashcard_lab/runs/full-matrix-20260526-notebooklm-independent/candidates/*.candidates.json`

Current live Freudd state:

- only live deck:
  `shows/personlighedspsykologi-en/flashcards/notebooklm-fuld-matrix-personlighedspsykologi.json`
- live card count: 234
- source policy: include `candidate` and `needs_review` cards from the newest
  full NotebookLM run; exclude `auto_rejected` cards

Current known imbalance:

- canonical matrix deck: 152 cards; strong orientation/trap/comparison
  baseline
- first NotebookLM variants deck: 79 cards; heavily skewed toward
  `personbegreb`
- independent NotebookLM variants deck: 74 cards; also skewed toward
  `personbegreb`
- full all-cluster run: 259 normalized candidates; not yet reviewed against
  this architecture

## Implementation Plan

### Phase 1: Architecture Classifier

Build a local review tool that reads all candidate/card pools and assigns:

- source pool
- theory topic
- matrix theory IDs
- visible Freudd category
- review family
- front/back length metrics
- duplicate-nearest existing cards
- safety warnings

The first implementation can use deterministic keyword/rule classification.
LLM review can come after the deterministic grid exists.

### Phase 2: Coverage Grid Report

Generate a Markdown and JSON report:

- cards by `theory_topic x review_family`
- gaps against the coverage targets
- overcrowded cells
- likely duplicates across all decks/candidates
- overlong or vague cards
- cards that are probably in the wrong category
- NotebookLM cards with high potential added value

This phase should not modify Freudd decks.

### Phase 3: Single-Call LLM Review

Use one Gemini 3.1 Pro review call only after the deterministic report is
ready.

The LLM input should include:

- the architecture/rubric summary
- current coverage grid
- candidate cards selected for possible promotion
- nearest existing card for each selected candidate
- relevant matrix rows or compact row excerpts

The LLM should return structured decisions using the labels above. It should
not be asked to generate a new deck from scratch.

### Phase 4: Promotion Strategy

After review, choose one of three promotion paths:

1. patch canonical matrix deck wording and keep IDs stable
2. create a new curated "best-of exam practice" deck
3. keep canonical and variants separate, but hide or de-emphasize weaker
   variant decks in Freudd

Do not decide this before seeing the coverage report.

## Acceptance Criteria

The comparison/review phase is complete only when:

- every existing and candidate card is mapped to `theory_topic` and
  `review_family`
- the report identifies missing and overcrowded `theory x family` cells
- duplicates are measured across original, variant, independent, and full-run
  candidates
- the report separates wording issues from conceptual-quality issues
- Gemini review, if used, is grounded in a compact candidate subset and the
  explicit rubric
- no new learner-facing deck is promoted without a recorded decision artifact

## Non-Goals

- Do not regenerate NotebookLM cards before the coverage report.
- Do not import raw NotebookLM candidates directly into Freudd.
- Do not treat student-note wording as learner-facing copy by default.
- Do not use notebook cluster names as the learner-facing topic taxonomy.
- Do not optimize for maximum card count.

## Recommended Next Step

Implement Phase 1 and Phase 2 as a local comparison/report script. The report
should be reviewed before any Gemini call or Freudd deck promotion.

Detailed implementation plan:

- `shows/personlighedspsykologi-en/docs/flashcard-review-implementation-plan.md`
