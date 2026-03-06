from django.apps import AppConfig


class QuizzesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "quizzes"

    def ready(self) -> None:
        from . import signals  # noqa: F401
