from __future__ import annotations

import html
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from quizzes import services as quiz_services
from quizzes.content_services import clear_content_service_caches
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
    UserReadingProgress,
    UserUnitProgress,
)
from quizzes.services import load_quiz_label_mapping
from quizzes.subject_services import clear_subject_service_caches
from quizzes.theme_resolver import DESIGN_SYSTEM_SESSION_PREVIEW_KEY
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

        self.override = override_settings(
            QUIZ_FILES_ROOT=self.quiz_root,
            QUIZ_LINKS_JSON_PATH=self.links_file,
            FREUDD_SUBJECTS_JSON_PATH=self.subjects_file,
            FREUDD_READING_MASTER_KEY_PATH=self.reading_master_file,
            FREUDD_READING_MASTER_KEY_FALLBACK_PATH=self.reading_fallback_file,
            FREUDD_SUBJECT_FEED_RSS_PATH=self.rss_file,
            FREUDD_SUBJECT_SPOTIFY_MAP_PATH=self.spotify_map_file,
            FREUDD_SUBJECT_CONTENT_MANIFEST_PATH=self.content_manifest_file,
            FREUDD_CREDENTIALS_MASTER_KEY="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
            FREUDD_CREDENTIALS_KEY_VERSION=1,
            FREUDD_EXT_SYNC_TIMEOUT_SECONDS=2,
            QUIZ_SIGNUP_RATE_LIMIT=1000,
            QUIZ_LOGIN_RATE_LIMIT=1000,
        )
        self.override.enable()
        self.addCleanup(self.override.disable)
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

    def _create_user(self, username: str = "alice", password: str = "Secret123!!") -> User:
        return User.objects.create_user(username=username, password=password)

    def _login(self, username: str = "alice", password: str = "Secret123!!") -> None:
        self.client.login(username=username, password=password)

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
        self.assertContains(response, f"{reverse('login')}?{urlencode({'next': quiz_url})}")
        self.assertContains(response, f"{reverse('signup')}?{urlencode({'next': quiz_url})}")

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
        )

        response = self.client.get(reverse("progress"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Uge 1, forelæsning 1")
        self.assertContains(response, "Episode")
        self.assertContains(response, "Mellem · 2 spørgsmål")
        self.assertContains(response, "Senest åbnet fag")

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

    def test_semester_update_endpoint_is_removed(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        response = self.client.post("/preferences/semester", {"semester": "F26"})
        self.assertEqual(response.status_code, 404)

    def test_default_design_system_renders_in_html_attribute(self) -> None:
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-design-system="classic"')

    def test_design_system_cookie_applies_for_anonymous_request(self) -> None:
        self.client.cookies[settings.FREUDD_DESIGN_SYSTEM_COOKIE_NAME] = "night-lab"
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-design-system="night-lab"')

    def test_design_system_query_override_wins_over_cookie(self) -> None:
        self.client.cookies[settings.FREUDD_DESIGN_SYSTEM_COOKIE_NAME] = "night-lab"
        response = self.client.get(f"{reverse('login')}?ds=paper-studio")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-design-system="paper-studio"')

    def test_design_system_invalid_cookie_falls_back_to_default(self) -> None:
        self.client.cookies[settings.FREUDD_DESIGN_SYSTEM_COOKIE_NAME] = "not-a-theme"
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-design-system="classic"')

    def test_design_system_preview_query_persists_session_override(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        response = self.client.get(f"{reverse('progress')}?ds=night-lab&preview=1")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-design-system="night-lab"')
        self.assertEqual(self.client.session.get(DESIGN_SYSTEM_SESSION_PREVIEW_KEY), "night-lab")

        response = self.client.get(reverse("progress"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-design-system="night-lab"')

        clear_response = self.client.post(
            reverse("design-system-preference"),
            {
                "design_system": "classic",
                "clear_preview": "1",
                "persist": "0",
                "next": reverse("progress"),
            },
        )
        self.assertEqual(clear_response.status_code, 302)
        self.assertNotIn(DESIGN_SYSTEM_SESSION_PREVIEW_KEY, self.client.session)

    def test_design_system_preference_endpoint_sets_cookie_for_anonymous(self) -> None:
        response = self.client.post(
            reverse("design-system-preference"),
            {"design_system": "night-lab", "next": reverse("login")},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("login"))
        self.assertEqual(
            response.cookies[settings.FREUDD_DESIGN_SYSTEM_COOKIE_NAME].value,
            "night-lab",
        )

    def test_design_system_preference_preview_only_sets_session_without_cookie_or_db(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        response = self.client.post(
            reverse("design-system-preference"),
            {
                "design_system": "night-lab",
                "preview": "1",
                "persist": "0",
                "next": reverse("progress"),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("progress"))
        self.assertEqual(self.client.session.get(DESIGN_SYSTEM_SESSION_PREVIEW_KEY), "night-lab")
        self.assertFalse(UserInterfacePreference.objects.filter(user=user).exists())
        self.assertNotIn(settings.FREUDD_DESIGN_SYSTEM_COOKIE_NAME, response.cookies)

    def test_design_system_preference_endpoint_persists_for_authenticated_user(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        response = self.client.post(
            reverse("design-system-preference"),
            {"design_system": "paper-studio", "next": reverse("progress")},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("progress"))
        pref = UserInterfacePreference.objects.get(user=user)
        self.assertEqual(pref.design_system, "paper-studio")

        response = self.client.get(reverse("progress"))
        self.assertContains(response, 'data-design-system="paper-studio"')

    def test_design_system_preference_endpoint_rejects_invalid_key(self) -> None:
        response = self.client.post(
            reverse("design-system-preference"),
            {"design_system": "invalid-theme"},
        )
        self.assertEqual(response.status_code, 400)

    def test_authenticated_user_preference_wins_over_cookie(self) -> None:
        user = self._create_user()
        UserInterfacePreference.objects.create(user=user, design_system="paper-studio")
        self.client.force_login(user)
        self.client.cookies[settings.FREUDD_DESIGN_SYSTEM_COOKIE_NAME] = "night-lab"

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
        self.assertContains(response, "Udvid alle")
        self.assertNotContains(response, "<h2>Læringssti</h2>", html=True)
        self.assertNotContains(response, "Næste fokus")
        self.assertNotContains(response, "Trin ")
        self.assertNotContains(response, "Låst")
        self.assertContains(response, "Uge 1, forelæsning 1")
        self.assertContains(response, "class=\"lecture-module\"")
        self.assertContains(response, "Introforelaesning")
        self.assertNotContains(response, "Uge 1, forelæsning 1 · Introforelaesning")
        self.assertNotContains(response, "W01L1 ·")
        self.assertNotContains(response, "Introforelaesning (Forelaesning 1, 2026-02-02)")
        self.assertContains(response, "timeline-item")
        self.assertContains(response, "lecture-details")
        self.assertNotContains(response, "lecture-details\" open")
        self.assertContains(response, "Quiz for alle kilder")
        self.assertContains(response, "Mellem · 2 spørgsmål")
        self.assertContains(response, "Ikke startet endnu")
        self.assertNotContains(response, ">Aktiv<")
        self.assertContains(response, "Grundbog kapitel 01 - Introduktion til personlighedspsykologi")
        self.assertContains(response, "Mangler kilde")
        self.assertContains(response, "Koutsoumpis (2025)")
        self.assertNotContains(response, "Tilmeld fag")
        self.assertNotContains(response, "Afmeld fag")

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
        self.assertContains(response, "Spotify")
        self.assertContains(response, "class=\"asset-link is-spotify\"")
        self.assertContains(response, "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8")
        self.assertContains(response, "https://open.spotify.com/episode/4w4gHCXnQK5fjQdsxQO0XG")
        self.assertNotContains(response, "https://example.test/podcast/w01l1-alle-kilder.mp3")
        self.assertNotContains(response, "https://example.test/podcast/w01l1-intro.mp3")

    def test_subject_detail_hides_unmapped_podcast_links(self) -> None:
        user = self._create_user()
        self.client.force_login(user)
        self._write_spotify_map({})
        clear_content_service_caches()

        response = self.client.get(reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"}))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "class=\"asset-link is-spotify\"")
        self.assertNotContains(response, "https://open.spotify.com/episode/")
        self.assertNotContains(response, "https://example.test/podcast/w01l1-alle-kilder.mp3")
        self.assertNotContains(response, "https://example.test/podcast/w01l1-intro.mp3")

    def test_subject_detail_hides_enrollment_badge_for_enrolled_user(self) -> None:
        user = self._create_user()
        SubjectEnrollment.objects.create(user=user, subject_slug="personlighedspsykologi")
        self.client.force_login(user)

        detail_url = reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Tilmeldt")
        self.assertNotContains(response, "Ikke tilmeldt")
        self.assertContains(response, "Udvid alle")
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
        self.assertContains(response, "Udvid alle")
        self.assertContains(response, "Ingen quiz")

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
        self.assertNotContains(response, "Reading-nøglen kunne ikke indlæses.")
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
        self.assertContains(response, "Reading-nøglen kunne ikke indlæses.")
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
