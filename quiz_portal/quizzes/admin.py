from django.contrib import admin

from .models import QuizProgress


@admin.register(QuizProgress)
class QuizProgressAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "quiz_id",
        "status",
        "answers_count",
        "question_count",
        "last_view",
        "updated_at",
    )
    search_fields = ("quiz_id", "user__username", "user__email")
    list_filter = ("status", "updated_at")
