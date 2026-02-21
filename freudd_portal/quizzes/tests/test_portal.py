from __future__ import annotations

import html
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from quizzes.models import QuizProgress, SubjectEnrollment, UserPreference
from quizzes.subject_services import clear_subject_service_caches


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

        self.override = override_settings(
            QUIZ_FILES_ROOT=self.quiz_root,
            QUIZ_LINKS_JSON_PATH=self.links_file,
            FREUDD_SUBJECTS_JSON_PATH=self.subjects_file,
            FREUDD_READING_MASTER_KEY_PATH=self.reading_master_file,
            QUIZ_SIGNUP_RATE_LIMIT=1000,
            QUIZ_LOGIN_RATE_LIMIT=1000,
        )
        self.override.enable()
        self.addCleanup(self.override.disable)
        clear_subject_service_caches()
        self.addCleanup(clear_subject_service_caches)

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
            by_name[title] = {
                "relative_path": f"{quiz_id}.html",
                "difficulty": meta.get("difficulty", "medium"),
                "links": [
                    {
                        "relative_path": f"{quiz_id}.html",
                        "difficulty": meta.get("difficulty", "medium"),
                        "format": "html",
                    }
                ],
            }

        self.links_file.write_text(json.dumps({"by_name": by_name}), encoding="utf-8")

    def _write_subjects_file(self, *, include_subject: bool = True) -> None:
        payload: dict[str, object] = {
            "version": 1,
            "semester_choices": ["F26"],
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

    def test_quiz_wrapper_allows_anonymous_and_shows_login_cta(self) -> None:
        quiz_url = reverse("quiz-wrapper", kwargs={"quiz_id": self.quiz_id})
        response = self.client.get(quiz_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tag quizzen anonymt.")
        self.assertContains(response, f"{reverse('login')}?{urlencode({'next': quiz_url})}")
        self.assertContains(response, f"{reverse('signup')}?{urlencode({'next': quiz_url})}")

    def test_quiz_wrapper_hides_anonymous_notice_for_logged_in_user(self) -> None:
        self._create_user()
        self._login()
        response = self.client.get(reverse("quiz-wrapper", kwargs={"quiz_id": self.quiz_id}))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Tag quizzen anonymt.")

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
        self.assertContains(response, "W1L1 - Episode")
        self.assertContains(response, "Mellem")

    def test_progress_page_shows_semester_and_subject_cards(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        response = self.client.get(reverse("progress"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aktivt semester")
        self.assertContains(response, "F26")
        self.assertContains(response, "Personlighedspsykologi")
        self.assertContains(response, "Tilmeld")

        preference = UserPreference.objects.get(user=user)
        self.assertEqual(preference.semester, "F26")

    def test_semester_update_accepts_valid_and_rejects_invalid_value(self) -> None:
        user = self._create_user()
        self.client.force_login(user)

        update_url = reverse("semester-update")
        response = self.client.post(update_url, {"semester": "F26"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("progress"))

        preference = UserPreference.objects.get(user=user)
        self.assertEqual(preference.semester, "F26")

        response = self.client.post(update_url, {"semester": "INVALID"})
        self.assertEqual(response.status_code, 302)
        preference.refresh_from_db()
        self.assertEqual(preference.semester, "F26")

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
        self.assertContains(response, "Ikke tilmeldt")
        self.assertContains(response, "W01L1 Introforelaesning")
        self.assertContains(response, "Grundbog kapitel 01 - Introduktion til personlighedspsykologi")
        self.assertContains(response, "MISSING")
        self.assertContains(response, "Koutsoumpis (2025)")

    def test_subject_detail_shows_enrolled_status_for_enrolled_user(self) -> None:
        user = self._create_user()
        SubjectEnrollment.objects.create(user=user, subject_slug="personlighedspsykologi")
        self.client.force_login(user)

        detail_url = reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tilmeldt")

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

    def test_subject_detail_handles_missing_master_reading_key(self) -> None:
        user = self._create_user()
        self.client.force_login(user)
        self.reading_master_file.unlink()
        clear_subject_service_caches()

        response = self.client.get(reverse("subject-detail", kwargs={"subject_slug": "personlighedspsykologi"}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reading-nøglen kunne ikke indlæses.")
        self.assertContains(response, "Ingen readings fundet for dette fag.")

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

    def test_subject_and_semester_posts_require_csrf(self) -> None:
        user = self._create_user()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(user)

        response = csrf_client.post(reverse("semester-update"), {"semester": "F26"})
        self.assertEqual(response.status_code, 403)

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

    def test_language_configuration_is_danish_only(self) -> None:
        self.assertEqual(settings.LANGUAGE_CODE, "da")
        self.assertEqual(settings.LANGUAGES, [("da", "Dansk")])
