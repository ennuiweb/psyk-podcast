from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from quizzes.access_services import (
    ELEVATED_READING_ACCESS_GROUP_NAME,
    set_user_elevated_reading_access,
    user_has_elevated_reading_access,
)


class Command(BaseCommand):
    help = "Grant or revoke per-user elevated reading download access."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--user", required=True, help="Username to target.")
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--enable", action="store_true", help="Enable elevated reading access for user.")
        mode.add_argument("--disable", action="store_true", help="Disable elevated reading access for user.")
        mode.add_argument("--show", action="store_true", help="Show current access state for user.")

    def handle(self, *args, **options):
        username = str(options["user"]).strip()
        user_model = get_user_model()
        user = user_model.objects.filter(username=username).first()
        if user is None:
            raise CommandError(f"Unknown user: {username}")

        if options.get("enable"):
            set_user_elevated_reading_access(user=user, enabled=True)
            action = "enabled"
        elif options.get("disable"):
            set_user_elevated_reading_access(user=user, enabled=False)
            action = "disabled"
        else:
            action = "show"

        payload = {
            "action": action,
            "user": user.username,
            "group": ELEVATED_READING_ACCESS_GROUP_NAME,
            "is_staff": bool(user.is_staff),
            "is_superuser": bool(user.is_superuser),
            "effective_access": user_has_elevated_reading_access(user),
            "group_access": bool(user.groups.filter(name=ELEVATED_READING_ACCESS_GROUP_NAME).exists()),
        }
        self.stdout.write(json.dumps(payload, ensure_ascii=False))
