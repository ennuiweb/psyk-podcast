# Personlighedspsykologi Concept Quiz Lab

Generated source packs for NotebookLM concept quizzes. Regenerate with:

```bash
.venv/bin/python scripts/export_personlighedspsykologi_concept_quiz_packs.py
```

The live generation path is the Hetzner NotebookLM queue show `personlighedspsykologi-concept-quizzes`; it uses medium difficulty as the single normal quiz level.

Ready-state handoff:

1. Generate or place one medium quiz JSON for each `W90L1`-`W90L7` pack under the lab `output/` tree, or pass an external output root to the import script.
2. Import into Freudd:

```bash
.venv/bin/python scripts/import_personlighedspsykologi_concept_quizzes.py --output-root notebooklm-podcast-auto/personlighedspsykologi/concept_quiz_lab/output
```

The importer fails closed if any pack is missing and writes the committed quiz files plus the subject manifest/links needed by Freudd.
