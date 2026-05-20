from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from quizzes.announcement_emails import (
    BIONEURO_FLASHCARD_ANNOUNCEMENT_SUBJECT,
    announcement_email_recipient_users,
    bioneuro_flashcard_announcement_content,
    normalize_email,
    send_bioneuro_flashcard_announcement_email,
)


class Command(BaseCommand):
    help = "Send the bioneuro flashcard announcement email with per-user unsubscribe links."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--send",
            action="store_true",
            help="Actually send the email. Without this flag the command only prints a dry-run summary.",
        )
        parser.add_argument(
            "--base-url",
            default="https://freudd.dk",
            help="Public Freudd base URL used for unsubscribe links.",
        )
        parser.add_argument(
            "--only-email",
            action="append",
            default=[],
            help="Limit the run to a specific normalized recipient email. Can be repeated.",
        )

    def handle(self, *args, **options):
        base_url = str(options.get("base_url") or "").strip()
        if not base_url:
            raise CommandError("--base-url cannot be empty")

        allowed_emails = {
            normalized
            for normalized in (normalize_email(value) for value in options.get("only_email") or [])
            if normalized
        }
        recipients = [
            user
            for user in announcement_email_recipient_users()
            if not allowed_emails or normalize_email(user.email) in allowed_emails
        ]

        sample = None
        if recipients:
            content = bioneuro_flashcard_announcement_content(user=recipients[0], base_url=base_url)
            sample = {
                "to": normalize_email(recipients[0].email),
                "plain_body": content.plain_body,
                "html_body": content.html_body,
            }

        should_send = bool(options.get("send"))
        summary = {
            "dry_run": not should_send,
            "subject": BIONEURO_FLASHCARD_ANNOUNCEMENT_SUBJECT,
            "recipient_count": len(recipients),
            "sent": 0,
            "failed": [],
            "sample": sample,
        }

        if not should_send:
            self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
            return

        for user in recipients:
            email = normalize_email(user.email)
            try:
                if send_bioneuro_flashcard_announcement_email(user=user, base_url=base_url):
                    summary["sent"] += 1
                else:
                    summary["failed"].append({"email": email, "error": "send returned false"})
            except Exception as exc:
                summary["failed"].append({"email": email, "error": str(exc)})

        self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
        if summary["failed"]:
            raise CommandError("One or more announcement emails failed.")
