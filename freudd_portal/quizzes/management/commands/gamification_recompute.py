from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from quizzes.gamification_services import recompute_many


class Command(BaseCommand):
    help = "Recompute gamification profile + unit progression from current quiz data."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--all", action="store_true", help="Recompute for all users.")
        parser.add_argument(
            "--user",
            action="append",
            default=[],
            help="Username to recompute. Can be provided multiple times.",
        )

    def handle(self, *args, **options):
        usernames = [str(item).strip() for item in options.get("user") or [] if str(item).strip()]
        if not options.get("all") and not usernames:
            raise CommandError("Provide --all or at least one --user")

        if options.get("all"):
            processed = recompute_many()
        else:
            processed = recompute_many(usernames=usernames)

        self.stdout.write(self.style.SUCCESS(f"Recomputed gamification for {processed} user(s)."))
