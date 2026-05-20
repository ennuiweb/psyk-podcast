from __future__ import annotations

from unittest.mock import Mock, patch

import requests
from django.contrib.auth.models import User
from django.core import mail
from django.urls import reverse
from django.test import TestCase, override_settings

from quizzes.activity_notifications import notify_new_user_created
from quizzes.announcement_emails import (
    BIONEURO_FLASHCARD_ANNOUNCEMENT_SUBJECT,
    announcement_email_recipient_users,
    make_announcement_unsubscribe_token,
    send_bioneuro_flashcard_announcement_email,
    send_bioneuro_flashcard_announcement_test_email,
)
from quizzes.models import UserNotificationPreference


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@test.freudd.dk",
)
class NewUserNotificationTests(TestCase):
    @override_settings(FREUDD_NEW_USER_NOTIFY_EMAIL="admin@tjekdepot.dk")
    def test_new_users_start_with_activity_notifications_enabled(self) -> None:
        user = User.objects.create_user(
            username="new-user",
            email="new-user@example.com",
            password="Secret123!!",
        )

        preference = UserNotificationPreference.objects.get(user=user)
        self.assertTrue(preference.activity_notifications_enabled)
        self.assertTrue(preference.announcement_emails_enabled)
        self.assertIsNone(preference.announcement_unsubscribed_at)

    @override_settings(
        FREUDD_ACTIVITY_NOTIFY_EMAILS=["legacy-alerts@tjekdepot.dk"],
        FREUDD_NEW_USER_NOTIFY_EMAIL="admin@tjekdepot.dk",
    )
    def test_signup_prefers_new_user_notification_recipient(self) -> None:
        User.objects.create_user(
            username="new-user",
            email="new-user@example.com",
            password="Secret123!!",
        )

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["admin@tjekdepot.dk"])

    @override_settings(
        FREUDD_ACTIVITY_NOTIFY_EMAILS=["legacy-alerts@tjekdepot.dk"],
        FREUDD_NEW_USER_NOTIFY_EMAIL="",
    )
    def test_signup_falls_back_to_legacy_activity_recipient_list(self) -> None:
        User.objects.create_user(
            username="new-user",
            email="new-user@example.com",
            password="Secret123!!",
        )

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["legacy-alerts@tjekdepot.dk"])

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

    @override_settings(FREUDD_NEW_USER_NOTIFY_EMAIL="", FREUDD_ACTIVITY_NOTIFY_EMAILS=[])
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
    def test_disabled_user_preference_blocks_notification_email(self) -> None:
        user = User.objects.create_user(
            username="new-user",
            email="new-user@example.com",
            password="Secret123!!",
        )
        UserNotificationPreference.objects.filter(user=user).update(activity_notifications_enabled=False)
        mail.outbox.clear()

        sent = notify_new_user_created(user=user)

        self.assertFalse(sent)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(FREUDD_NEW_USER_NOTIFY_EMAIL="")
    def test_announcement_unsubscribe_link_disables_only_announcement_emails(self) -> None:
        user = User.objects.create_user(
            username="new-user",
            email="new-user@example.com",
            password="Secret123!!",
        )
        token = make_announcement_unsubscribe_token(user)

        response = self.client.get(reverse("announcement-email-unsubscribe", kwargs={"token": token}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Du er afmeldt")
        preference = UserNotificationPreference.objects.get(user=user)
        self.assertTrue(preference.activity_notifications_enabled)
        self.assertFalse(preference.announcement_emails_enabled)
        self.assertIsNotNone(preference.announcement_unsubscribed_at)

    @override_settings(FREUDD_NEW_USER_NOTIFY_EMAIL="")
    def test_announcement_unsubscribe_link_is_idempotent(self) -> None:
        user = User.objects.create_user(
            username="new-user",
            email="new-user@example.com",
            password="Secret123!!",
        )
        token = make_announcement_unsubscribe_token(user)
        self.client.get(reverse("announcement-email-unsubscribe", kwargs={"token": token}))

        response = self.client.get(reverse("announcement-email-unsubscribe", kwargs={"token": token}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Du er allerede afmeldt")

    @override_settings(FREUDD_NEW_USER_NOTIFY_EMAIL="")
    def test_invalid_announcement_unsubscribe_link_does_not_update_preferences(self) -> None:
        user = User.objects.create_user(
            username="new-user",
            email="new-user@example.com",
            password="Secret123!!",
        )

        response = self.client.get(reverse("announcement-email-unsubscribe", kwargs={"token": "not-a-token"}))

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Linket virker ikke", status_code=400)
        preference = UserNotificationPreference.objects.get(user=user)
        self.assertTrue(preference.announcement_emails_enabled)
        self.assertIsNone(preference.announcement_unsubscribed_at)

    @override_settings(FREUDD_NEW_USER_NOTIFY_EMAIL="")
    def test_announcement_recipient_users_skip_unsubscribed_and_duplicate_emails(self) -> None:
        first = User.objects.create_user(
            username="first",
            email="shared@example.com",
            password="Secret123!!",
        )
        User.objects.create_user(
            username="duplicate",
            email="shared@example.com",
            password="Secret123!!",
        )
        unsubscribed = User.objects.create_user(
            username="unsubscribed",
            email="unsubscribed@example.com",
            password="Secret123!!",
        )
        User.objects.create_user(username="missing-email", email="", password="Secret123!!")
        UserNotificationPreference.objects.filter(user=unsubscribed).update(announcement_emails_enabled=False)

        recipients = list(announcement_email_recipient_users())

        self.assertEqual(recipients, [first])

    @override_settings(FREUDD_NEW_USER_NOTIFY_EMAIL="")
    def test_bioneuro_announcement_email_uses_clickable_html_unsubscribe_link(self) -> None:
        user = User.objects.create_user(
            username="new-user",
            email="new-user@example.com",
            password="Secret123!!",
        )

        sent = send_bioneuro_flashcard_announcement_email(user=user, base_url="https://freudd.dk")

        self.assertTrue(sent)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, BIONEURO_FLASHCARD_ANNOUNCEMENT_SUBJECT)
        self.assertEqual(message.to, ["new-user@example.com"])
        self.assertIn("op her:\n\nhttps://freudd.dk/subjects/bioneuro/cards/", message.body)
        self.assertIn("Afmeld mails:", message.body)
        self.assertIn("https://freudd.dk/email/unsubscribe/", message.body)

        self.assertEqual(len(message.alternatives), 1)
        html_part = message.alternatives[0]
        html_body = getattr(html_part, "content", html_part[0])
        mime_type = getattr(html_part, "mimetype", html_part[1])
        self.assertEqual(mime_type, "text/html")
        self.assertIn("op her:</p>\n<p><a href=", html_body)
        self.assertIn('href="https://freudd.dk/email/unsubscribe/', html_body)
        self.assertIn(">Afmeld mails</a>", html_body)

    @override_settings(FREUDD_NEW_USER_NOTIFY_EMAIL="")
    def test_bioneuro_announcement_test_email_can_target_non_user_address(self) -> None:
        sent = send_bioneuro_flashcard_announcement_test_email(
            recipient_email="OSKARVEDEL@PROTON.ME",
            base_url="https://freudd.dk",
        )

        self.assertTrue(sent)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["oskarvedel@proton.me"])
        self.assertIn("https://freudd.dk/email/unsubscribe/test-preview-link", message.body)

    @override_settings(FREUDD_NEW_USER_NOTIFY_EMAIL="")
    @patch.dict(
        "os.environ",
        {
            "FREUDD_RESEND_API_KEY": "re_test_key",
            "FREUDD_RESEND_API_URL": "https://api.resend.com/emails",
            "FREUDD_RESEND_TIMEOUT_SECONDS": "5",
        },
        clear=False,
    )
    @patch("quizzes.announcement_emails.requests.post")
    def test_bioneuro_announcement_email_uses_resend_api_with_html(self, post_mock: Mock) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        post_mock.return_value = response
        user = User.objects.create_user(
            username="new-user",
            email="new-user@example.com",
            password="Secret123!!",
        )

        sent = send_bioneuro_flashcard_announcement_email(user=user, base_url="https://freudd.dk")

        self.assertTrue(sent)
        post_mock.assert_called_once()
        args, kwargs = post_mock.call_args
        self.assertEqual(args[0], "https://api.resend.com/emails")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer re_test_key")
        self.assertEqual(kwargs["json"]["from"], "noreply@test.freudd.dk")
        self.assertEqual(kwargs["json"]["to"], ["new-user@example.com"])
        self.assertEqual(kwargs["json"]["subject"], BIONEURO_FLASHCARD_ANNOUNCEMENT_SUBJECT)
        self.assertIn("op her:\n\nhttps://freudd.dk/subjects/bioneuro/cards/", kwargs["json"]["text"])
        self.assertIn("op her:</p>\n<p><a href=", kwargs["json"]["html"])
        self.assertIn("https://freudd.dk/email/unsubscribe/", kwargs["json"]["text"])
        self.assertIn('href="https://freudd.dk/email/unsubscribe/', kwargs["json"]["html"])
        self.assertEqual(kwargs["timeout"], 5)
        self.assertEqual(len(mail.outbox), 0)

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
    @patch("quizzes.activity_notifications.requests.post")
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
    @patch("quizzes.activity_notifications.requests.post", side_effect=requests.Timeout("resend timeout"))
    def test_falls_back_to_django_email_when_resend_fails(self, _: Mock) -> None:
        User.objects.create_user(
            username="new-user",
            email="new-user@example.com",
            password="Secret123!!",
        )

        self.assertEqual(len(mail.outbox), 1)
