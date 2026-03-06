from __future__ import annotations

import logging
import os

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db.models.signals import post_save
from django.dispatch import receiver

User = get_user_model()
logger = logging.getLogger(__name__)


def _send_resend_email(*, notify_email: str, body: str) -> bool:
    resend_api_key = os.environ.get("FREUDD_RESEND_API_KEY", "").strip()
    if not resend_api_key:
        return False

    resend_api_url = os.environ.get("FREUDD_RESEND_API_URL", "https://api.resend.com/emails").strip()
    try:
        resend_timeout_seconds = int(os.environ.get("FREUDD_RESEND_TIMEOUT_SECONDS", "10"))
    except ValueError:
        resend_timeout_seconds = 10

    try:
        response = requests.post(
            resend_api_url,
            headers={
                "Authorization": f"Bearer {resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.DEFAULT_FROM_EMAIL,
                "to": [notify_email],
                "subject": "Freudd: New user created",
                "text": body,
            },
            timeout=resend_timeout_seconds,
        )
        response.raise_for_status()
    except requests.RequestException:
        logger.exception("Resend delivery failed for new-user notification.")
        return False
    return True


@receiver(post_save, sender=User)
def notify_admin_on_new_user(
    sender: type[User],
    instance: User,
    created: bool,
    **kwargs: object,
) -> None:
    if not created:
        return

    notify_email = settings.FREUDD_NEW_USER_NOTIFY_EMAIL.strip()
    if not notify_email:
        return

    body = "\n".join(
        [
            "A new Freudd user was created.",
            f"username: {instance.username}",
            f"email: {instance.email or 'no-email'}",
            f"user_id: {instance.id}",
        ]
    )

    if _send_resend_email(notify_email=notify_email, body=body):
        return

    send_mail(
        subject="Freudd: New user created",
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[notify_email],
        fail_silently=True,
    )
