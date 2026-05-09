# Personlighedspsykologi Danish Prompt Localization Plan

This document tracks the implementation of the Danish prompt-localization
architecture for the `personlighedspsykologi-da` mirror.

Status: in progress
Last updated: 2026-05-09

## Scope

This rollout changes prompt generation, not feed publication:

- keep English prompt logic canonical
- render Danish prompt scaffolding from a shared localization layer
- add a subject-owned Danish prompt override catalog
- add a subject-owned Danish course-context translation catalog
- prevent mixed-language prompt scaffolding in Danish runs
- add validation and tests so future English prompt changes cannot silently
  leak untranslated text into the Danish queue

This rollout does not change the Danish feed contract, R2 layout, or Freudd
portal scope.

## Objectives

- Danish prompt instructions should mirror the English prompt layer instead of
  forking it manually.
- The queue runtime must not depend on a live translation API.
- Code-owned prompt labels and templates must be localized centrally.
- Subject-owned prompt prose should be localized through repo-owned assets.
- Dynamic course-context prose should be localized or explicitly omitted rather
  than leaking English into Danish prompts.
- Future English prompt changes should produce deterministic translation
  maintenance failures, not silent mixed-language regressions.

## Architecture

- English remains the only canonical prompt logic source.
- `notebooklm_queue/prompt_localization.py` becomes the shared localization
  layer for prompt UI text, prompt override loading, and course-context text
  translation rules.
- `generate_week.py` carries both `language` and `prompt_locale`, so NotebookLM
  output language and prompt language can be controlled independently.
- `notebooklm_queue/prompting.py` and `notebooklm_queue/course_context.py`
  render locale-aware prompt scaffolding instead of hardcoding English.
- `notebooklm-podcast-auto/personlighedspsykologi/locales/` owns the Danish
  translation assets used by the mirror.
- Validation tooling checks for missing or obsolete Danish course-context
  translations.

## Progress

- [x] Create a dedicated tracked implementation document
- [x] Implement shared prompt-localization module
- [x] Wire prompt locale through generation, prompt assembly, and
  course-context rendering
- [x] Add Danish locale assets and translation validation tooling
- [ ] Add regression tests for Danish prompt rendering
- [ ] Run verification, deploy runtime changes, and update docs with final
  rollout status

## Work Log

### 2026-05-09

- Created this tracked implementation plan before code changes.
- Confirmed the root issue: the Danish wrapper only changes `language`, while
  the actual prompt scaffolding still comes from English defaults and English
  renderer templates.
- Confirmed the two required localization layers:
  static prompt/config translation and dynamic course-context translation.
- Added `notebooklm_queue/prompt_localization.py` as the shared localization
  layer for prompt UI strings, locale asset loading, and dynamic course-context
  text handling.
- Wired `prompt_locale` through `generate_week.py` so each language variant can
  resolve its own localized prompt bundle without forking the canonical English
  prompt config.
- Updated `notebooklm_queue/prompting.py` and
  `notebooklm_queue/course_context.py` to render locale-aware prompt
  scaffolding rather than hardcoded English wrappers.
- Added subject-owned Danish locale assets under
  `notebooklm-podcast-auto/personlighedspsykologi/locales/`.
- Added `sync_prompt_translations.py` to validate prompt-override coverage and
  maintain the course-context translation catalog.
- Began machine backfill of the Danish course-context translation catalog so
  the mirror can use tracked translated dynamic context instead of relying only
  on omission of untranslated English prose.
