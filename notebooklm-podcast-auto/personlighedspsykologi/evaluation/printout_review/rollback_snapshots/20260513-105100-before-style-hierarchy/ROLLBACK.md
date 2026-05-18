# Rollback: before style hierarchy

Snapshot taken before the renderer-only style hierarchy experiment.

To restore code and tests:

```sh
cp notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/rollback_snapshots/20260513-105100-before-style-hierarchy/printout_engine.py \
  notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/scripts/printout_engine.py
cp notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/rollback_snapshots/20260513-105100-before-style-hierarchy/test_printout_review_printout_engine.py \
  tests/test_printout_review_printout_engine.py
```

To restore the review PDF/output directory:

```sh
rm -rf notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/review
tar -xzf notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/rollback_snapshots/20260513-105100-before-style-hierarchy/review-before-style-hierarchy.tar.gz \
  -C notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review
```
