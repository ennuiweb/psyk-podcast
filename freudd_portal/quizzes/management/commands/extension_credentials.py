from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from quizzes.gamification_services import (
    ExtensionCredentialError,
    clear_extension_credential,
    extension_credential_meta,
    rotate_extension_credential_key,
    set_extension_credential,
)


class Command(BaseCommand):
    help = "Manage per-user encrypted extension credentials."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--user", required=True, help="Username to target.")
        parser.add_argument(
            "--extension",
            required=True,
            choices=["habitica", "anki"],
            help="Extension identifier.",
        )
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--set", action="store_true", help="Create or update credentials.")
        mode.add_argument("--show-meta", action="store_true", help="Show credential metadata without secrets.")
        mode.add_argument("--clear", action="store_true", help="Delete stored credentials.")
        mode.add_argument(
            "--rotate-key-version",
            action="store_true",
            help="Decrypt and re-encrypt with active key version.",
        )
        parser.add_argument("--habitica-user-id", help="Habitica API user id.")
        parser.add_argument("--habitica-api-token", help="Habitica API token.")
        parser.add_argument("--habitica-task-id", help="Habitica daily task id.")

    def handle(self, *args, **options):
        username = str(options["user"]).strip()
        extension = str(options["extension"]).strip().lower()

        user_model = get_user_model()
        user = user_model.objects.filter(username=username).first()
        if user is None:
            raise CommandError(f"Unknown user: {username}")

        if options.get("set"):
            if extension != "habitica":
                raise CommandError("Only --extension habitica supports --set in this phase.")
            payload = {
                "habitica_user_id": str(options.get("habitica_user_id") or "").strip(),
                "habitica_api_token": str(options.get("habitica_api_token") or "").strip(),
                "habitica_task_id": str(options.get("habitica_task_id") or "").strip(),
            }
            if not all(payload.values()):
                raise CommandError(
                    "--set requires --habitica-user-id, --habitica-api-token, and --habitica-task-id"
                )
            try:
                row = set_extension_credential(user=user, extension=extension, payload=payload)
            except ExtensionCredentialError as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(
                json.dumps(
                    {
                        "action": "set",
                        "user": user.username,
                        "extension": extension,
                        "key_version": row.key_version,
                        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                    },
                    ensure_ascii=False,
                )
            )
            return

        if options.get("show_meta"):
            meta = extension_credential_meta(user=user, extension=extension)
            self.stdout.write(
                json.dumps(
                    {
                        "action": "show_meta",
                        "exists": bool(meta),
                        "meta": meta,
                    },
                    ensure_ascii=False,
                )
            )
            return

        if options.get("clear"):
            deleted_count = clear_extension_credential(user=user, extension=extension)
            self.stdout.write(
                json.dumps(
                    {
                        "action": "clear",
                        "user": user.username,
                        "extension": extension,
                        "deleted_count": int(deleted_count),
                    },
                    ensure_ascii=False,
                )
            )
            return

        try:
            row = rotate_extension_credential_key(user=user, extension=extension)
        except ExtensionCredentialError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            json.dumps(
                {
                    "action": "rotate_key_version",
                    "user": user.username,
                    "extension": extension,
                    "key_version": row.key_version,
                    "rotated_at": row.rotated_at.isoformat() if row.rotated_at else None,
                },
                ensure_ascii=False,
            )
        )
