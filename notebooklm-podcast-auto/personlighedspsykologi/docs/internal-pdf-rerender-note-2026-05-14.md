# Internal PDF Rerender Note

Snapshot date: 2026-05-14
Output folder: `/Users/oskar/repo/podcasts/notebooklm-podcast-auto/personlighedspsykologi/output`

## Scope

Mode: renderer-only from existing JSON (`--rerender-existing`, no `--force`; LLM/provider layer not activated).

The output folder was being changed by another active generation process during this pass. New active source groups were intentionally excluded; only the stable JSON-backed set from before those new sources appeared was rerendered.

Stable source groups in scope: 34
Stable source groups with usable local JSON: 30
Target PDFs rerendered in this pass: 150
Stable source groups skipped because local usable `reading-printouts.json` is absent: 4

Ignored active/new source groups:
- `w05l2-k-ppe-1992-9a474402`
- `w07l1-jacobsen-2021-26129bff`
- `w11l1-grundbog-kapitel-11-postpsykologisk-subjektiveri-3557aeb2`

Skipped stable source groups without usable local JSON:
- `w05l1-gammelgaard-2010-e6baff8b`
- `w05l1-ricoeur-1981-19a5343f`
- `w05l2-andkj-r-olsen-and-k-ppe-1991a-1991b-720b5d8e`
- `w05l2-grundbog-kapitel-7-nyere-psykoanalytiske-teorier-fda84b6a`

## Progress

- 2026-05-14: scope frozen to 30 stable JSON-backed source groups; active/new source groups excluded.
- 2026-05-14: main rerender pass used default provider metadata and completed 28 / 30 stable source groups. The two W01L1 sources were not accepted in that pass because their JSON metadata is `openai/gpt-5.5`, not the default `gemini/gemini-3.1-pro-preview`.
- 2026-05-14: W01L1 retry used `--provider openai --model gpt-5.5` and completed 2 / 2 stable source groups.
- 2026-05-14: final renderer-only status: completed, 30 / 30 stable JSON-backed source groups rerendered.

## Target Source Groups

- `w01l1-grundbog-kapitel-1-introduktion-til-personlighed-1e727647`
- `w01l1-lewis-1999-295c67e3`
- `w04l1-freud-1973-1933-98cd9920`
- `w04l1-gammelgaard-2007-bcbdbec2`
- `w04l2-lacan-1966-2d720f56`
- `w04l2-laplanche-1970-968862d5`
- `w06l1-grundbog-kapitel-4-f-nomenologisk-personlighedsp-1afa74d2`
- `w06l1-moesk-r-hansen-and-roald-2022-b7aec462`
- `w06l1-spinelli-2005-b2f76e93`
- `w07l2-evans-1975-8e8a9d79`
- `w07l2-giorgi-2005-55ca98f7`
- `w07l2-maslow-1968-7ea53e34`
- `w08l1-lamiell-2021-be79d36e`
- `w08l1-laux-et-al-2010-cfff840c`
- `w08l2-holzkamp-1982-845aafd2`
- `w08l2-tolman-2009-455915e0`
- `w09l1-dreier-1999-35da58b5`
- `w09l1-grundbog-kapitel-10-kritisk-psykologi-b3286662`
- `w09l1-holzkamp-2013-c3068d8a`
- `w09l1-m-rch-and-hansen-2015-b1dbfc5f`
- `w10l1-bjerrum-nielsen-and-rudberg-2006-39335ee6`
- `w10l1-mitchell-2015-bc690b36`
- `w10l2-foucault-1997-92cd121d`
- `w11l2-bruner-1999-7930abd8`
- `w11l2-grundbog-kapitel-9-narrative-teorier-cd12008a`
- `w11l2-mcadams-and-pals-2006-b9675688`
- `w11l2-raggatt-2002-d15129af`
- `w12l1-elias-2000-f9176ae8`
- `w12l1-grundbog-kapitel-14-perspektiver-pa-personlighed-95ca3a38`
- `w12l1-grundbog-kapitel-8-personlighed-subjektivitet-og-b0095bfb`
