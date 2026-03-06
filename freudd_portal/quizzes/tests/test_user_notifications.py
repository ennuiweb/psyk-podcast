from __future__ import annotations

from unittest.mock import Mock, patch

import requests
from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@test.freudd.dk",
)
class NewUserNotificationTests(TestCase):
    @override_settings(FREUDD_NEW_USER_NOTIFY_EMAIL="admin@tjekdepot.dk")
    def test_sends_email_when_user_is_created(self) -> None:
        User.objects.create_user(
            username="new-user",
            email="new-user@example.com",
            password="Secret123!!",
        )

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, "Freudd: New user created")
        self.assertEqual(message.from_email, "noreply@test.freudd.dk")
        self.assertEqual(message.to, ["admin@tjekdepot.dk"])
        self.assertIn("username: new-user", message.body)
        self.assertIn("email: new-user@example.com", message.body)

    @override_settings(FREUDD_NEW_USER_NOTIFY_EMAIL="")
    def test_does_not_send_email_when_notify_email_not_set(self) -> None:
        User.objects.create_user(
            username="new-user",
            email="new-user@example.com",
            password="Secret123!!",
        )

        self.assertEqual(len(mail.outbox), 0)

    @override_settings(FREUDD_NEW_USER_NOTIFY_EMAIL="admin@tjekdepot.dk")
    def test_does_not_send_email_when_user_is_updated(self) -> None:
        user = User.objects.create_user(
            username="new-user",
            email="new-user@example.com",
            password="Secret123!!",
        )
        self.assertEqual(len(mail.outbox), 1)

        user.email = "updated@example.com"
        user.save(update_fields=["email"])

        self.assertEqual(len(mail.outbox), 1)

    @override_settings(FREUDD_NEW_USER_NOTIFY_EMAIL="admin@tjekdepot.dk")
    @patch.dict(
        "os.environ",
        {
            "FREUDD_RESEND_API_KEY": "re_test_key",
            "FREUDD_RESEND_API_URL": "https://api.resend.com/emails",
            "FREUDD_RESEND_TIMEOUT_SECONDS": "5",
        },
        clear=False,
    )
    @patch("quizzes.signals.requests.post")
    def test_uses_resend_when_api_key_is_present(self, post_mock: Mock) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        post_mock.return_value = response

        User.objects.create_user(
            username="new-user",
            email="new-user@example.com",
            password="Secret123!!",
        )

        post_mock.assert_called_once()
        args, kwargs = post_mock.call_args
        self.assertEqual(args[0], "https://api.resend.com/emails")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer re_test_key")
        self.assertEqual(kwargs["json"]["to"], ["admin@tjekdepot.dk"])
        self.assertEqual(kwargs["json"]["from"], "noreply@test.freudd.dk")
        self.assertEqual(kwargs["json"]["subject"], "Freudd: New user created")
        self.assertEqual(kwargs["timeout"], 5)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(FREUDD_NEW_USER_NOTIFY_EMAIL="admin@tjekdepot.dk")
    @patch.dict(
        "os.environ",
        {
            "FREUDD_RESEND_API_KEY": "re_test_key",
            "FREUDD_RESEND_API_URL": "https://api.resend.com/emails",
        },
        clear=False,
    )
    @patch("quizzes.signals.requests.post", side_effect=requests.Timeout("resend timeout"))
    def test_falls_back_to_django_email_when_resend_fails(self, _: Mock) -> None:
        User.objects.create_user(
            username="new-user",
            email="new-user@example.com",
            password="Secret123!!",
        )

        self.assertEqual(len(mail.outbox), 1)
