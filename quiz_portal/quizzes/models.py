"""Data model for user quiz progress."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class QuizProgress(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    quiz_id = models.CharField(max_length=8)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.IN_PROGRESS)
    state_json = models.JSONField(default=dict)
    raw_state_payload = models.TextField(blank=True, null=True)
    answers_count = models.PositiveIntegerField(default=0)
    question_count = models.PositiveIntegerField(default=0)
    last_view = models.CharField(max_length=32, default="question")
    first_seen_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "quiz_id"], name="uq_user_quiz_progress"),
        ]
        indexes = [
            models.Index(fields=["user", "status"], name="quiz_prog_user_status_idx"),
            models.Index(fields=["quiz_id"], name="quiz_prog_quiz_id_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.quiz_id}:{self.status}"
