from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from quizzes.gamification_services import set_extension_access


class Command(BaseCommand):
    help = "Enable or disable optional extensions for a specific user."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--user", required=True, help="Username to target.")
        parser.add_argument(
            "--extension",
            required=True,
            choices=["habitica", "anki"],
            help="Extension identifier.",
        )
        parser.add_argument("--by", default="system", help="Operator identity for audit fields.")
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--enable", action="store_true", help="Enable extension for user.")
        mode.add_argument("--disable", action="store_true", help="Disable extension for user.")

    def handle(self, *args, **options):
        username = str(options["user"]).strip()
        extension = str(options["extension"]).strip().lower()
        enabled = bool(options.get("enable"))
        actor = str(options.get("by") or "system").strip() or "system"

        user_model = get_user_model()
        user = user_model.objects.filter(username=username).first()
        if user is None:
            raise CommandError(f"Unknown user: {username}")

        access = set_extension_access(user=user, extension=extension, enabled=enabled, enabled_by=actor)
        state = "enabled" if access.enabled else "disabled"
        self.stdout.write(
            self.style.SUCCESS(
                f"{access.extension} is now {state} for user {user.username}"
            )
        )
