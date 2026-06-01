# Personlighedspsykologi Concept Quiz Lab

Generated source packs for NotebookLM concept quizzes. Regenerate with:

```bash
.venv/bin/python scripts/export_personlighedspsykologi_concept_quiz_packs.py
```

The live generation path is the Hetzner NotebookLM queue show `personlighedspsykologi-concept-quizzes`; it uses medium difficulty as the single normal quiz level. The show is quiz-only and intentionally ignores `NOTEBOOKLM_QUEUE_ONLY_SHORT_OUTPUTS` so it cannot inherit short-output settings from podcast services. Quiz language is controlled by the generator path; do not mutate global NotebookLM profile language to make these Danish.

Import with:

```bash
.venv/bin/python scripts/import_personlighedspsykologi_concept_quizzes.py --output-root notebooklm-podcast-auto/personlighedspsykologi/concept_quiz_lab/output
```

The importer rejects empty quizzes, likely English output, and leaked source/provenance wording such as matrix/source-material references before writing Freudd quiz files.

Category fit is guarded by `shows/personlighedspsykologi-en/concept_quizzes/category_contracts.json` and checked by:

```bash
.venv/bin/python scripts/audit_personlighedspsykologi_concept_quiz_categories.py --write-report
```

The audit writes `shows/personlighedspsykologi-en/concept_quizzes/category_fit_report.md` and is included in the Personlighedspsykologi artifact invariant check. Generated quiz titles are normalized to the manifest title on import so learner-facing category labels stay stable.

After importing and committing the Freudd quiz files, mark the corresponding queue jobs `completed` so the generation-only concept show does not keep an `awaiting_publish` backlog.
