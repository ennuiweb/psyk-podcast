from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .activity_notifications import notify_new_user_created

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

    notify_new_user_created(user=instance)
