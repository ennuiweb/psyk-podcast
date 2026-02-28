from __future__ import annotations

import importlib
import html
import io
import json
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import clear_url_caches, reverse, set_urlconf
from django.utils import timezone

from quizzes import services as quiz_services
from quizzes.content_services import clear_content_service_caches
from quizzes.leaderboard_services import active_half_year_season
from quizzes.models import (
    DailyGamificationStat,
    ExtensionSyncLedger,
    QuizProgress,
    SubjectEnrollment,
    UserExtensionAccess,
    UserExtensionCredential,
    UserGamificationProfile,
    UserInterfacePreference,
    UserLectureProgress,
    UserLeaderboardProfile,
    UserPodcastMark,
    UserReadingMark,
    UserReadingProgress,
    UserUnitProgress,
)
from quizzes.services import load_quiz_label_mapping
from quizzes.subject_services import clear_subject_service_caches
from quizzes.views import _enrich_subject_path_lectures


class QuizPortalTests(TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        root = Path(self.temp_dir.name)
        self.quiz_root = root / "quizzes"
        self.quiz_root.mkdir(parents=True, exist_ok=True)
        self.links_file = root / "quiz_links.json"
        self.subjects_file = root / "subjects.json"
        self.reading_master_file = root / "reading-file-key.md"
        self.reading_fallback_file = root / "reading-file-key-fallback.md"
        self.rss_file = root / "rss.xml"
        self.spotify_map_file = root / "spotify_map.json"
        self.content_manifest_file = root / "content_manifest.json"
        self.reading_files_root = root / "reading-files"
        self.reading_exclusions_file = root / "reading_download_exclusions.json"

        self.override = override_settings(
            QUIZ_FILES_ROOT=self.quiz_root,
            QUIZ_LINKS_JSON_PATH=self.links_file,
            FREUDD_SUBJECTS_JSON_PATH=self.subjects_file,
            FREUDD_READING_MASTER_KEY_PATH=self.reading_master_file,
            FREUDD_READING_MASTER_KEY_FALLBACK_PATH=self.reading_fallback_file,
            FREUDD_SUBJECT_FEED_RSS_PATH=self.rss_file,
            FREUDD_SUBJECT_SPOTIFY_MAP_PATH=self.spotify_map_file,
            FREUDD_SUBJECT_CONTENT_MANIFEST_PATH=self.content_manifest_file,
            FREUDD_READING_FILES_ROOT=self.reading_files_root,
            FREUDD_READING_DOWNLOAD_EXCLUSIONS_PATH=self.reading_exclusions_file,
            FREUDD_CREDENTIALS_MASTER_KEY="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
            FREUDD_CREDENTIALS_KEY_VERSION=1,
            FREUDD_EXT_SYNC_TIMEOUT_SECONDS=2,
            QUIZ_SIGNUP_RATE_LIMIT=1000,
            QUIZ_LOGIN_RATE_LIMIT=1000,
            FREUDD_AUTH_GOOGLE_ENABLED=False,
            SOCIALACCOUNT_PROVIDERS={},
        )
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(self._reload_root_urlconf)
        clear_subject_service_caches()
        self.addCleanup(clear_subject_service_caches)
        clear_content_service_caches()
        self.addCleanup(clear_content_service_caches)
        quiz_services._METADATA_CACHE["mtime"] = None
        quiz_services._METADATA_CACHE["data"] = {}

        self.quiz_id = "29ebcecd"
        self._write_quiz_file(self.quiz_id, question_count=2)
        self._write_quiz_json_file(self.quiz_id, question_count=2)
        self._write_links_file(
            {
                self.quiz_id: {
                    "title": "W1L1 - Episode",
                    "difficulty": "medium",
                }
            }
        )
        self._write_subjects_file()
        self._write_reading_master_file()
        self.reading_fallback_file.write_text(self.reading_master_file.read_text(encoding="utf-8"), encoding="utf-8")
        self._write_rss_file()
        self._write_spotify_map()
        self._write_reading_files()
        self._write_reading_download_exclusions([])

    def _write_quiz_file(self, quiz_id: str, *, question_count: int) -> None:
        payload = {"quiz": [{"question": f"Q{i + 1}"} for i in range(question_count)]}
        escaped_payload = html.escape(json.dumps(payload), quote=True)
        content = f"""<!doctype html>
<html>
  <body>
    <app-root data-app-data=\"{escaped_payload}\"></app-root>
  </body>
</html>
"""
        (self.quiz_root / f"{quiz_id}.html").write_text(content, encoding="utf-8")

    def _write_quiz_json_file(self, quiz_id: str, *, question_count: int) -> None:
        payload = {
            "title": "Personality Quiz",
            "questions": [
                {
                    "question": f"Q{i + 1}",
                    "answerOptions": [
                        {"text": "A", "isCorrect": i % 2 == 0, "rationale": "Forklaring A"},
                        {"text": "B", "isCorrect": i % 2 == 1, "rationale": "Forklaring B"},
                    ],
                    "hint": f"Hint {i + 1}",
                }
                for i in range(question_count)
            ],
        }
        (self.quiz_root / f"{quiz_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

    def _write_links_file(self, entries: dict[str, dict[str, str]]) -> None:
        by_name: dict[str, dict[str, object]] = {}
        for quiz_id, meta in entries.items():
            title = meta["title"]
            subject_slug = meta.get("subject_slug", "personlighedspsykologi")
            by_name[title] = {
                "relative_path": f"{quiz_id}.html",
                "difficulty": meta.get("difficulty", "medium"),
                "subject_slug": subject_slug,
                "links": [
                    {
                        "relative_path": f"{quiz_id}.html",
                        "difficulty": meta.get("difficulty", "medium"),
                        "format": "html",
                        "subject_slug": subject_slug,
                    }
                ],
            }

        self.links_file.write_text(json.dumps({"by_name": by_name}), encoding="utf-8")

    def _write_subjects_file(self, *, include_subject: bool = True) -> None:
        payload: dict[str, object] = {
            "version": 1,
            "subjects": [],
        }
        if include_subject:
            payload["subjects"] = [
                {
                    "slug": "personlighedspsykologi",
                    "title": "Personlighedspsykologi",
                    "description": "Personlighedspsykologi F26",
                    "active": True,
                }
            ]
        self.subjects_file.write_text(json.dumps(payload), encoding="utf-8")

    def _write_reading_master_file(self) -> None:
        self.reading_master_file.write_text(
            "\n".join(
                [
                    "# Reading File Key",
                    "",
                    "**W01L1 Introforelaesning (Forelaesning 1, 2026-02-02)**",
                    "- Grundbog kapitel 01 - Introduktion til personlighedspsykologi \u2192 Grundbog kapitel 01 - Introduktion.pdf",
                    "- Lewis (1999) \u2192 Lewis (1999).pdf",
                    "",
                    "**W01L2 Personality assessment (Forelaesning 2, 2026-02-03)**",
                    "- Mayer & Bryan (2024) \u2192 Mayer & Bryan (2024).pdf",
                    "- MISSING: Koutsoumpis (2025)",
                ]
            ),
            encoding="utf-8",
        )

    def _write_rss_file(self) -> None:
        self.rss_file.write_text(
            "\n".join(
                [
                    '<?xml version="1.0" encoding="UTF-8"?>',
                    "<rss version=\"2.0\">",
                    "<channel>",
                    "<item>",
                    "<title>U1F1 · [Podcast] · Alle kilder · 02/02 - 08/02</title>",
                    "<pubDate>Mon, 02 Feb 2026 08:00:00 +0100</pubDate>",
                    '<enclosure url="https://example.test/podcast/w01l1-alle-kilder.mp3" length="1" type="audio/mpeg" />',
                    "</item>",
                    "<item>",
                    "<title>U1F1 · [Podcast] · Grundbog kapitel 01 - Introduktion til personlighedspsykologi · 02/02 - 08/02</title>",
                    "<pubDate>Mon, 02 Feb 2026 10:00:00 +0100</pubDate>",
                    '<enclosure url="https://example.test/podcast/w01l1-intro.mp3" length="1" type="audio/mpeg" />',
                    "</item>",
                    "</channel>",
                    "</rss>",
                ]
            ),
            encoding="utf-8",
        )

    def _write_spotify_map(self, by_rss_title: dict[str, str] | None = None) -> None:
        mapping = by_rss_title if by_rss_title is not None else {
            "U1F1 · [Podcast] · Alle kilder · 02/02 - 08/02": "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8",
            "U1F1 · [Podcast] · Grundbog kapitel 01 - Introduktion til personlighedspsykologi · 02/02 - 08/02": "https://open.spotify.com/episode/4w4gHCXnQK5fjQdsxQO0XG",
        }
        self.spotify_map_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "subject_slug": "personlighedspsykologi",
                    "by_rss_title": mapping,
                }
            ),
            encoding="utf-8",
        )

    def _write_reading_files(self) -> None:
        w01l1 = self.reading_files_root / "W01L1"
        w01l2 = self.reading_files_root / "W01L2"
        w01l1.mkdir(parents=True, exist_ok=True)
        w01l2.mkdir(parents=True, exist_ok=True)
        (w01l1 / "Grundbog kapitel 01 - Introduktion.pdf").write_bytes(b"%PDF-1.4\n%test\n")
        (w01l1 / "Lewis (1999).pdf").write_bytes(b"%PDF-1.4\n%test\n")
        (w01l2 / "Mayer & Bryan (2024).pdf").write_bytes(b"%PDF-1.4\n%test\n")

    def _write_reading_download_exclusions(self, reading_keys: list[str]) -> None:
        self.reading_exclusions_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "subjects": {
                        "personlighedspsykologi": {
                            "excluded_reading_keys": reading_keys,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

    def _create_user(self, username: str = "alice", password: str = "Secret123!!") -> User:
        return User.objects.create_user(username=username, password=password)

    def _login(self, username: str = "alice", password: str = "Secret123!!") -> None:
        self.client.login(username=username, password=password)

    def _reload_root_urlconf(self) -> None:
        clear_url_caches()
        importlib.reload(importlib.import_module(settings.ROOT_URLCONF))
        set_urlconf(None)

    @contextmanager
    def _google_auth_enabled(self):
        with override_settings(
            FREUDD_AUTH_GOOGLE_ENABLED=True,
            SOCIALACCOUNT_PROVIDERS={
                "google": {
                    "APP": {
                        "client_id": "test-google-client-id",
                        "secret": "test-google-client-secret",
                        "key": "",
                    },
                    "SCOPE": ["profile", "email"],
                }
            },
        ):
            self._reload_root_urlconf()
            try:
                yield
            finally:
                self._reload_root_urlconf()

    def test_signup_creates_user_and_logs_in(self) -> None:
        response = self.client.post(
            reverse("signup"),
            {
                "username": "new-user",
                "email": "new@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("progress"))
        self.assertTrue(User.objects.filter(username="new-user").exists())
        self.assertIn("_auth_user_id", self.client.session)

    def test_signup_duplicate_username_shows_error(self) -> None:
        self._create_user(username="taken")
        response = self.client.post(
            reverse("signup"),
            {
                "username": "taken",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("username", response.context["form"].errors)

    def test_signup_requires_email(self) -> None:
        response = self.client.post(
            reverse("signup"),
            {
                "username": "",
                "email": "",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)

    def test_signup_allows_blank_username_and_generates_username(self) -> None:
        response = self.client.post(
            reverse("signup"),
            {
                "username": "",
                "email": "new.user@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("progress"))
        created = User.objects.get(email="new.user@example.com")
        self.assertTrue(created.username)
        self.assertIn("_auth_user_id", self.client.session)

    def test_login_bad_password(self) -> None:
        self._create_user(username="alice", password="Secret123!!")
        response = self.client.post(
            reverse("login"),
            {
                "username": "alice",
                "password": "wrong-password",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].non_field_errors())

    def test_login_rejects_external_next_redirect(self) -> None:
        self._create_user(username="alice", password="Secret123!!")
        response = self.client.post(
            f"{reverse('login')}?next=https://example.com/steal",
            {
                "username": "alice",
                "password": "Secret123!!",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("progress"))

    def test_login_allows_local_next_redirect(self) -> None:
        self._create_user(username="alice", password="Secret123!!")
        response = self.client.post(
            f"{reverse('login')}?next={reverse('quiz-wrapper', kwargs={'quiz_id': self.quiz_id})}",
            {
                "username": "alice",
                "password": "Secret123!!",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("quiz-wrapper", kwargs={"quiz_id": self.quiz_id}))

    def test_google_button_hidden_when_feature_disabled(self) -> None:
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Fortsæt med Google")
        self.assertEqual(self.client.get("/accounts/google/login/").status_code, 404)

    def test_google_button_visible_when_feature_enabled(self) -> None:
        with self._google_auth_enabled():
            response = self.client.get(reverse("login"))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Fortsæt med Google")
            self.assertContains(response, 'action="/accounts/google/login/"')

    def test_google_button_does_not_render_external_next_value(self) -> None:
        with self._google_auth_enabled():
            response = self.client.get(f"{reverse('login')}?next=https://example.com/steal")
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'name="next" value="https://example.com/steal"')
            self.assertNotContains(response, "example.com/steal")
            self.assertContains(response, 'action="/accounts/google/login/"')

    def test_google_login_post_initiates_oauth_redirect(self) -> None:
        with self._google_auth_enabled():
            response = self.client.post("/accounts/google/login/")
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith("https://accounts.google.com/o/oauth2/v2/auth"))

    def test_google_login_get_renders_confirmation_when_login_on_get_disabled(self) -> None:
        with self._google_auth_enabled():
            response = self.client.get("/accounts/google/login/")
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Fortsæt")

    def test_socialaccount_connections_available_for_authenticated_user(self) -> None:
        with self._google_auth_enabled():
            user = self._create_user()
            self.client.force_login(user)
            response = self.client.get("/accounts/3rdparty/")
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Forbind Google-konto")

    def test_logout_requires_post_and_clears_session(self) -> None:
        self._create_user()
        self._login()
        response = self.client.post(reverse("logout"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_quiz_wrapper_allows_anonymous_without_pre_summary_login_prompts(self) -> None:
        quiz_url = reverse("quiz-wrapper", kwargs={"quiz_id": self.quiz_id})
        response = self.client.get(quiz_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Uge 1, forelæsning 1")
        self.assertContains(response, "Episode")
        self.assertNotContains(response, "Tag quizzen anonymt.")
        self.assertNotContains(response, "Log ind for ")
        self.assertContains(response, "Quizzen er færdig. Log ind nu for at gemme din score og se din samlede score.")
        self.assertContains(response, 'id="quiz-points-feedback"')
        self.assertContains(response, "Optjent:")
        self.assertContains(response, f"{reverse('login')}?{urlencode({'next': quiz_url})}")
        self.assertContains(response, f"{reverse('signup')}?{urlencode({'next': quiz_url})}")

    def test_quiz_wrapper_does_not_persist_partial_progress_in_local_storage(self) -> None:
        response = self.client.get(reverse("quiz-wrapper", kwargs={"quiz_id": self.quiz_id}))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'setItem("quiz-local-state:')

    def test_quiz_wrapper_formats_complex_episode_title(self) -> None:
        self._write_links_file(
            {
                self.quiz_id: {
                    "title": "W1L1 - Alle kilder [EN] {type=audio lang=en format=deep-dive length=long sources=2 hash=f104a13e}.mp3",
                    "difficulty": "medium",
                }
            }
        )
        quiz_url = reverse("quiz-wrapper", kwargs={"quiz_id": self.quiz_id})
        response = self.client.get(quiz_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Uge 1, forelæsning 1")
        self.assertContains(response, "Alle kilder")
        self.assertNotContains(response, "Deep dive")
        self.assertNotContains(response, f"ID {self.quiz_id}")
        self.assertNotContains(response, "hash=f104a13e")
        self.assertNotContains(response, ".mp3")

    def test_quiz_wrapper_hides_anonymous_end_prompt_for_logged_in_user(self) -> None:
        self._create_user()
        self._login()
        response = self.client.get(reverse("quiz-wrapper", kwargs={"quiz_id": self.quiz_id}))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Quizzen er færdig. Log ind nu for at gemme din score og se din samlede score.")

    def test_quiz_raw_is_public_and_serves_html(self) -> None:
        response = self.client.get(reverse("quiz-raw", kwargs={"quiz_id": self.quiz_id}))
        self.assertEqual(response.status_code, 200)
        content = b"".join(response.streaming_content).decode("utf-8")
        self.assertIn("<app-root", content)

    def test_quiz_content_api_is_public_and_returns_questions(self) -> None:
        response = self.client.get(reverse("quiz-content", kwargs={"quiz_id": self.quiz_id}))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["title"], "Personality Quiz")
        self.assertEqual(len(payload["questions"]), 2)

    def test_quiz_content_api_falls_back_to_html_when_json_missing(self) -> None:
        (self.quiz_root / f"{self.quiz_id}.json").unlink()
        response = self.client.get(reverse("quiz-content", kwargs={"quiz_id": self.quiz_id}))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["title"], "Quiz")
        self.assertEqual(len(payload["questions"]), 2)

    def test_quiz_content_api_returns_404_when_quiz_files_are_unreadable(self) -> None:
        with patch("quizzes.services.Path.is_file", side_effect=PermissionError("denied")):
            response = self.client.get(reverse("quiz-content", kwargs={"quiz_id": self.quiz_id}))
        self.assertEqual(response.status_code, 404)

    def test_state_apis_redirect_when_anonymous(self) -> None:
        state_url = reverse("quiz-state", kwargs={"quiz_id": self.quiz_id})
        raw_state_url = reverse("quiz-state-raw", kwargs={"quiz_id": self.quiz_id})

        response = self.client.get(state_url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(f"{reverse('login')}?next="))

        response = self.client.post(state_url, data=json.dumps({}), content_type="application/json")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(f"{reverse('login')}?next="))

        response = self.client.get(raw_state_url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(f"{reverse('login')}?next="))

        response = self.client.post(raw_state_url, data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(f"{reverse('login')}?next="))

    def test_invalid_quiz_id_is_rejected(self) -> None:
        self._create_user()
        self._login()
        response = self.client.get("/q/nothexid.html")
        self.assertEqual(response.status_code, 404)
        response = self.client.get("/api/quiz-content/nothexid")
        self.assertEqual(response.status_code, 404)
        response = self.client.get("/api/quiz-state/nothexid")
        self.assertEqual(response.status_code, 404)

    def test_valid_but_unknown_quiz_id_returns_404(self) -> None:
        self._create_user()
        self._login()
        unknown_id = "aaaaaaaa"

        response = self.client.get(reverse("quiz-wrapper", kwargs={"quiz_id": unknown_id}))
        self.assertEqual(response.status_code, 404)

        response = self.client.get(reverse("quiz-raw", kwargs={"quiz_id": unknown_id}))
        self.assertEqual(response.status_code, 404)

        response = self.client.get(reverse("quiz-content", kwargs={"quiz_id": unknown_id}))
        self.assertEqual(response.status_code, 404)

        response = self.client.get(reverse("quiz-state", kwargs={"quiz_id": unknown_id}))
        self.assertEqual(response.status_code, 404)

        response = self.client.post(
            reverse("quiz-state", kwargs={"quiz_id": unknown_id}),
            data=json.dumps(
                {
                    "userAnswers": {"0": 1},
                    "currentQuestionIndex": 0,
                    "hiddenQuestionIndices": [],
                    "currentView": "question",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

        response = self.client.get(reverse("quiz-state-raw", kwargs={"quiz_id": unknown_id}))
        self.assertEqual(response.status_code, 404)

    def test_raw_state_get_does_not_create_progress(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        raw_url = reverse("quiz-state-raw", kwargs={"quiz_id": self.quiz_id})
        response = self.client.get(raw_url)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json())
        self.assertFalse(QuizProgress.objects.filter(user=user, quiz_id=self.quiz_id).exists())

    def test_state_api_roundtrip_and_completion_transitions(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        state_url = reverse("quiz-state", kwargs={"quiz_id": self.quiz_id})
        response = self.client.get(state_url)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json())

        first_payload = {
            "userAnswers": {"0": 1},
            "currentQuestionIndex": 0,
            "hiddenQuestionIndices": [],
            "currentView": "question",
        }
        response = self.client.post(state_url, data=json.dumps(first_payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "in_progress")

        progress = QuizProgress.objects.get(user=user, quiz_id=self.quiz_id)
        self.assertEqual(progress.answers_count, 1)
        self.assertEqual(progress.question_count, 2)
        self.assertEqual(progress.status, QuizProgress.Status.IN_PROGRESS)

        completed_payload = {
            "userAnswers": {"0": 1, "1": 2},
            "currentQuestionIndex": 1,
            "hiddenQuestionIndices": [],
            "currentView": "summary",
        }
        response = self.client.post(state_url, data=json.dumps(completed_payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "completed")

        progress.refresh_from_db()
        first_completed_at = progress.completed_at
        self.assertIsNotNone(first_completed_at)

        response = self.client.post(state_url, data=json.dumps(first_payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "in_progress")

        progress.refresh_from_db()
        self.assertEqual(progress.status, QuizProgress.Status.IN_PROGRESS)
        self.assertEqual(progress.completed_at, first_completed_at)

        response = self.client.post(state_url, data=json.dumps(completed_payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "completed")

        progress.refresh_from_db()
        self.assertEqual(progress.completed_at, first_completed_at)

        response = self.client.get(state_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["currentView"], "summary")

    def test_state_api_allows_timed_out_questions_to_complete_quiz(self) -> None:
        user = self._create_user()
        self.client.force_login(user)
        state_url = reverse("quiz-state", kwargs={"quiz_id": self.quiz_id})

        payload = {
            "userAnswers": {"0": 0},
            "currentQuestionIndex": 1,
            "hiddenQuestionIndices": [],
            "currentView": "summary",
            "timedOutQuestionIndices": [1],
            "questionDeadlineEpochMs": {},
        }
        response = self.client.post(state_url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "completed")

        progress = QuizProgress.objects.get(user=user, quiz_id=self.quiz_id)
        self.assertEqual(progress.answers_count, 2)
        self.assertEqual(progress.status, QuizProgress.Status.COMPLETED)

    def test_state_api_blocks_quiz_reset_while_cooldown_active(self) -> None:
        user = self._create_user()
        self.client.force_login(user)
        state_url = reverse("quiz-state", kwargs={"quiz_id": self.quiz_id})

        completed_payload = {
            "userAnswers": {"0": 0, "1": 1},
            "currentQuestionIndex": 1,
            "hiddenQuestionIndices": [],
            "currentView": "summary",
        }
        response = self.client.post(state_url, data=json.dumps(completed_payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["cooldown"]["is_blocked"])

        reset_payload = {
            "userAnswers": {},
            "currentQuestionIndex": 0,
            "hiddenQuestionIndices": [],
            "currentView": "question",
        }
        response = self.client.post(state_url, data=json.dumps(reset_payload), content_type="application/json")
        self.assertEqual(response.status_code, 429)
        body = response.json()
        self.assertEqual(body["error"], "cooldown_active")
        self.assertTrue(body["cooldown"]["is_blocked"])

    def test_state_api_allows_quiz_reset_after_full_cooldown_reset_window(self) -> None:
        user = self._create_user()
        self.client.force_login(user)
        state_url = reverse("quiz-state", kwargs={"quiz_id": self.quiz_id})

        completed_payload = {
            "userAnswers": {"0": 0, "1": 1},
            "currentQuestionIndex": 1,
            "hiddenQuestionIndices": [],
            "currentView": "summary",
        }
        response = self.client.post(state_url, data=json.dumps(completed_payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)

        progress = QuizProgress.objects.get(user=user, quiz_id=self.quiz_id)
        progress.retry_streak_count = 4
        progress.last_attempt_completed_at = timezone.now() - timedelta(hours=2)
        progress.retry_cooldown_until_at = timezone.now() - timedelta(minutes=5)
        progress.save(
            update_fields=[
                "retry_streak_count",
                "last_attempt_completed_at",
                "retry_cooldown_until_at",
                "updated_at",
            ]
        )

        reset_payload = {
            "userAnswers": {},
            "currentQuestionIndex": 0,
            "hiddenQuestionIndices": [],
            "currentView": "question",
        }
        response = self.client.post(state_url, data=json.dumps(reset_payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "in_progress")
        self.assertFalse(response.json()["cooldown"]["is_blocked"])

        progress.refresh_from_db()
        self.assertEqual(progress.retry_streak_count, 0)
        self.assertIsNone(progress.retry_cooldown_until_at)

    def test_state_api_rejects_invalid_schema(self) -> None:
        self._create_user()
        self._login()

        state_url = reverse("quiz-state", kwargs={"quiz_id": self.quiz_id})
        response = self.client.post(state_url, data=json.dumps([1, 2]), content_type="application/json")
        self.assertEqual(response.status_code, 400)

        response = self.client.post(
            state_url,
            data=json.dumps({"userAnswers": "bad", "currentQuestionIndex": 0, "hiddenQuestionIndices": [], "currentView": "question"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.post(
            state_url,
            data=json.dumps({"userAnswers": {}, "currentQuestionIndex": 0}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_raw_state_api_roundtrip(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        raw_url = reverse("quiz-state-raw", kwargs={"quiz_id": self.quiz_id})
        response = self.client.get(raw_url)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json())

        payload = "[1,2,3]"
        response = self.client.post(raw_url, data=payload, content_type="application/json")
        self.assertEqual(response.status_code, 200)

        progress = QuizProgress.objects.get(user=user, quiz_id=self.quiz_id)
        self.assertEqual(progress.raw_state_payload, payload)

        response = self.client.get(raw_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)

    def test_raw_state_api_rejects_non_json(self) -> None:
        self._create_user()
        self._login()

        raw_url = reverse("quiz-state-raw", kwargs={"quiz_id": self.quiz_id})
        response = self.client.post(raw_url, data="not-json", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_progress_page_uses_quiz_links_labels(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        QuizProgress.objects.create(
            user=user,
            quiz_id=self.quiz_id,
            status=QuizProgress.Status.COMPLETED,
            state_json={
                "userAnswers": {"0": 1, "1": 2},
                "currentQuestionIndex": 1,
                "hiddenQuestionIndices": [],
                "currentView": "summary",
            },
            answers_count=2,
            question_count=2,
            last_view="summary",
            completed_at=timezone.now(),
            last_attempt_completed_at=timezone.now(),
        )

        response = self.client.get(reverse("progress"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Uge 1, forelæsning 1")
        self.assertContains(response, "Episode")
        self.assertContains(response, "Mellem · 2 spørgsmål")
        self.assertContains(response, "Senest åbnet fag")

    def test_progress_page_quiz_history_shows_completed_status_and_correct_answers(self) -> None:
        user = self._create_user()
        self.client.force_login(user)
        completed_at = timezone.now() - timedelta(minutes=20)

        QuizProgress.objects.create(
            user=user,
            quiz_id=self.quiz_id,
            status=QuizProgress.Status.IN_PROGRESS,
            state_json={},
            answers_count=1,
            question_count=10,
            last_view="question",
            completed_at=completed_at,
            last_attempt_completed_at=completed_at,
            leaderboard_best_correct_answers=5,
            leaderboard_best_question_count=10,
        )

        response = self.client.get(reverse("progress"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rigtige svar")
        self.assertContains(response, "Fuldført")
        self.assertNotContains(response, "I gang")
        self.assertContains(response, "5 / 10")

    def test_load_quiz_label_mapping_reads_subject_slug(self) -> None:
        labels = load_quiz_label_mapping()
        label = labels[self.quiz_id]
        self.assertEqual(label.subject_slug, "personlighedspsykologi")

    def test_load_quiz_label_mapping_fallbacks_to_link_subject_slug(self) -> None:
        self.links_file.write_text(
            json.dumps(
                {
                    "by_name": {
                        "W1L1 - Episode": {
                            "relative_path": f"{self.quiz_id}.html",
                            "difficulty": "medium",
                            "links": [
                                {
                                    "relative_path": f"{self.quiz_id}.html",
                                    "difficulty": "medium",
                                    "format": "html",
                                    "subject_slug": "personlighedspsykologi",
                                }
                            ],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        labels = load_quiz_label_mapping()
        self.assertEqual(labels[self.quiz_id].subject_slug, "personlighedspsykologi")

    def test_load_quiz_label_mapping_invalid_subject_slug_becomes_none(self) -> None:
        self.links_file.write_text(
            json.dumps(
                {
                    "by_name": {
                        "W1L1 - Episode": {
                            "relative_path": f"{self.quiz_id}.html",
                            "difficulty": "medium",
                            "subject_slug": "bad slug",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        labels = load_quiz_label_mapping()
        self.assertIsNone(labels[self.quiz_id].subject_slug)

    def test_progress_page_shows_subject_cards_without_semester(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        response = self.client.get(reverse("progress"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Aktivt semester")
        self.assertNotContains(response, "Gem semester")
        self.assertContains(response, "Personlighedspsykologi")
        self.assertContains(response, "Mine fag")
        self.assertContains(response, "Tilmeld")

    def test_progress_page_shows_personal_tracking_and_leaderboard_sections(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        response = self.client.get(reverse("progress"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Personlig tracking")
        self.assertContains(response, "Offentlig quizliga")
        self.assertContains(response, reverse("leaderboard-profile"))

    def test_progress_page_moves_enrollment_controls_to_bottom_module(self) -> None:
        user = self._create_user()
        self.client.force_login(user)
        SubjectEnrollment.objects.create(user=user, subject_slug="personlighedspsykologi")

        response = self.client.get(reverse("progress"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tilmeld og afmeld fag")

        body = response.content.decode("utf-8")
        mine_fag_start = body.find("<h2 class=\"section-title\">Mine fag</h2>")
        tracking_start = body.find("<h2 class=\"section-title\">Personlig tracking</h2>")
        self.assertGreaterEqual(mine_fag_start, 0)
        self.assertGreaterEqual(tracking_start, 0)
        mine_fag_markup = body[mine_fag_start:tracking_start]
        self.assertNotIn(">Afmeld</button>", mine_fag_markup)
        self.assertNotIn(">Tilmeld</button>", mine_fag_markup)

        history_start = body.find("<h2 class=\"section-title\">Quizhistorik</h2>")
        enroll_start = body.find("<h2 class=\"section-title\">Tilmeld og afmeld fag</h2>")
        self.assertGreaterEqual(history_start, 0)
        self.assertGreaterEqual(enroll_start, 0)
        self.assertGreater(enroll_start, history_start)

    def test_progress_page_locks_existing_quizliga_alias_by_default(self) -> None:
        user = self._create_user()
        self.client.force_login(user)
        UserLeaderboardProfile.objects.create(
            user=user,
            public_alias="LockedAlias",
            public_alias_normalized="lockedalias",
            is_public=True,
        )

        response = self.client.get(reverse("progress"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alias er låst for at undgå utilsigtede ændringer.")
        self.assertContains(response, "Ændr alias")
        self.assertNotContains(response, 'name="allow_alias_change" value="1"')

        response = self.client.get(f"{reverse('progress')}?edit_alias=1")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="allow_alias_change" value="1"')
        self.assertContains(response, "Annuller alias-ændring")

    def test_leaderboard_page_is_public(self) -> None:
        response = self.client.get(
            reverse("leaderboard-subject", kwargs={"subject_slug": "personlighedspsykologi"})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "quizliga")

    def test_base_nav_contains_quizliga_link(self) -> None:
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("leaderboard-subject", kwargs={"subject_slug": "personlighedspsykologi"}),
        )

    def test_leaderboard_profile_requires_login(self) -> None:
        response = self.client.post(
            reverse("leaderboard-profile"),
            {
                "public_alias": "AliasOne",
                "is_public": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(f"{reverse('login')}?next="))

    def test_leaderboard_profile_alias_is_case_insensitive_unique(self) -> None:
        first = self._create_user(username="first-user")
        second = self._create_user(username="second-user")
        UserLeaderboardProfile.objects.create(
            user=first,
            public_alias="Alias",
            public_alias_normalized="alias",
            is_public=True,
        )

        self.client.force_login(second)
        response = self.client.post(
            reverse("leaderboard-profile"),
            {
                "public_alias": "alias",
                "is_public": "1",
                "next": reverse("progress"),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("progress"))
        self.assertFalse(UserLeaderboardProfile.objects.filter(user=second).exists())

    def test_leaderboard_profile_alias_change_requires_explicit_flag_when_alias_exists(self) -> None:
        user = self._create_user()
        self.client.force_login(user)
        UserLeaderboardProfile.objects.create(
            user=user,
            public_alias="FixedAlias",
            public_alias_normalized="fixedalias",
            is_public=True,
        )

        response = self.client.post(
            reverse("leaderboard-profile"),
            {
                "public_alias": "AttemptedAlias",
                "is_public": "1",
                "next": reverse("progress"),
            },
        )
        self.assertEqual(response.status_code, 302)
        profile = UserLeaderboardProfile.objects.get(user=user)
        self.assertEqual(profile.public_alias, "FixedAlias")

        response = self.client.post(
            reverse("leaderboard-profile"),
            {
                "public_alias": "UpdatedAlias",
                "allow_alias_change": "1",
                "is_public": "1",
                "next": reverse("progress"),
            },
        )
        self.assertEqual(response.status_code, 302)
        profile.refresh_from_db()
        self.assertEqual(profile.public_alias, "UpdatedAlias")
        self.assertEqual(profile.public_alias_normalized, "updatedalias")

    def test_leaderboard_opt_out_hides_user_but_keeps_alias(self) -> None:
        user = self._create_user()
        self.client.force_login(user)
        QuizProgress.objects.create(
            user=user,
            quiz_id=self.quiz_id,
            status=QuizProgress.Status.COMPLETED,
            state_json={},
            answers_count=2,
            question_count=2,
            last_view="summary",
            completed_at=timezone.now(),
        )

        response = self.client.post(
            reverse("leaderboard-profile"),
            {
                "public_alias": "PublicAlias",
                "is_public": "1",
                "next": reverse("progress"),
            },
        )
        self.assertEqual(response.status_code, 302)

        response = self.client.get(
            reverse("leaderboard-subject", kwargs={"subject_slug": "personlighedspsykologi"})
        )
        self.assertContains(response, "PublicAlias")

        response = self.client.post(
            reverse("leaderboard-profile"),
            {
                "public_alias": "",
                "next": reverse("progress"),
            },
        )
        self.assertEqual(response.status_code, 302)

        profile = UserLeaderboardProfile.objects.get(user=user)
        self.assertFalse(profile.is_public)
        self.assertEqual(profile.public_alias, "PublicAlias")
        self.assertEqual(profile.public_alias_normalized, "publicalias")

        response = self.client.get(
            reverse("leaderboard-subject", kwargs={"subject_slug": "personlighedspsykologi"})
        )
        self.assertNotContains(response, "PublicAlias")

    def test_leaderboard_scoring_tiebreak_and_subject_filtering(self) -> None:
        second_quiz_id = "aaaaaaaa"
        other_subject_quiz = "bbbbbbbb"
        self._write_quiz_file(second_quiz_id, question_count=2)
        self._write_quiz_json_file(second_quiz_id, question_count=2)
        self._write_quiz_file(other_subject_quiz, question_count=2)
        self._write_quiz_json_file(other_subject_quiz, question_count=2)
        self._write_links_file(
            {
                self.quiz_id: {
                    "title": "W1L1 - Episode",
                    "difficulty": "medium",
                    "subject_slug": "personlighedspsykologi",
                },
                second_quiz_id: {
                    "title": "W1L1 - Episode Two",
                    "difficulty": "medium",
                    "subject_slug": "personlighedspsykologi",
                },
                other_subject_quiz: {
                    "title": "W1L1 - Other Subject Quiz",
                    "difficulty": "medium",
                    "subject_slug": "other-subject",
                },
            }
        )

        user_a = self._create_user(username="alpha")
        user_b = self._create_user(username="beta")
        UserLeaderboardProfile.objects.create(
            user=user_a,
            public_alias="Alpha",
            public_alias_normalized="alpha",
            is_public=True,
        )
        UserLeaderboardProfile.objects.create(
            user=user_b,
            public_alias="Beta",
            public_alias_normalized="beta",
            is_public=True,
        )

        QuizProgress.objects.create(
            user=user_a,
            quiz_id=self.quiz_id,
            status=QuizProgress.Status.COMPLETED,
            state_json={},
            answers_count=2,
            question_count=2,
            last_view="summary",
            completed_at=datetime(2026, 1, 2, 10, 0, tzinfo=dt_timezone.utc),
        )
        QuizProgress.objects.create(
            user=user_a,
            quiz_id=second_quiz_id,
            status=QuizProgress.Status.COMPLETED,
            state_json={},
            answers_count=2,
            question_count=2,
            last_view="summary",
            completed_at=datetime(2026, 1, 3, 10, 0, tzinfo=dt_timezone.utc),
        )
        QuizProgress.objects.create(
            user=user_b,
            quiz_id=self.quiz_id,
            status=QuizProgress.Status.COMPLETED,
            state_json={},
            answers_count=2,
            question_count=2,
            last_view="summary",
            completed_at=datetime(2026, 1, 2, 11, 0, tzinfo=dt_timezone.utc),
        )
        QuizProgress.objects.create(
            user=user_b,
            quiz_id=second_quiz_id,
            status=QuizProgress.Status.COMPLETED,
            state_json={},
            answers_count=2,
            question_count=2,
            last_view="summary",
            completed_at=datetime(2026, 1, 4, 10, 0, tzinfo=dt_timezone.utc),
        )
        QuizProgress.objects.create(
            user=user_b,
            quiz_id=other_subject_quiz,
            status=QuizProgress.Status.COMPLETED,
            state_json={},
            answers_count=2,
            question_count=2,
            last_view="summary",
            completed_at=datetime(2026, 1, 5, 10, 0, tzinfo=dt_timezone.utc),
        )

        response = self.client.get(
            reverse("leaderboard-subject", kwargs={"subject_slug": "personlighedspsykologi"})
        )
        self.assertEqual(response.status_code, 200)
        entries = response.context["entries"]
        self.assertEqual(entries[0]["alias"], "Alpha")
        self.assertEqual(entries[1]["alias"], "Beta")
        self.assertEqual(entries[0]["quiz_count"], 2)
        self.assertEqual(entries[1]["quiz_count"], 2)

    def test_leaderboard_scoring_uses_points_before_quiz_count(self) -> None:
        second_quiz_id = "aaaaaaaa"
        self._write_quiz_file(second_quiz_id, question_count=2)
        self._write_quiz_json_file(second_quiz_id, question_count=2)
        self._write_links_file(
            {
                self.quiz_id: {
                    "title": "W1L1 - Episode",
                    "difficulty": "medium",
                    "subject_slug": "personlighedspsykologi",
                },
                second_quiz_id: {
                    "title": "W1L1 - Episode Two",
                    "difficulty": "medium",
                    "subject_slug": "personlighedspsykologi",
                },
            }
        )

        user_a = self._create_user(username="alpha-points")
        user_b = self._create_user(username="beta-points")
        UserLeaderboardProfile.objects.create(
            user=user_a,
            public_alias="AlphaPoints",
            public_alias_normalized="alphapoints",
            is_public=True,
        )
        UserLeaderboardProfile.objects.create(
            user=user_b,
            public_alias="BetaPoints",
            public_alias_normalized="betapoints",
            is_public=True,
        )

        season_key = active_half_year_season(datetime(2026, 2, 1, 0, 0, tzinfo=dt_timezone.utc)).key
        QuizProgress.objects.create(
            user=user_a,
            quiz_id=self.quiz_id,
            status=QuizProgress.Status.COMPLETED,
            state_json={},
            answers_count=2,
            question_count=2,
            last_view="summary",
            completed_at=datetime(2026, 1, 2, 10, 0, tzinfo=dt_timezone.utc),
            leaderboard_season_key=season_key,
            leaderboard_best_score=100,
            leaderboard_best_correct_answers=1,
            leaderboard_best_question_count=2,
            leaderboard_best_duration_ms=60000,
            leaderboard_best_reached_at=datetime(2026, 1, 2, 10, 0, tzinfo=dt_timezone.utc),
        )
        QuizProgress.objects.create(
            user=user_a,
            quiz_id=second_quiz_id,
            status=QuizProgress.Status.COMPLETED,
            state_json={},
            answers_count=2,
            question_count=2,
            last_view="summary",
            completed_at=datetime(2026, 1, 3, 10, 0, tzinfo=dt_timezone.utc),
            leaderboard_season_key=season_key,
            leaderboard_best_score=100,
            leaderboard_best_correct_answers=1,
            leaderboard_best_question_count=2,
            leaderboard_best_duration_ms=60000,
            leaderboard_best_reached_at=datetime(2026, 1, 3, 10, 0, tzinfo=dt_timezone.utc),
        )
        QuizProgress.objects.create(
            user=user_b,
            quiz_id=self.quiz_id,
            status=QuizProgress.Status.COMPLETED,
            state_json={},
            answers_count=2,
            question_count=2,
            last_view="summary",
            completed_at=datetime(2026, 1, 2, 11, 0, tzinfo=dt_timezone.utc),
            leaderboard_season_key=season_key,
            leaderboard_best_score=250,
            leaderboard_best_correct_answers=2,
            leaderboard_best_question_count=2,
            leaderboard_best_duration_ms=20000,
            leaderboard_best_reached_at=datetime(2026, 1, 2, 11, 0, tzinfo=dt_timezone.utc),
        )

        response = self.client.get(
            reverse("leaderboard-subject", kwargs={"subject_slug": "personlighedspsykologi"})
        )
        self.assertEqual(response.status_code, 200)
        entries = response.context["entries"]
        self.assertEqual(entries[0]["alias"], "BetaPoints")
        self.assertEqual(entries[0]["score_points"], 250)
        self.assertEqual(entries[0]["quiz_count"], 1)
        self.assertEqual(entries[1]["alias"], "AlphaPoints")
        self.assertEqual(entries[1]["score_points"], 200)
        self.assertEqual(entries[1]["quiz_count"], 2)

    def test_half_year_season_boundaries(self) -> None:
        jan_start = active_half_year_season(datetime(2026, 1, 1, 0, 0, tzinfo=dt_timezone.utc))
        self.assertEqual(jan_start.key, "2026-H1")
        self.assertEqual(jan_start.start_at.isoformat(), "2026-01-01T00:00:00+00:00")
        self.assertEqual(jan_start.end_at.isoformat(), "2026-07-01T00:00:00+00:00")

        june_end = active_half_year_season(datetime(2026, 6, 30, 23, 59, 59, tzinfo=dt_timezone.utc))
        self.assertEqual(june_end.key, "2026-H1")
        self.assertEqual(june_end.end_at.isoformat(), "2026-07-01T00:00:00+00:00")

        july_start = active_half_year_season(datetime(2026, 7, 1, 0, 0, tzinfo=dt_timezone.utc))
        self.assertEqual(july_start.key, "2026-H2")
        self.assertEqual(july_start.start_at.isoformat(), "2026-07-01T00:00:00+00:00")
        self.assertEqual(july_start.end_at.isoformat(), "2027-01-01T00:00:00+00:00")

    def test_semester_update_endpoint_is_removed(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        response = self.client.post("/preferences/semester", {"semester": "F26"})
        self.assertEqual(response.status_code, 404)

    def test_default_design_system_renders_in_html_attribute(self) -> None:
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-design-system="paper-studio"')

    def test_design_system_cookie_override_is_ignored_for_unsupported_theme(self) -> None:
        self.client.cookies[settings.FREUDD_DESIGN_SYSTEM_COOKIE_NAME] = "night-lab"
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-design-system="paper-studio"')

    def test_design_system_query_override_is_ignored_for_unsupported_theme(self) -> None:
        response = self.client.get(f"{reverse('login')}?ds=night-lab&preview=1")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-design-system="paper-studio"')

    def test_design_system_invalid_cookie_falls_back_to_default(self) -> None:
        self.client.cookies[settings.FREUDD_DESIGN_SYSTEM_COOKIE_NAME] = "not-a-theme"
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-design-system="paper-studio"')

    def test_design_system_switcher_is_removed_from_progress_page(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        response = self.client.get(reverse("progress"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="progress-design-system-select"')

    def test_design_system_preference_endpoint_is_removed(self) -> None:
        response = self.client.post("/preferences/design-system", {"design_system": "paper-studio"})
        self.assertEqual(response.status_code, 404)

    def test_authenticated_user_preference_wins_over_cookie(self) -> None:
        user = self._create_user()
        UserInterfacePreference.objects.create(user=user, design_system="paper-studio")
        self.client.force_login(user)
        self.client.cookies[settings.FREUDD_DESIGN_SYSTEM_COOKIE_NAME] = "night-lab"

        response = self.client.get(reverse("progress"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-design-system="paper-studio"')

    def test_authenticated_user_unsupported_preference_falls_back_to_default(self) -> None:
        user = self._create_user()
        UserInterfacePreference.objects.create(user=user, design_system="classic")
        self.client.force_login(user)

        response = self.client.get(reverse("progress"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-design-system="paper-studio"')

    def test_subject_enroll_and_unenroll_are_idempotent(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        enroll_url = reverse("subject-enroll", kwargs={"subject_slug": "personlighedspsykologi"})
        unenroll_url = reverse("subject-unenroll", kwargs={"subject_slug": "personlighedspsykologi"})

        response = self.client.post(enroll_url, {"next": reverse("progress")})
        self.assertEqual(response.status_code, 302)
        response = self.client.post(enroll_url, {"next": reverse("progress")})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            SubjectEnrollment.objects.filter(user=user, subject_slug="personlighedspsykologi").count(),
            1,
        )

        response = self.client.post(unenroll_url, {"next": reverse("progress")})
        self.assertEqual(response.status_code, 302)
        response = self.client.post(unenroll_url, {"next": reverse("progress")})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            SubjectEnrollment.objects.filter(user=user, subject_slug="personlighedspsykologi").exists()
        )

    def test_subject_detail_is_accessible_without_enrollment_and_lists_readings(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        detail_url = reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Ikke tilmeldt")
        self.assertNotContains(response, "Tilmeldt")
        self.assertNotContains(response, "Udvid alle")
        self.assertNotContains(response, "Luk alle")
        self.assertNotContains(response, "overview-grid")
        self.assertNotContains(response, "<h2>Læringssti</h2>", html=True)
        self.assertNotContains(response, "Næste fokus")
        self.assertNotContains(response, "Trin ")
        self.assertNotContains(response, "Låst")
        self.assertContains(response, "Uge 1, forelæsning 1")
        self.assertContains(response, "Introforelaesning")
        self.assertContains(response, "data-active-lecture-key=\"W01L1\"")
        self.assertContains(response, "lecture-rail-item")
        self.assertNotContains(response, "lecture-details")
        self.assertNotContains(response, "timeline-item")
        self.assertNotContains(response, "Introforelaesning (Forelaesning 1, 2026-02-02)")
        self.assertContains(response, "Quiz for alle kilder")
        self.assertContains(response, "reading-difficulties")
        self.assertContains(response, "Ikke startet endnu")
        self.assertContains(response, "Grundbog kapitel 01 - Introduktion til personlighedspsykologi")
        self.assertContains(response, "Uge 1, forelæsning 1: Introforelaesning")
        self.assertNotContains(response, "Mangler kilde")
        self.assertNotContains(response, "Koutsoumpis (2025)")
        self.assertNotContains(response, "Tilmeld fag")
        self.assertNotContains(response, "Afmeld fag")

        body = response.content.decode("utf-8")
        readings_pos = body.find('class="lecture-section lecture-readings"')
        podcasts_pos = body.find('class="lecture-section lecture-podcasts"')
        quizzes_pos = body.find('class="lecture-section lecture-quizzes"')
        self.assertGreaterEqual(readings_pos, 0)
        self.assertGreaterEqual(podcasts_pos, 0)
        self.assertGreaterEqual(quizzes_pos, 0)
        self.assertLess(readings_pos, podcasts_pos)
        self.assertLess(podcasts_pos, quizzes_pos)

        self.assertEqual(response.context["active_lecture"]["lecture_key"], "W01L1")
        self.assertEqual(len(response.context["lecture_rail_items"]), 2)
        self.assertTrue(response.context["lecture_rail_items"][0]["is_active"])
        self.assertFalse(response.context["lecture_rail_items"][1]["is_active"])

    def test_subject_detail_query_param_selects_active_lecture(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        detail_url = reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"})
        response = self.client.get(f"{detail_url}?lecture=W01L2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_lecture"]["lecture_key"], "W01L2")
        self.assertContains(response, "data-active-lecture-key=\"W01L2\"")
        self.assertContains(response, "Koutsoumpis (2025)")
        self.assertTrue(response.context["lecture_rail_items"][1]["is_active"])
        self.assertFalse(response.context["lecture_rail_items"][0]["is_active"])
        self.assertTrue(response.context["lecture_rail_items"][0]["is_past"])
        self.assertFalse(response.context["lecture_rail_items"][1]["is_past"])
        self.assertContains(response, 'class="lecture-rail-item  is-past ')

    def test_subject_detail_invalid_query_param_falls_back_to_default_lecture(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        detail_url = reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"})
        response = self.client.get(f"{detail_url}?lecture=DOES_NOT_EXIST")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_lecture"]["lecture_key"], "W01L1")
        self.assertContains(response, "data-active-lecture-key=\"W01L1\"")

    def test_subject_detail_omits_kpi_strip_and_toolbar_controls(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        response = self.client.get(reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"}))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "overview-grid")
        self.assertNotContains(response, "Udvid alle")
        self.assertNotContains(response, "Luk alle")
        self.assertNotContains(response, "subject_path_overview")

    def test_subject_detail_renders_rail_links_for_each_lecture(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        detail_url = reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        rail_items = response.context["lecture_rail_items"]
        self.assertEqual(len(rail_items), 2)
        self.assertEqual(rail_items[0]["lecture_key"], "W01L1")
        self.assertEqual(rail_items[1]["lecture_key"], "W01L2")
        self.assertTrue(rail_items[0]["lecture_url"].endswith("?lecture=W01L1"))
        self.assertTrue(rail_items[1]["lecture_url"].endswith("?lecture=W01L2"))
        self.assertContains(response, 'class="lecture-rail-copy"')
        self.assertContains(response, 'href="/subjects/personlighedspsykologi?lecture=W01L1"')

    @override_settings(FREUDD_SUBJECT_DETAIL_SHOW_READING_QUIZZES=False)
    def test_subject_detail_always_shows_reading_difficulty_indicators(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        response = self.client.get(reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "reading-difficulties")
        self.assertContains(response, "difficulty-chip is-easy")
        self.assertContains(response, "difficulty-chip is-medium")
        self.assertContains(response, "difficulty-chip is-hard")

    def test_subject_detail_hides_question_count_when_quiz_file_is_missing(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        with patch(
            "quizzes.views.get_subject_learning_path_snapshot",
            return_value={
                "lectures": [
                    {
                        "lecture_key": "W01L1",
                        "lecture_title": "W01L1 Intro",
                        "status": "active",
                        "completed_quizzes": 0,
                        "total_quizzes": 1,
                        "lecture_assets": {
                            "quizzes": [
                                {
                                    "quiz_id": "ffffffff",
                                    "difficulty": "medium",
                                    "quiz_url": "/q/ffffffff.html",
                                }
                            ],
                            "podcasts": [],
                        },
                        "readings": [],
                    }
                ],
                "source_meta": {},
            },
        ):
            response = self.client.get(reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mellem")
        self.assertNotContains(response, "· 0 spørgsmål")
        self.assertNotContains(response, "Ukendt")

    def test_subject_detail_orders_quiz_links_easy_medium_hard(self) -> None:
        enriched = _enrich_subject_path_lectures(
            [
                {
                    "lecture_key": "W01L1",
                    "lecture_title": "W01L1 Intro",
                    "status": "active",
                    "completed_quizzes": 0,
                    "total_quizzes": 3,
                    "lecture_assets": {
                        "quizzes": [
                            {"quiz_id": "hard-1", "difficulty": "hard", "quiz_url": "/q/hard-1.html"},
                            {"quiz_id": "easy-1", "difficulty": "easy", "quiz_url": "/q/easy-1.html"},
                            {"quiz_id": "medium-1", "difficulty": "medium", "quiz_url": "/q/medium-1.html"},
                        ],
                        "podcasts": [],
                    },
                    "readings": [],
                }
            ]
        )

        self.assertEqual(
            [quiz["difficulty"] for quiz in enriched[0]["lecture_assets"]["quizzes"]],
            ["easy", "medium", "hard"],
        )

    def test_subject_detail_shows_spotify_links_for_mapped_podcasts(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        response = self.client.get(reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "class=\"podcast-inline-trigger\"")
        self.assertNotContains(response, "class=\"podcast-play\"")
        self.assertNotContains(response, "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8")
        self.assertNotContains(response, "https://open.spotify.com/episode/4w4gHCXnQK5fjQdsxQO0XG")
        self.assertContains(
            response,
            "data-spotify-embed-url=\"https://open.spotify.com/embed/episode/5m0hYfDU9ThM5qR2xMugr8?utm_source=generator\"",
        )
        self.assertContains(
            response,
            "data-spotify-embed-url=\"https://open.spotify.com/embed/episode/4w4gHCXnQK5fjQdsxQO0XG?utm_source=generator\"",
        )
        self.assertContains(response, "data-spotify-player-frame")
        self.assertNotContains(response, "https://example.test/podcast/w01l1-alle-kilder.mp3")
        self.assertNotContains(response, "https://example.test/podcast/w01l1-intro.mp3")

    def test_subject_detail_hides_podcast_rows_when_spotify_episode_map_missing(self) -> None:
        user = self._create_user()
        self.client.force_login(user)
        self._write_spotify_map({})
        clear_content_service_caches()

        response = self.client.get(reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"}))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "https://open.spotify.com/episode/")
        self.assertNotContains(response, "data-spotify-embed-url=")
        self.assertNotContains(response, "https://open.spotify.com/search/")
        self.assertNotContains(response, "Find i Spotify")
        self.assertNotContains(response, "https://example.test/podcast/w01l1-alle-kilder.mp3")
        self.assertNotContains(response, "https://example.test/podcast/w01l1-intro.mp3")
        self.assertContains(response, "Ingen podcasts registreret i denne forelæsning.")

    def test_subject_detail_podcast_duration_label_is_optional(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        with patch(
            "quizzes.views.get_subject_learning_path_snapshot",
            return_value={
                "lectures": [
                    {
                        "lecture_key": "W01L1",
                        "lecture_title": "W01L1 Intro",
                        "status": "active",
                        "completed_quizzes": 0,
                        "total_quizzes": 2,
                        "lecture_assets": {
                            "quizzes": [
                                {"quiz_id": "aaaaaaaa", "difficulty": "easy", "quiz_url": "/q/aaaaaaaa.html"},
                                {"quiz_id": "bbbbbbbb", "difficulty": "medium", "quiz_url": "/q/bbbbbbbb.html"},
                            ],
                            "podcasts": [
                                {
                                    "title": "U1F1 · [Podcast] · Introduktion til kurset",
                                    "url": "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8",
                                    "duration_label": "15 min",
                                },
                                {
                                    "title": "U1F1 · [Podcast] · Hvad er personlighed?",
                                    "url": "https://open.spotify.com/episode/4w4gHCXnQK5fjQdsxQO0XG",
                                },
                            ],
                        },
                        "readings": [],
                    }
                ],
                "source_meta": {},
            },
        ):
            response = self.client.get(reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ep. 1: Introduktion til kurset (15 min)")
        self.assertContains(response, "Ep. 2: Hvad er personlighed?")
        self.assertContains(
            response,
            "data-spotify-embed-url=\"https://open.spotify.com/embed/episode/5m0hYfDU9ThM5qR2xMugr8?utm_source=generator\"",
        )

    def test_subject_detail_shows_private_tracking_controls(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        response = self.client.get(reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Markér læst")
        self.assertContains(response, "Markér lyttet")

    def test_subject_detail_shows_open_reading_link_for_available_file(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        response = self.client.get(reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"}))
        self.assertEqual(response.status_code, 200)
        lecture = response.context["active_lecture"]
        reading = lecture["readings"][0]
        expected_url = reverse(
            "subject-open-reading",
            kwargs={
                "subject_slug": "personlighedspsykologi",
                "reading_key": reading["reading_key"],
            },
        )
        self.assertContains(response, expected_url)
        self.assertContains(response, "åbn tekst")

    def test_subject_open_reading_requires_login(self) -> None:
        user = self._create_user()
        self.client.force_login(user)
        detail = self.client.get(reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"}))
        reading_key = detail.context["active_lecture"]["readings"][0]["reading_key"]
        self.client.logout()

        response = self.client.get(
            reverse(
                "subject-open-reading",
                kwargs={
                    "subject_slug": "personlighedspsykologi",
                    "reading_key": reading_key,
                },
            )
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response.url)

    def test_subject_open_reading_serves_pdf_inline(self) -> None:
        user = self._create_user()
        self.client.force_login(user)
        detail = self.client.get(reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"}))
        reading_key = detail.context["active_lecture"]["readings"][0]["reading_key"]

        response = self.client.get(
            reverse(
                "subject-open-reading",
                kwargs={
                    "subject_slug": "personlighedspsykologi",
                    "reading_key": reading_key,
                },
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("inline", response.get("Content-Disposition", ""))

    def test_subject_open_reading_serves_docx_as_attachment(self) -> None:
        user = self._create_user()
        self.client.force_login(user)
        (self.reading_files_root / "W01L1" / "Custom.docx").write_bytes(b"DOCX")

        with patch(
            "quizzes.views.get_subject_learning_path_snapshot",
            return_value={
                "lectures": [
                    {
                        "lecture_key": "W01L1",
                        "readings": [
                            {
                                "reading_key": "w01l1-custom-1234",
                                "source_filename": "Custom.docx",
                            }
                        ],
                    }
                ]
            },
        ):
            response = self.client.get(
                reverse(
                    "subject-open-reading",
                    kwargs={
                        "subject_slug": "personlighedspsykologi",
                        "reading_key": "w01l1-custom-1234",
                    },
                )
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertIn("attachment", response.get("Content-Disposition", ""))

    def test_subject_open_reading_returns_404_when_file_is_missing(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        with patch(
            "quizzes.views.get_subject_learning_path_snapshot",
            return_value={
                "lectures": [
                    {
                        "lecture_key": "W01L1",
                        "readings": [
                            {
                                "reading_key": "w01l1-missing-1234",
                                "source_filename": "DoesNotExist.pdf",
                            }
                        ],
                    }
                ]
            },
        ):
            response = self.client.get(
                reverse(
                    "subject-open-reading",
                    kwargs={
                        "subject_slug": "personlighedspsykologi",
                        "reading_key": "w01l1-missing-1234",
                    },
                )
            )
        self.assertEqual(response.status_code, 404)

    def test_subject_open_reading_rejects_path_traversal_source_filename(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        with patch(
            "quizzes.views.get_subject_learning_path_snapshot",
            return_value={
                "lectures": [
                    {
                        "lecture_key": "W01L1",
                        "readings": [
                            {
                                "reading_key": "w01l1-evil-1234",
                                "source_filename": "../secret.pdf",
                            }
                        ],
                    }
                ]
            },
        ):
            response = self.client.get(
                reverse(
                    "subject-open-reading",
                    kwargs={
                        "subject_slug": "personlighedspsykologi",
                        "reading_key": "w01l1-evil-1234",
                    },
                )
            )
        self.assertEqual(response.status_code, 404)

    def test_subject_open_reading_blocks_excluded_reading_keys(self) -> None:
        user = self._create_user()
        self.client.force_login(user)
        detail = self.client.get(reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"}))
        reading_key = detail.context["active_lecture"]["readings"][0]["reading_key"]
        open_url = reverse(
            "subject-open-reading",
            kwargs={
                "subject_slug": "personlighedspsykologi",
                "reading_key": reading_key,
            },
        )

        self._write_reading_download_exclusions([reading_key])
        from quizzes import views as quiz_views

        quiz_views._READING_EXCLUSION_CACHE["path"] = None
        quiz_views._READING_EXCLUSION_CACHE["mtime"] = None
        quiz_views._READING_EXCLUSION_CACHE["data"] = {}

        blocked_detail = self.client.get(reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"}))
        self.assertNotContains(blocked_detail, open_url)

        blocked_open = self.client.get(open_url)
        self.assertEqual(blocked_open.status_code, 404)

    def test_subject_reading_tracking_toggle_is_idempotent(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        detail_url = reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"})
        detail_response = self.client.get(detail_url)
        lecture = detail_response.context["subject_path_lectures"][0]
        reading = lecture["readings"][0]

        track_url = reverse(
            "subject-tracking-reading",
            kwargs={"subject_slug": "personlighedspsykologi"},
        )
        payload = {
            "next": detail_url,
            "lecture_key": lecture["lecture_key"],
            "reading_key": reading["reading_key"],
            "action": "mark",
        }
        response = self.client.post(track_url, payload)
        self.assertEqual(response.status_code, 302)
        response = self.client.post(track_url, payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            UserReadingMark.objects.filter(
                user=user,
                subject_slug="personlighedspsykologi",
                lecture_key=lecture["lecture_key"],
                reading_key=reading["reading_key"],
            ).count(),
            1,
        )

        payload["action"] = "unmark"
        response = self.client.post(track_url, payload)
        self.assertEqual(response.status_code, 302)
        response = self.client.post(track_url, payload)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            UserReadingMark.objects.filter(
                user=user,
                subject_slug="personlighedspsykologi",
                lecture_key=lecture["lecture_key"],
                reading_key=reading["reading_key"],
            ).exists()
        )

    def test_subject_podcast_tracking_toggle_is_idempotent_with_stable_key(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        detail_url = reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"})
        first_response = self.client.get(detail_url)
        lecture = first_response.context["subject_path_lectures"][0]
        lecture_podcasts = lecture["lecture_assets"]["podcasts"]
        self.assertGreaterEqual(len(lecture_podcasts), 1)
        first_key = lecture_podcasts[0]["podcast_key"]

        second_response = self.client.get(detail_url)
        second_key = second_response.context["subject_path_lectures"][0]["lecture_assets"]["podcasts"][0][
            "podcast_key"
        ]
        self.assertEqual(first_key, second_key)

        track_url = reverse(
            "subject-tracking-podcast",
            kwargs={"subject_slug": "personlighedspsykologi"},
        )
        payload = {
            "next": detail_url,
            "lecture_key": lecture["lecture_key"],
            "podcast_key": first_key,
            "action": "mark",
        }
        response = self.client.post(track_url, payload)
        self.assertEqual(response.status_code, 302)
        response = self.client.post(track_url, payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            UserPodcastMark.objects.filter(
                user=user,
                subject_slug="personlighedspsykologi",
                lecture_key=lecture["lecture_key"],
                reading_key__isnull=True,
                podcast_key=first_key,
            ).count(),
            1,
        )

        payload["action"] = "unmark"
        response = self.client.post(track_url, payload)
        self.assertEqual(response.status_code, 302)
        response = self.client.post(track_url, payload)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            UserPodcastMark.objects.filter(
                user=user,
                subject_slug="personlighedspsykologi",
                lecture_key=lecture["lecture_key"],
                reading_key__isnull=True,
                podcast_key=first_key,
            ).exists()
        )

    def test_subject_detail_hides_enrollment_badge_for_enrolled_user(self) -> None:
        user = self._create_user()
        SubjectEnrollment.objects.create(user=user, subject_slug="personlighedspsykologi")
        self.client.force_login(user)

        detail_url = reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Tilmeldt")
        self.assertNotContains(response, "Ikke tilmeldt")
        self.assertContains(response, "lecture-rail-item")
        self.assertNotContains(response, "Afmeld fag")

    def test_subject_detail_handles_snapshot_failure_without_500(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        with patch("quizzes.views.get_subject_learning_path_snapshot", side_effect=RuntimeError("boom")):
            response = self.client.get(reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Læringsstien kunne ikke indlæses lige nu")
        self.assertContains(response, "Ingen læringssti endnu for dette fag.")

    def test_subject_detail_has_no_next_focus_or_step_copy_after_progress_updates(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        state_url = reverse("quiz-state", kwargs={"quiz_id": self.quiz_id})
        payload = {
            "userAnswers": {"0": 1},
            "currentQuestionIndex": 0,
            "hiddenQuestionIndices": [],
            "currentView": "question",
        }
        response = self.client.post(state_url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)

        detail_url = reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Næste fokus")
        self.assertNotContains(response, "Start nu")
        self.assertNotContains(response, "Trin ")

    def test_subject_detail_keeps_path_even_when_quiz_subject_slug_missing(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        self.links_file.write_text(
            json.dumps(
                {
                    "by_name": {
                        "W1L1 - Episode": {
                            "relative_path": f"{self.quiz_id}.html",
                            "difficulty": "medium",
                            "links": [
                                {
                                    "relative_path": f"{self.quiz_id}.html",
                                    "difficulty": "medium",
                                    "format": "html",
                                }
                            ],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        detail_url = reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "lecture-rail-item")
        self.assertContains(response, "data-active-lecture-key=\"W01L1\"")
        self.assertContains(response, "Grundbog kapitel 01 - Introduktion til personlighedspsykologi")

    def test_unknown_subject_slug_returns_404_for_all_subject_endpoints(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        detail_url = reverse("subject-detail", kwargs={"subject_slug": "unknown-subject"})
        enroll_url = reverse("subject-enroll", kwargs={"subject_slug": "unknown-subject"})
        unenroll_url = reverse("subject-unenroll", kwargs={"subject_slug": "unknown-subject"})

        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 404)
        response = self.client.post(enroll_url)
        self.assertEqual(response.status_code, 404)
        response = self.client.post(unenroll_url)
        self.assertEqual(response.status_code, 404)

    def test_progress_hides_stale_subject_enrollments_not_in_catalog(self) -> None:
        user = self._create_user()
        self.client.force_login(user)
        SubjectEnrollment.objects.create(user=user, subject_slug="legacy-subject")

        response = self.client.get(reverse("progress"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Personlighedspsykologi")
        self.assertNotContains(response, "legacy-subject")

    def test_topmenu_context_lists_enrolled_subjects(self) -> None:
        user = self._create_user()
        self.client.force_login(user)
        SubjectEnrollment.objects.create(user=user, subject_slug="personlighedspsykologi")

        response = self.client.get(reverse("progress"))
        self.assertEqual(response.status_code, 200)
        subjects = response.context["topmenu_enrolled_subjects"]
        self.assertEqual(len(subjects), 1)
        self.assertEqual(subjects[0]["slug"], "personlighedspsykologi")
        self.assertEqual(subjects[0]["title"], "Personlighedspsykologi")
        self.assertEqual(
            subjects[0]["detail_url"],
            reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"}),
        )
        self.assertContains(
            response,
            '<a class="nav-action nav-action-subject" href="/subjects/personlighedspsykologi">Personlighedspsykologi</a>',
            html=True,
        )
        self.assertContains(
            response,
            '<button class="nav-text-button" type="submit">Log ud</button>',
            html=True,
        )
        self.assertNotContains(response, "Forbind Google")

    def test_topmenu_context_hides_stale_subject_enrollments(self) -> None:
        user = self._create_user()
        self.client.force_login(user)
        SubjectEnrollment.objects.create(user=user, subject_slug="legacy-subject")

        response = self.client.get(reverse("progress"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["topmenu_enrolled_subjects"], tuple())
        self.assertNotContains(
            response,
            '<a class="nav-action nav-action-subject" href="/subjects/legacy-subject">legacy-subject</a>',
            html=True,
        )

    def test_progress_handles_missing_subject_catalog_file(self) -> None:
        user = self._create_user()
        self.client.force_login(user)
        self.subjects_file.unlink()
        clear_subject_service_caches()

        response = self.client.get(reverse("progress"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fagkataloget kunne ikke indlæses.")

    def test_progress_handles_invalid_subject_catalog_payload(self) -> None:
        user = self._create_user()
        self.client.force_login(user)
        self.subjects_file.write_text("{not-json", encoding="utf-8")
        clear_subject_service_caches()

        response = self.client.get(reverse("progress"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fagkataloget kunne ikke indlæses.")

    def test_subject_detail_uses_fallback_when_primary_master_key_missing(self) -> None:
        user = self._create_user()
        self.client.force_login(user)
        self.reading_master_file.unlink()
        clear_subject_service_caches()
        clear_content_service_caches()

        response = self.client.get(reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"}))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Tekst-nøglen kunne ikke indlæses.")
        self.assertContains(response, "Uge 1, forelæsning 1")

    def test_subject_detail_shows_error_when_both_master_and_fallback_missing(self) -> None:
        user = self._create_user()
        self.client.force_login(user)
        self.reading_master_file.unlink()
        self.reading_fallback_file.unlink()
        clear_subject_service_caches()
        clear_content_service_caches()

        response = self.client.get(reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tekst-nøglen kunne ikke indlæses.")
        self.assertContains(response, "Ingen læringssti endnu for dette fag.")

    def test_state_post_requires_csrf(self) -> None:
        user = self._create_user()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(user)

        state_url = reverse("quiz-state", kwargs={"quiz_id": self.quiz_id})
        payload = {
            "userAnswers": {"0": 1},
            "currentQuestionIndex": 0,
            "hiddenQuestionIndices": [],
            "currentView": "question",
        }

        response = csrf_client.post(state_url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 403)

    def test_subject_posts_require_csrf(self) -> None:
        user = self._create_user()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(user)
        detail_url = reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"})
        detail_response = csrf_client.get(detail_url)
        lecture = detail_response.context["subject_path_lectures"][0]
        reading = lecture["readings"][0]
        podcast_key = lecture["lecture_assets"]["podcasts"][0]["podcast_key"]

        response = csrf_client.post(
            reverse("subject-enroll", kwargs={"subject_slug": "personlighedspsykologi"}),
            {"next": reverse("progress")},
        )
        self.assertEqual(response.status_code, 403)

        response = csrf_client.post(
            reverse("subject-unenroll", kwargs={"subject_slug": "personlighedspsykologi"}),
            {"next": reverse("progress")},
        )
        self.assertEqual(response.status_code, 403)

        response = csrf_client.post(
            reverse("subject-tracking-reading", kwargs={"subject_slug": "personlighedspsykologi"}),
            {
                "next": detail_url,
                "lecture_key": lecture["lecture_key"],
                "reading_key": reading["reading_key"],
                "action": "mark",
            },
        )
        self.assertEqual(response.status_code, 403)

        response = csrf_client.post(
            reverse("subject-tracking-podcast", kwargs={"subject_slug": "personlighedspsykologi"}),
            {
                "next": detail_url,
                "lecture_key": lecture["lecture_key"],
                "podcast_key": podcast_key,
                "action": "mark",
            },
        )
        self.assertEqual(response.status_code, 403)

        response = csrf_client.post(
            reverse("leaderboard-profile"),
            {
                "public_alias": "AliasOne",
                "is_public": "1",
                "next": reverse("progress"),
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_quiz_state_updates_gamification_models(self) -> None:
        user = self._create_user()
        self.client.force_login(user)
        state_url = reverse("quiz-state", kwargs={"quiz_id": self.quiz_id})

        first_payload = {
            "userAnswers": {"0": 1},
            "currentQuestionIndex": 0,
            "hiddenQuestionIndices": [],
            "currentView": "question",
        }
        response = self.client.post(state_url, data=json.dumps(first_payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)

        completed_payload = {
            "userAnswers": {"0": 1, "1": 2},
            "currentQuestionIndex": 1,
            "hiddenQuestionIndices": [],
            "currentView": "summary",
        }
        response = self.client.post(
            state_url,
            data=json.dumps(completed_payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        profile = UserGamificationProfile.objects.get(user=user)
        self.assertEqual(profile.xp_total, 60)
        self.assertGreaterEqual(profile.current_level, 1)

        daily = DailyGamificationStat.objects.get(user=user)
        self.assertEqual(daily.answered_delta, 2)
        self.assertEqual(daily.completed_delta, 1)

        units = list(UserUnitProgress.objects.filter(user=user))
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0].unit_key, "W01")
        self.assertEqual(units[0].status, UserUnitProgress.Status.COMPLETED)
        self.assertFalse(
            UserUnitProgress.objects.filter(user=user, status="locked").exists()
        )

        lectures = list(UserLectureProgress.objects.filter(user=user).order_by("sequence_index"))
        self.assertEqual(len(lectures), 2)
        self.assertEqual(lectures[0].lecture_key, "W01L1")
        self.assertEqual(lectures[0].status, UserLectureProgress.Status.COMPLETED)
        self.assertEqual(lectures[1].lecture_key, "W01L2")
        self.assertEqual(lectures[1].status, UserLectureProgress.Status.ACTIVE)
        self.assertFalse(
            UserLectureProgress.objects.filter(user=user, status="locked").exists()
        )

        readings = list(
            UserReadingProgress.objects.filter(
                user=user,
                subject_slug="personlighedspsykologi",
                lecture_key="W01L1",
            ).order_by("sequence_index")
        )
        self.assertEqual(len(readings), 2)
        self.assertEqual(readings[0].status, UserReadingProgress.Status.NO_QUIZ)
        self.assertEqual(readings[1].status, UserReadingProgress.Status.NO_QUIZ)
        self.assertFalse(
            UserReadingProgress.objects.filter(user=user, status="locked").exists()
        )

    def test_progress_page_hides_learning_path_section(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        response = self.client.get(reverse("progress"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Læringssti")
        self.assertNotContains(response, "Næste fokus")
        self.assertNotContains(response, "Extensions")

    def test_gamification_api_requires_login_and_returns_snapshot(self) -> None:
        url = reverse("gamification-me")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

        user = self._create_user()
        self.client.force_login(user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("profile", payload)
        self.assertIn("daily", payload)
        self.assertIn("units", payload)
        self.assertIn("extensions", payload)

    def test_extension_sync_endpoint_is_removed(self) -> None:
        response = self.client.post("/api/extensions/sync", data=json.dumps({}), content_type="application/json")
        self.assertEqual(response.status_code, 404)

    def test_extension_commands_are_idempotent(self) -> None:
        user = self._create_user()

        call_command(
            "extension_access",
            "--user",
            user.username,
            "--extension",
            "anki",
            "--enable",
            stdout=io.StringIO(),
        )
        call_command(
            "extension_access",
            "--user",
            user.username,
            "--extension",
            "anki",
            "--enable",
            stdout=io.StringIO(),
        )
        self.assertEqual(
            UserExtensionAccess.objects.filter(user=user, extension="anki", enabled=True).count(),
            1,
        )

        call_command(
            "extension_access",
            "--user",
            user.username,
            "--extension",
            "anki",
            "--disable",
            stdout=io.StringIO(),
        )
        self.assertFalse(
            UserExtensionAccess.objects.get(user=user, extension="anki").enabled
        )

    def test_extension_credentials_commands_store_encrypted_payload(self) -> None:
        user = self._create_user()

        call_command(
            "extension_credentials",
            "--user",
            user.username,
            "--extension",
            "habitica",
            "--set",
            "--habitica-user-id",
            "habitica-user",
            "--habitica-api-token",
            "secret-token",
            "--habitica-task-id",
            "task-123",
            stdout=io.StringIO(),
        )
        credential = UserExtensionCredential.objects.get(user=user, extension="habitica")
        self.assertNotIn("secret-token", credential.encrypted_payload)

        show_out = io.StringIO()
        call_command(
            "extension_credentials",
            "--user",
            user.username,
            "--extension",
            "habitica",
            "--show-meta",
            stdout=show_out,
        )
        metadata_payload = json.loads(show_out.getvalue().strip())
        self.assertTrue(metadata_payload["exists"])
        self.assertEqual(metadata_payload["meta"]["extension"], "habitica")
        self.assertNotIn("secret-token", show_out.getvalue())

        call_command(
            "extension_credentials",
            "--user",
            user.username,
            "--extension",
            "habitica",
            "--rotate-key-version",
            stdout=io.StringIO(),
        )
        credential.refresh_from_db()
        self.assertIsNotNone(credential.rotated_at)

        call_command(
            "extension_credentials",
            "--user",
            user.username,
            "--extension",
            "habitica",
            "--clear",
            stdout=io.StringIO(),
        )
        self.assertFalse(
            UserExtensionCredential.objects.filter(user=user, extension="habitica").exists()
        )

    @patch("quizzes.gamification_services.requests.post")
    def test_sync_extensions_updates_access_and_ledger_and_is_idempotent(self, mock_post) -> None:
        class _Response:
            status_code = 200

            @staticmethod
            def json() -> dict[str, object]:
                return {"success": True}

        mock_post.return_value = _Response()

        user = self._create_user()
        call_command(
            "extension_access",
            "--user",
            user.username,
            "--extension",
            "habitica",
            "--enable",
            stdout=io.StringIO(),
        )
        call_command(
            "extension_credentials",
            "--user",
            user.username,
            "--extension",
            "habitica",
            "--set",
            "--habitica-user-id",
            "habitica-user",
            "--habitica-api-token",
            "secret-token",
            "--habitica-task-id",
            "task-123",
            stdout=io.StringIO(),
        )

        call_command("sync_extensions", "--extension", "habitica", stdout=io.StringIO())
        access = UserExtensionAccess.objects.get(user=user, extension="habitica")
        self.assertEqual(access.last_sync_status, UserExtensionAccess.SyncStatus.OK)
        self.assertIsNotNone(access.last_sync_at)
        self.assertEqual(
            ExtensionSyncLedger.objects.filter(user=user, extension="habitica").count(),
            1,
        )

        call_command("sync_extensions", "--extension", "habitica", stdout=io.StringIO())
        self.assertEqual(
            ExtensionSyncLedger.objects.filter(user=user, extension="habitica").count(),
            1,
        )

    @patch("quizzes.gamification_services.requests.post")
    def test_sync_extensions_handles_missing_credentials_and_continues_batch(self, mock_post) -> None:
        class _Response:
            status_code = 200

            @staticmethod
            def json() -> dict[str, object]:
                return {"success": True}

        mock_post.return_value = _Response()

        good_user = self._create_user(username="good-user")
        bad_user = self._create_user(username="bad-user")

        for target_user in (good_user, bad_user):
            call_command(
                "extension_access",
                "--user",
                target_user.username,
                "--extension",
                "habitica",
                "--enable",
                stdout=io.StringIO(),
            )

        call_command(
            "extension_credentials",
            "--user",
            good_user.username,
            "--extension",
            "habitica",
            "--set",
            "--habitica-user-id",
            "habitica-user",
            "--habitica-api-token",
            "secret-token",
            "--habitica-task-id",
            "task-123",
            stdout=io.StringIO(),
        )

        with self.assertRaises(CommandError):
            call_command("sync_extensions", "--extension", "habitica", stdout=io.StringIO())

        good_access = UserExtensionAccess.objects.get(user=good_user, extension="habitica")
        bad_access = UserExtensionAccess.objects.get(user=bad_user, extension="habitica")
        self.assertEqual(good_access.last_sync_status, UserExtensionAccess.SyncStatus.OK)
        self.assertEqual(bad_access.last_sync_status, UserExtensionAccess.SyncStatus.ERROR)
        self.assertIn("Missing extension credentials", bad_access.last_sync_error)

        self.assertEqual(
            ExtensionSyncLedger.objects.filter(user=good_user, extension="habitica").count(),
            1,
        )
        self.assertEqual(
            ExtensionSyncLedger.objects.filter(user=bad_user, extension="habitica").count(),
            1,
        )

    def test_sync_extensions_dry_run_does_not_write(self) -> None:
        user = self._create_user()
        call_command(
            "extension_access",
            "--user",
            user.username,
            "--extension",
            "habitica",
            "--enable",
            stdout=io.StringIO(),
        )

        with self.assertRaises(CommandError):
            call_command("sync_extensions", "--extension", "habitica", "--dry-run", stdout=io.StringIO())

        access = UserExtensionAccess.objects.get(user=user, extension="habitica")
        self.assertEqual(access.last_sync_status, UserExtensionAccess.SyncStatus.IDLE)
        self.assertFalse(
            ExtensionSyncLedger.objects.filter(user=user, extension="habitica").exists()
        )

    def test_rebuild_content_manifest_command_writes_manifest(self) -> None:
        output = io.StringIO()
        call_command(
            "rebuild_content_manifest",
            "--subject",
            "personlighedspsykologi",
            stdout=output,
        )
        self.assertTrue(self.content_manifest_file.exists())
        payload = json.loads(self.content_manifest_file.read_text(encoding="utf-8"))
        self.assertEqual(payload["subject_slug"], "personlighedspsykologi")
        self.assertEqual(len(payload["lectures"]), 2)
        summary = json.loads(output.getvalue().strip())
        self.assertEqual(summary["lectures"], 2)
        self.assertGreaterEqual(summary["quiz_assets"], 1)

    def test_rebuild_content_manifest_strict_fails_on_warnings(self) -> None:
        self.rss_file.unlink()
        with self.assertRaises(CommandError):
            call_command(
                "rebuild_content_manifest",
                "--subject",
                "personlighedspsykologi",
                "--strict",
                stdout=io.StringIO(),
            )

    def test_gamification_recompute_command_runs_for_single_user(self) -> None:
        user = self._create_user()
        output = io.StringIO()
        call_command("gamification_recompute", "--user", user.username, stdout=output)
        self.assertIn("Recomputed gamification", output.getvalue())

    def test_language_configuration_is_danish_only(self) -> None:
        self.assertEqual(settings.LANGUAGE_CODE, "da")
        self.assertEqual(settings.LANGUAGES, [("da", "Dansk")])
