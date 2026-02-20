"""URL routing for quiz pages and APIs."""

from django.urls import re_path

from . import views

urlpatterns = [
    re_path(r"^q/(?P<quiz_id>[0-9a-f]{8})\.html$", views.quiz_wrapper_view, name="quiz-wrapper"),
    re_path(r"^q/raw/(?P<quiz_id>[0-9a-f]{8})\.html$", views.quiz_raw_view, name="quiz-raw"),
    re_path(r"^api/quiz-content/(?P<quiz_id>[0-9a-f]{8})$", views.quiz_content_view, name="quiz-content"),
    re_path(r"^api/quiz-state/(?P<quiz_id>[0-9a-f]{8})$", views.quiz_state_view, name="quiz-state"),
    re_path(
        r"^api/quiz-state/(?P<quiz_id>[0-9a-f]{8})/raw$",
        views.quiz_state_raw_view,
        name="quiz-state-raw",
    ),
    re_path(r"^progress$", views.progress_view, name="progress"),
]
