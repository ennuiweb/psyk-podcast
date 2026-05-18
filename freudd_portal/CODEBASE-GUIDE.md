# Freudd Portal Codebase Guide
This guide is for coding LLMs working in `freudd_portal/`.
This subsystem is the student-facing Django app that exposes generated learning artifacts as a usable study product.

## 1. Business purpose
The rest of the repo generates and organizes educational content.
`freudd_portal/` is the delivery layer where students actually consume it.

The portal is responsible for:
- quiz access
- subject overview pages
- reading/slide access
- progress tracking
- gamification and leaderboard behavior
- enrollment and access gating

Its job is not to generate content.
Its job is to make the generated content navigable, stateful, and motivating.

## 2. Directory structure
Important branches:
- `freudd_portal/`
- `quizzes/`
- `templates/`
- `docs/`
- `README.md`

What they mean:
- `freudd_portal/`: Django project settings and root URL wiring
- `quizzes/`: the real product app; most business logic lives here
- `templates/`: HTML templates
- `docs/`: deploy and operational docs

## 3. Read this subsystem in this order
1. `README.md`
2. `freudd_portal/urls.py`
3. `quizzes/urls.py`
4. `quizzes/models.py`
5. `quizzes/views.py`
6. `quizzes/services.py`
7. `quizzes/content_services.py`
8. `quizzes/subject_services.py`

The app is “service-layered” in naming, but not in a strict clean-architecture sense.

## 4. Root URL layer
Source: `freudd_portal/freudd_portal/urls.py`

This file is intentionally thin.
It mostly delegates to the `quizzes` app and auth routes.
That means almost every user-facing behavior ultimately lives below `quizzes/`.

## 5. Real route contract
Source: `freudd_portal/quizzes/urls.py`

This file is the real top-level product contract.

Snippet:
```python
# freudd_portal/quizzes/urls.py
re_path(r"^q/(?P<quiz_id>[0-9a-f]{8})\.html$", views.quiz_wrapper_view, name="quiz-wrapper")
re_path(r"^api/quiz-content/(?P<quiz_id>[0-9a-f]{8})$", views.quiz_content_view, name="quiz-content")
re_path(r"^subjects/(?P<subject_slug>[a-z0-9-]+)$", views.subject_detail_view, name="subject-detail")
```

This route table tells you what the app really is:
- quiz webapp
- quiz APIs
- subject hub
- reading/slide access layer
- leaderboard/profile system

It also includes legacy aliases.
Preserve them unless you are intentionally doing a migration.

## 6. Data model center of gravity
Source: `freudd_portal/quizzes/models.py`

This file is large because the portal stores several overlapping kinds of user state.
Key model families include:
- quiz progress
- subject enrollment
- lecture/reading progress
- interface preferences
- notification preferences
- gamification profile
- extension access/credentials

Treat this file as a schema hub.
Any change here can affect:
- views
- serializers/API payloads
- leaderboard logic
- migration behavior
- cached assumptions in service code

## 7. Views layer reality
Source: `freudd_portal/quizzes/views.py`

`views.py` is a monolith.
That is the main architectural fact to remember.

It handles:
- HTML page rendering
- content APIs
- subject navigation
- reading opening/downloading
- leaderboard pages
- tracking mutations
- settings/progress redirects

This means view bugs and business-rule bugs are often interleaved.
Do not expect a thin-controller architecture.

## 8. Services layer
Source: `freudd_portal/quizzes/services.py`

Despite the name, this file is also broad.
It owns utility and business logic such as:
- quiz file resolution
- subject file lookup
- parsing normalized/static quiz artifacts
- copy normalization
- TeX normalization
- label mapping
- scoring helpers
- cooldown logic

This file is one of the highest-risk places for accidental regression because many unrelated views depend on it.

## 9. Subject content manifest layer
Source: `freudd_portal/quizzes/content_services.py`

This file is the bridge between static show artifacts and subject pages.
It builds and caches a subject content manifest from multiple generated files.

Snippet:
```python
# freudd_portal/quizzes/content_services.py
candidates: list[Path] = [
    subject_paths.reading_key_path,
    subject_paths.quiz_links_path,
    subject_paths.episode_inventory_path,
    subject_paths.feed_rss_path,
    subject_paths.spotify_map_path,
    subject_paths.slides_catalog_path,
]
```

That snippet explains a lot:
the portal does not own its own curriculum model.
It synthesizes one from generated repo-side artifacts.

So if subject pages are wrong, the bug may be upstream in those artifacts rather than in the portal code itself.

## 10. Subject path resolution
Source: `freudd_portal/quizzes/subject_services.py`

This file resolves subject-specific path overrides from subject catalog/config data.
It is the routing boundary between “portal code” and “repo content layout”.

If a portal bug affects one subject but not another, start here before changing generic views.

## 11. Gamification and tracking services
Other important service files:
- `tracking_services.py`
- `gamification_services.py`
- `leaderboard_services.py`
- `access_services.py`

These files keep some logic out of `views.py`, but the overall system is still tightly coupled.
Expect cross-module assumptions.

## 12. The real dependency direction
Many web apps own their own content database.
This portal does not.
Instead, it depends on generated/static repo artifacts from other subsystems.

Direction:
`shows/ + generated artifacts -> content_services -> views/templates -> user`

That means:
- content freshness bugs can be artifact staleness bugs
- cache invalidation matters
- file-path assumptions are product-critical

## 13. Common failure classes
- broken subject path resolution
- stale or malformed `content_manifest.json`
- quiz artifact naming drift
- model/view mismatch after schema changes
- route alias regressions
- user progress logic depending on stale generated content

## 14. Non-idiomatic traits
- very thick `views.py`
- very thick `services.py`
- file-based subject content synthesis instead of fully DB-owned content
- some regex-heavy routing/content parsing behavior
- legacy aliases kept alive for deep links

These are not inherently wrong, but they increase coupling and regression risk.

## 15. Safe change strategy
When changing the portal:
1. decide whether the bug is UI, portal logic, or upstream artifact content
2. trace the route in `quizzes/urls.py`
3. inspect the view
4. inspect service/helper dependencies
5. confirm which generated files the page/API reads
6. preserve deep-link compatibility unless explicitly migrating

If you are unsure where to start, start with `quizzes/urls.py`, then `views.py`, then `content_services.py`.

