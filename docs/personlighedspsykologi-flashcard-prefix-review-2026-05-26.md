# Personlighedspsykologi Flashcard Prefix Review

Date: 2026-05-26

Scope: 100 deterministic random cards from the live deck
`shows/personlighedspsykologi-en/flashcards/notebooklm-fuld-matrix-personlighedspsykologi.json`.

Sampling method: Python `random.Random(20260526).sample(cards, 100)`.

Review method: manual inspection of the card front text. No Gemini/LLM card
review call was used. The question reviewed here is narrow: can the leading
`X:` prefix be removed directly without damaging the front's meaning?

## Summary

Out of 100 sampled cards:

- 60 had no leading prefix.
- 40 had a leading prefix before the first colon.
- 36 of those 40 can have the prefix removed directly.
- 4 should not have the prefix removed directly, because the prefix supplies
  the referent for phrases like "denne tilgang", "denne tradition", or a topic
  that is otherwise absent from the question.

Prefix counts in the sample:

| Prefix | Count |
|---|---:|
| None | 60 |
| `Eksamenstrap` | 9 |
| `Begreb` | 7 |
| `Sammenligning` | 7 |
| `Eksamensfælde` | 3 |
| `Personbegreb` | 3 |
| `Biosociale perspektiver` | 2 |
| `Orienteringspunkt` | 2 |
| `Personlighedsfunktion` | 2 |
| `Agency` | 1 |
| `Begrænsning` | 1 |
| `Historicitet` | 1 |
| `Metode` | 1 |
| `Orienteringspunkter` | 1 |

## Recommendation

For learner-facing cards, remove pure card-type prefixes directly:
`Begreb:`, `Metode:`, `Personbegreb:`, `Sammenligning:`, `Eksamenstrap:`,
`Eksamensfælde:`, `Orienteringspunkt:`, `Orienteringspunkter:`, `Agency:`,
`Historicitet:`, `Kritik:`, `Styrke:`, `Styrker og begrænsninger:`, and
`Begrænsning:`.

Do not blindly remove theory/topic prefixes such as `Biosociale perspektiver:`
or context prefixes such as `Personlighedsfunktion:` when the remaining
question contains "denne tilgang", "denne tradition", or otherwise needs the
prefix as its subject. Those cards should be rewritten so the context is inside
the question instead.

Suggested implementation rule:

- If the prefix is a known category label and the post-colon text still has a
  clear subject, remove the prefix.
- If the prefix is a theory/topic label and the post-colon text uses a deictic
  phrase such as "denne tilgang" or "denne tradition", preserve meaning by
  rewriting, not deleting.
- For term-prompt fronts such as `Begreb: Den leksikale hypotese`, deletion is
  semantically safe, but the nicer final polish is often to rewrite as a real
  question.

## Full-Deck Follow-Up

After the 100-card sample, the remaining 219 live cards were inspected by
complete prefix inventory over all 319 cards. The full deck had 127 leading
prefixes across 18 prefix types before cleanup.

Implementation result:

- 118 prefixes were removed safely by
  `notebooklm_queue/personlighedspsykologi_full_notebooklm_flashcards.py`.
- 9 prefixes were intentionally preserved because direct removal would make the
  question underspecified.
- The live deck still has 319 cards.
- The coverage audit still reports 0 `missing`, 0 `weak`, and 0 high-priority
  missing/weak units.

Removed prefix counts:

| Prefix | Removed |
|---|---:|
| `Sammenligning` | 31 |
| `Begreb` | 20 |
| `Eksamenstrap` | 19 |
| `Eksamensfælde` | 9 |
| `Metode` | 7 |
| `Orienteringspunkt` | 6 |
| `Personbegreb` | 5 |
| `Begrænsning` | 4 |
| `Styrke` | 4 |
| `Agency` | 3 |
| `Orienteringspunkter` | 3 |
| `Trækpsykologi` | 3 |
| `Historicitet` | 2 |
| `Kritik` | 1 |
| `Styrker og begrænsninger` | 1 |

