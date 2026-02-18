# Reading File Key (Bio / Neuropsychology)

Navngivningspolicy for denne show-scaffold:
- Brug plain `W#` tokens i Drive-navne (fx `W1`, `W2`, ..., `W13`).
- Undga krav om `L#` eller dato i lydfilnavne for auto-spec matching.
- Hold `Grundbog Kapitel X.mp3` stabilt, da `episode_metadata.json` og `reading_summaries.json` er seedet med disse nøgler.

Seedet mapping fra Readings-foldere:

| Uge | Kildefolder | Seedet lydnavn |
| --- | --- | --- |
| W1 | `W1L1 Introduktion (2026-02-06)` | `Grundbog Kapitel 1.mp3` |
| W2 | `W2L1 Funktionel neuroanatomi (2026-02-13)` | `Grundbog Kapitel 2.mp3` |
| W3 | `W3L1 Neurofysiologi (2026-02-20)` | `Grundbog Kapitel 3.mp3` |
| W4 | `W4L1 Neurokemi og neurofarmakologi (2026-02-27)` | `Grundbog Kapitel 4.mp3` |
| W5 | `W5L1 Hormoner og hjernen (2026-03-06)` | `Grundbog Kapitel 5.mp3` |

Manuel udvidelse:
- Hvis nye kapitler/lydfiler tilføjes, opdatér både `episode_metadata.json` og `reading_summaries.json` med samme `by_name`-nøgle.
- Hold ugehenvisninger i navne/mapper konsistente med `auto_spec.json` aliases (`w1`..`w13`).
