from __future__ import annotations

import html
import json
import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from quizzes.models import QuizProgress


class QuizPortalTests(TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        root = Path(self.temp_dir.name)
        self.quiz_root = root / "quizzes"
        self.quiz_root.mkdir(parents=True, exist_ok=True)
        self.links_file = root / "quiz_links.json"

        self.override = override_settings(
            QUIZ_FILES_ROOT=self.quiz_root,
            QUIZ_LINKS_JSON_PATH=self.links_file,
            QUIZ_SIGNUP_RATE_LIMIT=1000,
            QUIZ_LOGIN_RATE_LIMIT=1000,
        )
        self.override.enable()
        self.addCleanup(self.override.disable)

        self.quiz_id = "29ebcecd"
        self._write_quiz_file(self.quiz_id, question_count=2)
        self._write_links_file(
            {
                self.quiz_id: {
                    "title": "W1L1 - Episode",
                    "difficulty": "medium",
                }
            }
        )

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

    def test_quiz_wrapper_redirects_when_anonymous(self) -> None:
        response = self.client.get(reverse("quiz-wrapper", kwargs={"quiz_id": self.quiz_id}))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(f"{reverse('login')}?next="))

    def test_quiz_raw_requires_auth_and_serves_html(self) -> None:
        self._create_user()
        self._login()

        response = self.client.get(reverse("quiz-raw", kwargs={"quiz_id": self.quiz_id}))
        self.assertEqual(response.status_code, 200)
        content = b"".join(response.streaming_content).decode("utf-8")
        self.assertIn("<app-root", content)

    def test_invalid_quiz_id_is_rejected(self) -> None:
        self._create_user()
        self._login()
        response = self.client.get("/q/nothexid.html")
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