Preserved prefixes:

| Prefix | Preserved | Reason |
|---|---:|---|
| `Biosociale perspektiver` | 3 | The prefix names the theory frame; direct deletion would make at least some questions ambiguous. |
| `Personlighedsfunktion` | 3 | The prefix names the approach behind phrases like "denne tilgang" or generic "funktionsniveau". |
| `Trækpsykologi` | 2 | Preserved only where the remaining question says "teorien" or "denne tradition". |
| `Personlighedsfunktion og patologi` | 1 | The remaining question says "denne nyere tradition", so the prefix is the referent. |

Implementation note: removing `Begreb:` exposed that the coverage audit was
partly relying on the card-type word rather than conceptual Danish wording for
critical psychology central concepts. The audit now has explicit Danish aliases
for central concepts such as `subjectivity`/`subjektivitet`,
`participation`/`deltagelse`, `conditions`/`betingelser`, and `everyday
life`/`hverdagslivet`.

## Sample Review

| # | Card ID | Prefix | Can remove directly? | Rationale |
|---:|---|---|---|---|
| 1 | `nlm-measurement-development-pathology-5b1752aad85a9c57` | `Begreb` | Yes | Pure card-type label; the question still asks about selvstyring. |
| 2 | `nlm-gap-repair-comparisons-traps-d3c35cc95a28119f` | None | N/A | No leading prefix. |
| 3 | `nlm-coverage-closure-phenomenological-psychology-source-note-basis-anes-tabel` | None | N/A | No leading prefix. |
| 4 | `nlm-measurement-development-pathology-670a9ddae19a6fff` | `Eksamenstrap` | Yes | The remaining question still names the misunderstanding. |
| 5 | `nlm-global-calibration-synthesis-b5fe369e07ed1a7f` | None | N/A | No leading prefix. |
| 6 | `nlm-psychoanalysis-experience-humanism-01e8b5492fab89ba` | `Sammenligning` | Yes | The question already asks what separates two traditions. |
| 7 | `nlm-gap-repair-source-basis-e16ace6e8b0eb711` | None | N/A | No leading prefix. |
| 8 | `nlm-global-calibration-synthesis-bb9d79a78ceb1644` | None | N/A | No leading prefix. |
| 9 | `nlm-global-calibration-synthesis-487ba41f16cf2c53` | None | N/A | No leading prefix. |
| 10 | `nlm-global-calibration-synthesis-f9e88cc1a0f398a8` | None | N/A | No leading prefix. |
| 11 | `nlm-gap-repair-source-basis-4e9620e61e292f81` | None | N/A | No leading prefix. |
| 12 | `nlm-oral-exam-comparison-workshop-37386fa61ba1195b` | `Eksamenstrap` | Yes | The remaining question is still a complete contrast question. |
| 13 | `nlm-global-calibration-synthesis-7e6e1be5e9fae563` | `Begreb` | Yes | The label is only a card type; the term prompt remains meaningful. |
| 14 | `nlm-coverage-closure-sociocultural-poststructural-approaches-source-note-basi-bc8fbe589469746f` | None | N/A | No leading prefix. |
| 15 | `nlm-critical-sociocultural-narrative-d21344de4dfff01e` | `Personbegreb` | Yes | The question already names narrativ psykologi and personen. |
| 16 | `nlm-psychoanalysis-experience-humanism-5a980619a78aa778` | None | N/A | No leading prefix. |
| 17 | `nlm-global-calibration-synthesis-ff3eab30ac6eb1dd` | None | N/A | No leading prefix. |
| 18 | `nlm-critical-sociocultural-narrative-e2b395a19dae0af8` | `Sammenligning` | Yes | The remaining question is explicitly comparative. |
| 19 | `nlm-global-calibration-synthesis-db08a0ab93ac5af6` | None | N/A | No leading prefix. |
| 20 | `nlm-psychoanalysis-experience-humanism-c200e1804913e43a` | None | N/A | No leading prefix. |
| 21 | `nlm-gap-repair-comparisons-traps-c8fd48abf3cea3e8` | None | N/A | No leading prefix. |
| 22 | `nlm-critical-sociocultural-narrative-93a975f4b37d4c78` | `Agency` | Yes | The remaining question names handlepotentiale in kritisk psykologi. |
| 23 | `nlm-gap-repair-comparisons-traps-da7507ed50267775` | None | N/A | No leading prefix. |
| 24 | `nlm-global-calibration-synthesis-6deda0893612a330` | `Eksamensfælde` | Yes | The remaining question still names agency and kritisk psykologi. |
| 25 | `nlm-global-calibration-synthesis-e8f0683fc8da1a45` | None | N/A | No leading prefix. |
| 26 | `nlm-gap-repair-source-basis-25df777c05d1c84c` | None | N/A | No leading prefix. |
| 27 | `nlm-gap-repair-comparisons-traps-fb614e1ab4e8766b` | None | N/A | No leading prefix. |
| 28 | `nlm-global-calibration-synthesis-159264c7c9d32790` | `Eksamensfælde` | Yes | The remaining question still contains the misconception. |
| 29 | `nlm-measurement-development-pathology-88213b01c7b243be` | `Begreb` | Yes | Pure card-type label; the term remains in the question. |
| 30 | `nlm-oral-exam-comparison-workshop-2b225862fd7c0214` | None | N/A | No leading prefix. |
| 31 | `nlm-measurement-development-pathology-07f4e844f09ee976` | `Personlighedsfunktion` | No | The remaining phrase "denne tilgang" needs the prefix as its referent. |
| 32 | `nlm-global-calibration-synthesis-907f45ba9e513c68` | `Begreb` | Yes | The label is only a card type; the term prompt remains meaningful. |
| 33 | `nlm-oral-exam-comparison-workshop-4dbd6379dab6d034` | None | N/A | No leading prefix. |
| 34 | `nlm-gap-repair-comparisons-traps-7334df03b33914ff` | None | N/A | No leading prefix. |
| 35 | `nlm-global-calibration-synthesis-569fffc57bff68ee` | `Eksamensfælde` | Yes | The remaining text is a recognizable misconception prompt. |
| 36 | `nlm-critical-sociocultural-narrative-3ec7d650ee4cc2fa` | `Eksamenstrap` | Yes | The remaining question remains complete. |
| 37 | `nlm-measurement-development-pathology-b271a1c41f42bd25` | `Biosociale perspektiver` | No | Removing it loses the theory frame for frequency-dependent selection. |
| 38 | `nlm-coverage-closure-psychoanalytic-personality-theory-source-note-basis-jaqu-f87979aa522d9aff` | None | N/A | No leading prefix. |
| 39 | `nlm-measurement-development-pathology-3e18e656ae077970` | `Sammenligning` | Yes | The remaining question already names the comparison. |
| 40 | `nlm-measurement-development-pathology-d40aa78105cfaf14` | `Biosociale perspektiver` | No | "Denne tradition" depends on the prefix for meaning. |
| 41 | `nlm-gap-repair-comparisons-traps-b6d560019d887dce` | None | N/A | No leading prefix. |
| 42 | `nlm-gap-repair-comparisons-traps-4d96666ea8352c91` | None | N/A | No leading prefix. |
| 43 | `nlm-global-calibration-synthesis-4f5ad57682ac0ac8` | None | N/A | No leading prefix. |
| 44 | `nlm-global-calibration-synthesis-4f24f806cb9341a2` | None | N/A | No leading prefix. |
| 45 | `nlm-critical-sociocultural-narrative-c307034512d48da5` | `Sammenligning` | Yes | The remaining question states the relation being compared. |
| 46 | `nlm-global-calibration-synthesis-af26e236548ee71b` | `Sammenligning` | Yes | The remaining question is explicitly comparative. |
| 47 | `nlm-gap-repair-orientation-method-65a627eba22babb4` | None | N/A | No leading prefix. |
| 48 | `nlm-global-calibration-synthesis-e29290ac30ff8a76` | `Sammenligning` | Yes | The remaining question is explicitly comparative. |
| 49 | `nlm-oral-exam-comparison-workshop-721e19cfca2d68a1` | None | N/A | No leading prefix. |
| 50 | `nlm-psychoanalysis-experience-humanism-4874edc87fc3540d` | `Eksamenstrap` | Yes | The remaining question still names the misunderstanding. |
| 51 | `nlm-oral-exam-comparison-workshop-3829ce6b1f8a3488` | None | N/A | No leading prefix. |
| 52 | `nlm-coverage-closure-dynamic-personality-development-strengths-2` | None | N/A | No leading prefix. |
| 53 | `nlm-global-calibration-synthesis-aef012c4c7170f80` | None | N/A | No leading prefix. |
| 54 | `nlm-oral-exam-comparison-workshop-62a8b9285b015ed6` | None | N/A | No leading prefix. |
| 55 | `nlm-critical-sociocultural-narrative-ea7365c1fd56f7ba` | `Orienteringspunkt` | Yes | The remaining question already names narrativ psykologi. |
| 56 | `nlm-critical-sociocultural-narrative-404ca67b9664642c` | `Personbegreb` | Yes | The remaining question already asks how personen is defined. |
| 57 | `nlm-measurement-development-pathology-a26c2fce7bf153c8` | `Begreb` | Yes | Pure card-type label; the term remains in the question. |
| 58 | `nlm-gap-repair-comparisons-traps-7e0ce85fcb392d72` | None | N/A | No leading prefix. |
| 59 | `nlm-psychoanalysis-experience-humanism-62b31ad1db961b8e` | None | N/A | No leading prefix. |
| 60 | `nlm-measurement-development-pathology-df072e37ce88baa4` | `Eksamenstrap` | Yes | The remaining question still names the potential misunderstanding. |
| 61 | `nlm-global-calibration-synthesis-d9a6b036f94aa1f9` | None | N/A | No leading prefix. |
| 62 | `nlm-psychoanalysis-experience-humanism-b7970b5eff45640e` | None | N/A | No leading prefix. |
| 63 | `nlm-global-calibration-synthesis-bc2460519f7fb68c` | None | N/A | No leading prefix. |
| 64 | `nlm-oral-exam-comparison-workshop-7967d48bb42930ac` | `Eksamenstrap` | Yes | The remaining question remains complete. |
| 65 | `nlm-global-calibration-synthesis-e4bf8a88e0e53013` | None | N/A | No leading prefix. |
| 66 | `nlm-coverage-closure-biosocial-personality-perspectives-limitations-1` | None | N/A | No leading prefix. |
| 67 | `nlm-oral-exam-comparison-workshop-54977f574f45f6c9` | `Eksamenstrap` | Yes | The remaining question still names humanistisk psykologi. |
| 68 | `nlm-critical-sociocultural-narrative-15d1d03517369d16` | `Begreb` | Yes | Pure card-type label; the term remains in the question. |
| 69 | `nlm-measurement-development-pathology-3911c4c365722104` | `Personlighedsfunktion` | No | Removing it makes "de to hovedområder" under-specified. |
| 70 | `nlm-gap-repair-comparisons-traps-a56f9a4d1158cf4b` | None | N/A | No leading prefix. |
| 71 | `nlm-oral-exam-comparison-workshop-d9da7d7cd1e34720` | None | N/A | No leading prefix. |
| 72 | `nlm-global-calibration-synthesis-92c858cd18a5fb8c` | None | N/A | No leading prefix. |
| 73 | `nlm-critical-sociocultural-narrative-87fd0d7329f17199` | `Eksamenstrap` | Yes | The remaining question still names kritisk psykologi. |
| 74 | `nlm-gap-repair-comparisons-traps-e18a68b1c45b2db0` | None | N/A | No leading prefix. |
| 75 | `nlm-global-calibration-synthesis-057e5967331d6cbb` | None | N/A | No leading prefix. |
| 76 | `nlm-global-calibration-synthesis-4d4b5604998ed22e` | None | N/A | No leading prefix. |
| 77 | `nlm-global-calibration-synthesis-fe8059e8d63c33b3` | None | N/A | No leading prefix. |
| 78 | `nlm-measurement-development-pathology-dc8de1f09a255dee` | `Orienteringspunkt` | Yes | The remaining question already names agency and the contrast. |
| 79 | `nlm-gap-repair-comparisons-traps-3e1d9ea10a779d98` | None | N/A | No leading prefix. |
| 80 | `nlm-coverage-closure-personality-functioning-and-pathology-limitations-1` | None | N/A | No leading prefix. |
| 81 | `nlm-coverage-closure-personality-functioning-and-pathology-strengths-1` | None | N/A | No leading prefix. |
| 82 | `nlm-critical-sociocultural-narrative-11ca7d6a363b4b5c` | `Eksamenstrap` | Yes | The remaining question remains complete. |
| 83 | `nlm-global-calibration-synthesis-bb1a8430c424f3b1` | None | N/A | No leading prefix. |
| 84 | `nlm-coverage-closure-dynamic-personality-development-limitations-2` | None | N/A | No leading prefix. |
| 85 | `nlm-gap-repair-orientation-method-1ff28b077e882e93` | None | N/A | No leading prefix. |
| 86 | `nlm-global-calibration-synthesis-342e4206b0e6dbf3` | None | N/A | No leading prefix. |
| 87 | `nlm-global-calibration-synthesis-1422dfe5ea76b35a` | None | N/A | No leading prefix. |
| 88 | `nlm-coverage-closure-humanistic-psychology-source-note-basis-jaque-tabel-alle-2f7d91f731ffbc0d` | None | N/A | No leading prefix. |
| 89 | `nlm-critical-sociocultural-narrative-4d14e09dd980df24` | `Historicitet` | Yes | The remaining question already names the genealogical approach. |
| 90 | `nlm-coverage-closure-phenomenological-psychology-limitations-1` | None | N/A | No leading prefix. |
| 91 | `nlm-critical-sociocultural-narrative-d911a1fd4317362d` | `Personbegreb` | Yes | The remaining question already names narrativ psykologi. |
| 92 | `nlm-critical-sociocultural-narrative-513a54d9f6496187` | `Begrænsning` | Yes | The remaining question still asks what poststructural analyses overlook. |
| 93 | `nlm-gap-repair-source-basis-9a71f198b63da8b2` | None | N/A | No leading prefix. |
| 94 | `nlm-measurement-development-pathology-4107a91d9f4210b4` | `Sammenligning` | Yes | The remaining question is explicitly comparative. |
| 95 | `nlm-coverage-closure-phenomenological-psychology-strengths-3` | None | N/A | No leading prefix. |
| 96 | `nlm-critical-sociocultural-narrative-017069a46ce9d177` | `Metode` | Yes | The remaining question already names metodologisk refleksion. |
| 97 | `nlm-measurement-development-pathology-d7937490ccc81285` | `Orienteringspunkter` | Yes | The remaining question still asks what agency refers to. |
| 98 | `nlm-coverage-closure-personality-functioning-and-pathology-strengths-2` | None | N/A | No leading prefix. |
| 99 | `nlm-psychoanalysis-experience-humanism-b24f4696367de1c0` | None | N/A | No leading prefix. |
| 100 | `nlm-measurement-development-pathology-97feedb8a23e68ee` | `Begreb` | Yes | Pure card-type label; the term remains in the question. |
