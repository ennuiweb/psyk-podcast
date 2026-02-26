from django.contrib import admin

from .models import QuizProgress, SubjectEnrollment, UserInterfacePreference


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


@admin.register(SubjectEnrollment)
class SubjectEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "subject_slug", "enrolled_at", "updated_at")
    search_fields = ("user__username", "user__email", "subject_slug")
    list_filter = ("subject_slug", "enrolled_at")


@admin.register(UserInterfacePreference)
class UserInterfacePreferenceAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "design_system", "updated_at")
    search_fields = ("user__username", "user__email", "design_system")
    list_filter = ("design_system", "updated_at")
