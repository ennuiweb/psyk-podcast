from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db.models.signals import post_save
from django.dispatch import receiver

User = get_user_model()


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
    send_mail(
        subject="Freudd: New user created",
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[notify_email],
        fail_silently=True,
    )
