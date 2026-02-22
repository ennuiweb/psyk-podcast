from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from quizzes.gamification_services import create_extension_token, revoke_extension_tokens


class Command(BaseCommand):
    help = "Rotate or revoke per-user extension API tokens."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--user", required=True, help="Username to target.")
        parser.add_argument("--by", default="system", help="Operator identity for token audit.")
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--rotate", action="store_true", help="Create new token and revoke old ones.")
        mode.add_argument("--revoke", action="store_true", help="Revoke all active tokens.")

    def handle(self, *args, **options):
        username = str(options["user"]).strip()
        actor = str(options.get("by") or "system").strip() or "system"

        user_model = get_user_model()
        user = user_model.objects.filter(username=username).first()
        if user is None:
            raise CommandError(f"Unknown user: {username}")

        if options.get("rotate"):
            token = create_extension_token(user=user, created_by=actor)
            self.stdout.write(
                self.style.SUCCESS(f"New token issued for {user.username}. Store it now; it cannot be recovered.")
            )
            self.stdout.write(token)
            return

        revoked_count = revoke_extension_tokens(user=user)
        self.stdout.write(
            self.style.SUCCESS(f"Revoked {revoked_count} active token(s) for user {user.username}.")
        )
