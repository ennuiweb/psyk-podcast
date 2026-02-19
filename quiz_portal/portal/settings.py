"""Settings for the quiz login/progress portal."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("QUIZ_PORTAL_SECRET_KEY", "dev-insecure-secret-change-me")

DEBUG = os.environ.get("QUIZ_PORTAL_DEBUG", "false").lower() in {"1", "true", "yes", "on"}

allowed_hosts = os.environ.get("QUIZ_PORTAL_ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [host.strip() for host in allowed_hosts.split(",") if host.strip()] or [
    "127.0.0.1",
    "localhost",
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "quizzes",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "portal.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "portal.wsgi.application"
ASGI_APPLICATION = "portal.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "da"
LANGUAGES = [
    ("da", "Dansk"),
]
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/accounts/login"
LOGIN_REDIRECT_URL = "/progress"
LOGOUT_REDIRECT_URL = "/accounts/login"

X_FRAME_OPTIONS = "SAMEORIGIN"

QUIZ_FILES_ROOT = Path(
    os.environ.get(
        "QUIZ_FILES_ROOT",
        "/var/www/quizzes/personlighedspsykologi",
    )
)
QUIZ_LINKS_JSON_PATH = Path(
    os.environ.get(
        "QUIZ_LINKS_JSON_PATH",
        BASE_DIR.parent / "shows" / "personlighedspsykologi-en" / "quiz_links.json",
    )
)

QUIZ_SIGNUP_RATE_LIMIT = int(os.environ.get("QUIZ_SIGNUP_RATE_LIMIT", "20"))
QUIZ_LOGIN_RATE_LIMIT = int(os.environ.get("QUIZ_LOGIN_RATE_LIMIT", "40"))
QUIZ_RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("QUIZ_RATE_LIMIT_WINDOW_SECONDS", "3600"))

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "quiz-portal-cache",
    }
}
