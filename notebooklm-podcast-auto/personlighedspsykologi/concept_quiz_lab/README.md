# Personlighedspsykologi Concept Quiz Lab

Generated source packs for NotebookLM concept quizzes. Regenerate with:

```bash
.venv/bin/python scripts/export_personlighedspsykologi_concept_quiz_packs.py
```

The live generation path is the Hetzner NotebookLM queue show `personlighedspsykologi-concept-quizzes`; it uses medium difficulty as the single normal quiz level. The show is quiz-only and intentionally ignores `NOTEBOOKLM_QUEUE_ONLY_SHORT_OUTPUTS` so it cannot inherit short-output settings from podcast services.

Import with:

```bash
.venv/bin/python scripts/import_personlighedspsykologi_concept_quizzes.py --output-root notebooklm-podcast-auto/personlighedspsykologi/concept_quiz_lab/output
```

The importer rejects empty quizzes, likely English output, and leaked source/provenance wording such as matrix/source-material references before writing Freudd quiz files.
