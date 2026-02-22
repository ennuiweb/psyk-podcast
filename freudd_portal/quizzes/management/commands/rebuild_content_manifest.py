from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from quizzes.content_services import build_subject_content_manifest, write_subject_content_manifest


class Command(BaseCommand):
    help = "Rebuild lecture-first content manifest for a subject."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--subject", required=True, help="Subject slug to build manifest for.")
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Fail if manifest warnings are present.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Build and print summary without writing manifest file.",
        )

    def handle(self, *args, **options):
        subject_slug = str(options.get("subject") or "").strip().lower()
        if not subject_slug:
            raise CommandError("--subject is required")

        manifest = build_subject_content_manifest(subject_slug)
        warnings = manifest.get("warnings") or []
        if options.get("strict") and warnings:
            raise CommandError(f"Manifest has warnings ({len(warnings)}).")

        if not options.get("dry_run"):
            write_subject_content_manifest(manifest)

        lecture_count = len(manifest.get("lectures") or [])
        reading_count = 0
        quiz_count = 0
        podcast_count = 0
        for lecture in manifest.get("lectures") or []:
            if not isinstance(lecture, dict):
                continue
            lecture_assets = lecture.get("lecture_assets") if isinstance(lecture.get("lecture_assets"), dict) else {}
            quiz_count += len(lecture_assets.get("quizzes") or [])
            podcast_count += len(lecture_assets.get("podcasts") or [])
            for reading in lecture.get("readings") or []:
                if not isinstance(reading, dict):
                    continue
                reading_count += 1
                assets = reading.get("assets") if isinstance(reading.get("assets"), dict) else {}
                quiz_count += len(assets.get("quizzes") or [])
                podcast_count += len(assets.get("podcasts") or [])

        summary = {
            "subject_slug": subject_slug,
            "dry_run": bool(options.get("dry_run")),
            "lectures": lecture_count,
            "readings": reading_count,
            "quiz_assets": quiz_count,
            "podcast_assets": podcast_count,
            "warning_count": len(warnings),
        }
        self.stdout.write(json.dumps(summary, ensure_ascii=False))
