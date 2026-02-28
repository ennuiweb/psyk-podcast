"""URL routing for quiz pages and APIs."""

from django.urls import re_path

from . import views

urlpatterns = [
    re_path(r"^q/(?P<quiz_id>[0-9a-f]{8})\.html$", views.quiz_wrapper_view, name="quiz-wrapper"),
    re_path(r"^q/raw/(?P<quiz_id>[0-9a-f]{8})\.html$", views.quiz_raw_view, name="quiz-raw"),
    re_path(r"^api/quiz-content/(?P<quiz_id>[0-9a-f]{8})$", views.quiz_content_view, name="quiz-content"),
    re_path(r"^api/gamification/me$", views.gamification_me_view, name="gamification-me"),
    re_path(r"^api/quiz-state/(?P<quiz_id>[0-9a-f]{8})$", views.quiz_state_view, name="quiz-state"),
    re_path(
        r"^api/quiz-state/(?P<quiz_id>[0-9a-f]{8})/raw$",
        views.quiz_state_raw_view,
        name="quiz-state-raw",
    ),
    re_path(r"^leaderboard/profile$", views.leaderboard_profile_view, name="leaderboard-profile"),
    re_path(
        r"^leaderboard/(?P<subject_slug>[a-z0-9-]+)$",
        views.leaderboard_subject_view,
        name="leaderboard-subject",
    ),
    re_path(r"^subjects/(?P<subject_slug>[a-z0-9-]+)$", views.subject_detail_view, name="subject-detail"),
    re_path(
        r"^subjects/(?P<subject_slug>[a-z0-9-]+)/enroll$",
        views.subject_enroll_view,
        name="subject-enroll",
    ),
    re_path(
        r"^subjects/(?P<subject_slug>[a-z0-9-]+)/unenroll$",
        views.subject_unenroll_view,
        name="subject-unenroll",
    ),
    re_path(
        r"^subjects/(?P<subject_slug>[a-z0-9-]+)/tracking/tekst$",
        views.subject_tracking_reading_view,
        name="subject-tracking-reading",
    ),
    re_path(
        r"^subjects/(?P<subject_slug>[a-z0-9-]+)/tekster/open/(?P<reading_key>[a-z0-9-]+)$",
        views.subject_open_reading_view,
        name="subject-open-reading",
    ),
    # Legacy aliases kept for backward compatibility with existing deep links.
    re_path(
        r"^subjects/(?P<subject_slug>[a-z0-9-]+)/tracking/reading$",
        views.subject_tracking_reading_view,
        name="subject-tracking-reading-legacy",
    ),
    re_path(
        r"^subjects/(?P<subject_slug>[a-z0-9-]+)/readings/open/(?P<reading_key>[a-z0-9-]+)$",
        views.subject_open_reading_view,
        name="subject-open-reading-legacy",
    ),
    re_path(
        r"^subjects/(?P<subject_slug>[a-z0-9-]+)/tracking/podcast$",
        views.subject_tracking_podcast_view,
        name="subject-tracking-podcast",
    ),
    re_path(r"^progress$", views.progress_view, name="progress"),
    re_path(
        r"^preferences/design-system$",
        views.design_system_preference_view,
        name="design-system-preference",
    ),
]
