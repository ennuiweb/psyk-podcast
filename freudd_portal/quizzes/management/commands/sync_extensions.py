from __future__ import annotations

import json
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from quizzes.gamification_services import sync_extensions_batch


class Command(BaseCommand):
    help = "Run server-side extension sync for enabled users."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--extension",
            default="all",
            choices=["habitica", "all"],
            help="Extension to sync (default: all).",
        )
        parser.add_argument("--user", help="Only sync one username.")
        parser.add_argument("--date", help="Sync date as YYYY-MM-DD (default: today).")
        parser.add_argument("--dry-run", action="store_true", help="Compute outcome without DB writes.")

    def handle(self, *args, **options):
        date_value = str(options.get("date") or "").strip()
        sync_date: date | None = None
        if date_value:
            try:
                sync_date = date.fromisoformat(date_value)
            except ValueError as exc:
                raise CommandError("--date must be YYYY-MM-DD") from exc

        summary = sync_extensions_batch(
            extension=str(options.get("extension") or "all").strip().lower(),
            username=str(options.get("user") or "").strip() or None,
            sync_date=sync_date,
            dry_run=bool(options.get("dry_run")),
        )
        self.stdout.write(json.dumps(summary, ensure_ascii=False))
        if int(summary.get("error", 0)) > 0:
            raise CommandError("One or more extension sync operations failed.")
