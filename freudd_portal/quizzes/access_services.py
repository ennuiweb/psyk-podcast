from __future__ import annotations

from django.contrib.auth.models import Group

ELEVATED_READING_ACCESS_GROUP_NAME = "elevated-reading-access"
_ELEVATED_READING_ACCESS_CACHE_ATTR = "_freudd_elevated_reading_access"


def _user_authenticated(user: object | None) -> bool:
    return bool(user is not None and getattr(user, "is_authenticated", False))


def user_has_elevated_reading_access(user: object | None) -> bool:
    if not _user_authenticated(user):
        return False
    if bool(getattr(user, "is_superuser", False) or getattr(user, "is_staff", False)):
        return True

    cached = getattr(user, _ELEVATED_READING_ACCESS_CACHE_ATTR, None)
    if isinstance(cached, bool):
        return cached

    groups = getattr(user, "groups", None)
    has_access = bool(groups is not None and groups.filter(name=ELEVATED_READING_ACCESS_GROUP_NAME).exists())
    setattr(user, _ELEVATED_READING_ACCESS_CACHE_ATTR, has_access)
    return has_access


def user_has_elevated_slide_access(user: object | None) -> bool:
    # Slide downloads reuse the same elevated access model as reading downloads.
    return user_has_elevated_reading_access(user)


def set_user_elevated_reading_access(*, user: object, enabled: bool) -> bool:
    group, _ = Group.objects.get_or_create(name=ELEVATED_READING_ACCESS_GROUP_NAME)
    if enabled:
        user.groups.add(group)
    else:
        user.groups.remove(group)
    setattr(user, _ELEVATED_READING_ACCESS_CACHE_ATTR, bool(enabled))
    return user_has_elevated_reading_access(user)
