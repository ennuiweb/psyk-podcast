from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from .models import UserNotificationPreference


ANNOUNCEMENT_UNSUBSCRIBE_SALT = "freudd.announcement-emails.unsubscribe"
BIONEURO_FLASHCARD_ANNOUNCEMENT_SUBJECT = "Flashcards til bioneuro"
BIONEURO_FLASHCARD_URL = "https://freudd.dk/subjects/bioneuro/cards/biologisk-psykologi-og-neuropsykologi"
BIONEURO_FLASHCARD_ANNOUNCEMENT_BODY = """Hej freudd.dk-bruger

Hurtig servicemeddelelse: Der er lagt over 600 flashcards op til bioneuro op her:
https://freudd.dk/subjects/bioneuro/cards/biologisk-psykologi-og-neuropsykologi

Man kan øve alle kort på én gang eller vælge et specifikt emne at fokusere på

God læselyst!"""
ANNOUNCEMENT_UNSUBSCRIBE_LINK_TEXT = "Afmeld mails"


@dataclass(frozen=True)
class AnnouncementUnsubscribeResult:
    ok: bool
    already_unsubscribed: bool = False
    user_id: int | None = None


@dataclass(frozen=True)
class AnnouncementEmailContent:
    subject: str
    plain_body: str
    html_body: str
    unsubscribe_url: str


def normalize_email(value: object) -> str:
    return str(value or "").strip().lower()


def announcement_emails_enabled(user: object) -> bool:
    if not bool(getattr(user, "is_active", False)):
        return False
    if not normalize_email(getattr(user, "email", "")):
        return False
    try:
        preference = user.usernotificationpreference
    except UserNotificationPreference.DoesNotExist:
        return True
    return bool(preference.announcement_emails_enabled)


def announcement_email_recipient_users():
    user_model = get_user_model()
    seen_emails: set[str] = set()
    users = (
        user_model.objects.filter(is_active=True)
        .exclude(email="")
        .select_related("usernotificationpreference")
        .order_by("email", "id")
    )
    for user in users:
        email = normalize_email(user.email)
        if not email or email in seen_emails:
            continue
        if not announcement_emails_enabled(user):
            continue
        seen_emails.add(email)
        yield user


def make_announcement_unsubscribe_token(user: object) -> str:
    return signing.dumps(
        {
            "uid": int(getattr(user, "pk")),
            "email": normalize_email(getattr(user, "email", "")),
        },
        salt=ANNOUNCEMENT_UNSUBSCRIBE_SALT,
    )


def announcement_unsubscribe_path(user: object) -> str:
    return reverse(
        "announcement-email-unsubscribe",
        kwargs={"token": make_announcement_unsubscribe_token(user)},
    )


def announcement_unsubscribe_url(*, user: object, base_url: str) -> str:
    return urljoin(f"{str(base_url).rstrip('/')}/", announcement_unsubscribe_path(user).lstrip("/"))


def test_announcement_unsubscribe_url(*, base_url: str) -> str:
    return urljoin(f"{str(base_url).rstrip('/')}/", "email/unsubscribe/test-preview-link")


def bioneuro_flashcard_announcement_content_for_unsubscribe_url(*, unsubscribe_url: str) -> AnnouncementEmailContent:
    plain_body = (
        f"{BIONEURO_FLASHCARD_ANNOUNCEMENT_BODY}\n\n"
        f"{ANNOUNCEMENT_UNSUBSCRIBE_LINK_TEXT}:\n{unsubscribe_url}"
    )
    html_body = "\n".join(
        [
            "<p>Hej freudd.dk-bruger</p>",
            (
                "<p>Hurtig servicemeddelelse: Der er lagt over 600 flashcards op til bioneuro op her:<br>"
                f'<a href="{escape(BIONEURO_FLASHCARD_URL)}">{escape(BIONEURO_FLASHCARD_URL)}</a></p>'
            ),
            "<p>Man kan øve alle kort på én gang eller vælge et specifikt emne at fokusere på</p>",
            "<p>God læselyst!</p>",
            (
                "<p>"
                f'<a href="{escape(unsubscribe_url)}">{escape(ANNOUNCEMENT_UNSUBSCRIBE_LINK_TEXT)}</a>'
                "</p>"
            ),
        ]
    )
    return AnnouncementEmailContent(
        subject=BIONEURO_FLASHCARD_ANNOUNCEMENT_SUBJECT,
        plain_body=plain_body,
        html_body=html_body,
        unsubscribe_url=unsubscribe_url,
    )


def bioneuro_flashcard_announcement_content(*, user: object, base_url: str) -> AnnouncementEmailContent:
    return bioneuro_flashcard_announcement_content_for_unsubscribe_url(
        unsubscribe_url=announcement_unsubscribe_url(user=user, base_url=base_url)
    )


def _send_announcement_content(
    *,
    content: AnnouncementEmailContent,
    recipient_email: str,
    fail_silently: bool,
) -> bool:
    message = EmailMultiAlternatives(
        subject=content.subject,
        body=content.plain_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient_email],
    )
    message.attach_alternative(content.html_body, "text/html")
    return bool(message.send(fail_silently=fail_silently))


def send_bioneuro_flashcard_announcement_email(
    *,
    user: object,
    base_url: str,
    fail_silently: bool = False,
) -> bool:
    if not announcement_emails_enabled(user):
        return False

    recipient_email = normalize_email(getattr(user, "email", ""))
    if not recipient_email:
        return False

    content = bioneuro_flashcard_announcement_content(user=user, base_url=base_url)
    return _send_announcement_content(
        content=content,
        recipient_email=recipient_email,
        fail_silently=fail_silently,
    )


def send_bioneuro_flashcard_announcement_test_email(
    *,
    recipient_email: str,
    base_url: str,
    fail_silently: bool = False,
) -> bool:
    normalized_email = normalize_email(recipient_email)
    if not normalized_email:
        return False
    content = bioneuro_flashcard_announcement_content_for_unsubscribe_url(
        unsubscribe_url=test_announcement_unsubscribe_url(base_url=base_url)
    )
    return _send_announcement_content(
        content=content,
        recipient_email=normalized_email,
        fail_silently=fail_silently,
    )


def unsubscribe_announcement_token(token: str) -> AnnouncementUnsubscribeResult:
    try:
        payload = signing.loads(str(token or ""), salt=ANNOUNCEMENT_UNSUBSCRIBE_SALT)
        user_id = int(payload.get("uid"))
        signed_email = normalize_email(payload.get("email"))
    except (signing.BadSignature, TypeError, ValueError, AttributeError):
        return AnnouncementUnsubscribeResult(ok=False)

    if not signed_email:
        return AnnouncementUnsubscribeResult(ok=False)

    user_model = get_user_model()
    user = user_model.objects.filter(pk=user_id, is_active=True).first()
    if user is None or normalize_email(user.email) != signed_email:
        return AnnouncementUnsubscribeResult(ok=False)

    preference, _ = UserNotificationPreference.objects.get_or_create(user=user)
    already_unsubscribed = not preference.announcement_emails_enabled
    preference.announcement_emails_enabled = False
    if preference.announcement_unsubscribed_at is None:
        preference.announcement_unsubscribed_at = timezone.now()
    preference.save(
        update_fields=[
            "announcement_emails_enabled",
            "announcement_unsubscribed_at",
            "updated_at",
        ]
    )
    return AnnouncementUnsubscribeResult(
        ok=True,
        already_unsubscribed=already_unsubscribed,
        user_id=user.id,
    )
