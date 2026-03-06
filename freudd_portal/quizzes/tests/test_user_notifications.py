from __future__ import annotations

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
