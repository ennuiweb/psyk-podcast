from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

from django.contrib.auth import get_user_model
from django.core import signing
from django.urls import reverse
from django.utils import timezone

from .models import UserNotificationPreference


ANNOUNCEMENT_UNSUBSCRIBE_SALT = "freudd.announcement-emails.unsubscribe"


@dataclass(frozen=True)
class AnnouncementUnsubscribeResult:
    ok: bool
    already_unsubscribed: bool = False
    user_id: int | None = None


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
