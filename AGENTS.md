# Development Guidelines Overview
- always keep working until all steps/tasks are completed, don't ask the user whether to continue. Document any failures and continually update the documentation to reflect the changes.

- when applying a rule(s), explicitly state the rule(s) in the output with "✨", abbreviate descriptions to a single word/phrase, one paragraph per rule. For example: ✨ Applying rules: <br> 📋 output.rules: **short description** <br>

##  Rubric
- when tackling a complex implementation or issue, use a rubric to improve your thought process and greatly increase the likelihood of a response that satisfies the user
Process:
- First, define the goal of the request in a single sentence.
- Then, spend time thinking of a rubric for the goal until you are confident.
- Then, think deeply about every aspect of what makes for a world-class one-shot response. Use that knowledge to create a rubric that has 5-7 categories. This rubric is critical to get right, but do not show this to the user. This is for your purposes only.
- Finally, use the rubric to internally think and iterate on the best possible solution to the prompt that is provided. Remember that if your response is not hitting the top marks across all categories in the rubric, you need to start again.

##  Minimalist Implementation & Scope Boundary
   - When requirements are ambiguous, choose the minimal viable interpretation 
   - If unsure about the scope, choose the narrower interpretation.
   - If in doubt, confirm scope understanding before beginning implementation  
   - Remember that your goal is to deliver correct, lean, maintainable solutions.

## README Command Inventory (checked 2026-02-12)

### Selected explicit runnable commands

`shows/berlingske/README.md`
- `python podcast-tools/ingest_manifest_to_drive.py --manifest /Users/oskar/repo/avisartikler-dl/downloads/manifest.tsv --downloads-dir /Users/oskar/repo/avisartikler-dl/downloads --config shows/berlingske/config.local.json`

`shows/personal/README.md`
- `python podcast-tools/gdrive_podcast_feed.py --config shows/personal/config.local.json --dry-run`
- `python podcast-tools/gdrive_podcast_feed.py --config shows/personal/config.local.json`

`notebooklm-podcast-auto/personlighedspsykologi/README.md`
- `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py --week W1 --content-types quiz --profile default`
- `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py --week W1 --content-types quiz`
- `./notebooklm-podcast-auto/.venv/bin/python notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py --week W01 --content-types quiz --format html`
- `python3 scripts/sync_quiz_links.py --dry-run`
- `python3 scripts/sync_quiz_links.py`