# Podcasts Repo Codebase Guides
This repo is not one application.
It is a multi-system content platform.
The code is split across several distinct subsystems that share generated artifacts, show config, and operator workflows.
This index points coding LLMs at the right guide before they start changing code.

## 1. What the repo fundamentally does
At the highest level, `podcasts` is the content and delivery repo for:
- podcast generation and publication
- NotebookLM-assisted content production
- course-specific semantic preprocessing
- a student-facing learning portal
- transcript acquisition
- legacy Drive-trigger glue

The repo is therefore not cleanly layered like a single web app.
It is closer to a small platform with:
- content source understanding
- generation pipelines
- publication automation
- static/generated artifact management
- user-facing delivery

That matters because bugs often cross subsystem boundaries.
For example:
- a queue bug can look like a feed bug
- a show config mistake can look like a generator bug
- a semantic preprocessing mistake can look like a portal content bug

## 2. Read these guides in this order
1. [TECHNICAL.md](/Users/oskar/repo/podcasts/TECHNICAL.md)
2. This file
3. The subsystem guide for the code you are touching

## 3. Subsystem guide map

### Core pipelines
- [notebooklm_queue/CODEBASE-GUIDE.md](/Users/oskar/repo/podcasts/notebooklm_queue/CODEBASE-GUIDE.md)
  Queue/orchestration layer for discover → generate → publish.
- [notebooklm-podcast-auto/CODEBASE-GUIDE.md](/Users/oskar/repo/podcasts/notebooklm-podcast-auto/CODEBASE-GUIDE.md)
  NotebookLM client wrappers and course-specific generation scripts.
- [podcast-tools/CODEBASE-GUIDE.md](/Users/oskar/repo/podcasts/podcast-tools/CODEBASE-GUIDE.md)
  Feed generation, media inventory, Drive/R2 storage logic, and quiz-link syncing.

### User-facing delivery
- [freudd_portal/CODEBASE-GUIDE.md](/Users/oskar/repo/podcasts/freudd_portal/CODEBASE-GUIDE.md)
  Django portal serving quizzes, subject tracking, reading access, and gamification.

### Supporting automation
- [spotify_transcripts/CODEBASE-GUIDE.md](/Users/oskar/repo/podcasts/spotify_transcripts/CODEBASE-GUIDE.md)
  Spotify transcript acquisition and normalization pipeline.
- [apps-script/CODEBASE-GUIDE.md](/Users/oskar/repo/podcasts/apps-script/CODEBASE-GUIDE.md)
  Legacy Google Apps Script trigger layer for Drive change detection.

### Data/config boundary
- [shows/CODEBASE-GUIDE.md](/Users/oskar/repo/podcasts/shows/CODEBASE-GUIDE.md)
  Show-level config, generated outputs, and source-of-truth versus derived artifacts.

### Canonical printout workspace
- [notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/CODEBASE-GUIDE.md](/Users/oskar/repo/podcasts/notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/CODEBASE-GUIDE.md)
  Current canonical PDF-producing printout generation for `personlighedspsykologi`; main-code integration is still pending.

## 4. Quick routing advice
- If the bug mentions queue state, stage transitions, or publication state:
  start with `notebooklm_queue`.
- If the bug mentions NotebookLM generation, profiles, artifacts, or course scripts:
  start with `notebooklm-podcast-auto`.
- If the bug mentions RSS output, media inventory, feed ordering, or Drive/R2:
  start with `podcast-tools`.
- If the bug is user-facing on `freudd.dk`:
  start with `freudd_portal`.
- If the bug is transcript-related:
  start with `spotify_transcripts`.
- If the bug smells like “the wrong file is being used”:
  inspect `shows/` and the relevant show config before touching runtime code.

## 5. Important cross-cutting reality
This repo has several non-idiomatic traits that every coding model should remember:
- many scripts are operator CLIs, not import-clean libraries
- several large files are monolithic and own too much behavior
- show directories mix canonical inputs and derived outputs
- multiple subsystems use filename conventions as part of their data model
- generated artifacts are often treated as runtime inputs later in the chain

Do not assume the repo is normalized around one framework boundary.
It is a working production system built around real publishing workflows and evolving course automation.
Preserve contracts first.
Refactor only when you can clearly preserve those contracts.
