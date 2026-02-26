"""Settings for freudd auth and quiz progress."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _as_bool_env(name: str, *, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _as_csv_env(name: str, *, default: str = "") -> list[str]:
    value = os.environ.get(name, default)
    return [part.strip() for part in value.split(",") if part.strip()]


# QUIZ_PORTAL_* fallback is temporary for rollout compatibility.
SECRET_KEY = os.environ.get("FREUDD_PORTAL_SECRET_KEY") or os.environ.get(
    "QUIZ_PORTAL_SECRET_KEY",
    "dev-insecure-secret-change-me",
)

DEBUG = (
    os.environ.get("FREUDD_PORTAL_DEBUG")
    or os.environ.get("QUIZ_PORTAL_DEBUG", "false")
).lower() in {"1", "true", "yes", "on"}

allowed_hosts = os.environ.get("FREUDD_PORTAL_ALLOWED_HOSTS") or os.environ.get(
    "QUIZ_PORTAL_ALLOWED_HOSTS",
    "",
)
ALLOWED_HOSTS = [host.strip() for host in allowed_hosts.split(",") if host.strip()] or [
    "127.0.0.1",
    "localhost",
]
CSRF_TRUSTED_ORIGINS = _as_csv_env("FREUDD_PORTAL_CSRF_TRUSTED_ORIGINS")
SESSION_COOKIE_SECURE = _as_bool_env("FREUDD_PORTAL_SESSION_COOKIE_SECURE", default="0")
CSRF_COOKIE_SECURE = _as_bool_env("FREUDD_PORTAL_CSRF_COOKIE_SECURE", default="0")

if _as_bool_env("FREUDD_PORTAL_TRUST_X_FORWARDED_PROTO", default="0"):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "quizzes",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "freudd_portal.urls"

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
                "quizzes.context_processors.design_system_context",
            ],
        },
    },
]

WSGI_APPLICATION = "freudd_portal.wsgi.application"
ASGI_APPLICATION = "freudd_portal.asgi.application"

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
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SITE_ID = int(os.environ.get("FREUDD_PORTAL_SITE_ID", "1"))

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

LOGIN_URL = "/accounts/login"
LOGIN_REDIRECT_URL = "/progress"
LOGOUT_REDIRECT_URL = "/accounts/login"

SOCIALACCOUNT_LOGIN_ON_GET = False
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION = False
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = False

FREUDD_AUTH_GOOGLE_ENABLED = _as_bool_env("FREUDD_AUTH_GOOGLE_ENABLED", default="0")
FREUDD_GOOGLE_CLIENT_ID = os.environ.get("FREUDD_GOOGLE_CLIENT_ID", "").strip()
FREUDD_GOOGLE_CLIENT_SECRET = os.environ.get("FREUDD_GOOGLE_CLIENT_SECRET", "").strip()
SOCIALACCOUNT_PROVIDERS: dict[str, dict[str, object]] = {}

if FREUDD_AUTH_GOOGLE_ENABLED:
    if not FREUDD_GOOGLE_CLIENT_ID or not FREUDD_GOOGLE_CLIENT_SECRET:
        raise RuntimeError(
            "Google auth is enabled but FREUDD_GOOGLE_CLIENT_ID/FREUDD_GOOGLE_CLIENT_SECRET is missing."
        )
    SOCIALACCOUNT_PROVIDERS["google"] = {
        "APP": {
            "client_id": FREUDD_GOOGLE_CLIENT_ID,
            "secret": FREUDD_GOOGLE_CLIENT_SECRET,
            "key": "",
        },
        "SCOPE": ["profile", "email"],
    }

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

FREUDD_SUBJECTS_JSON_PATH = Path(
    os.environ.get(
        "FREUDD_SUBJECTS_JSON_PATH",
        BASE_DIR / "subjects.json",
    )
)
FREUDD_READING_MASTER_KEY_PATH = Path(
    os.environ.get(
        "FREUDD_READING_MASTER_KEY_PATH",
        "/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/"
        "Mine dokumenter \U0001F4BE/psykologi/Personlighedspsykologi/.ai/reading-file-key.md",
    )
)
FREUDD_READING_MASTER_KEY_FALLBACK_PATH = Path(
    os.environ.get(
        "FREUDD_READING_MASTER_KEY_FALLBACK_PATH",
        BASE_DIR.parent / "shows" / "personlighedspsykologi-en" / "docs" / "reading-file-key.md",
    )
)
FREUDD_SUBJECT_FEED_RSS_PATH = Path(
    os.environ.get(
        "FREUDD_SUBJECT_FEED_RSS_PATH",
        BASE_DIR.parent / "shows" / "personlighedspsykologi-en" / "feeds" / "rss.xml",
    )
)
FREUDD_SUBJECT_SPOTIFY_MAP_PATH = Path(
    os.environ.get(
        "FREUDD_SUBJECT_SPOTIFY_MAP_PATH",
        BASE_DIR.parent / "shows" / "personlighedspsykologi-en" / "spotify_map.json",
    )
)
FREUDD_SUBJECT_CONTENT_MANIFEST_PATH = Path(
    os.environ.get(
        "FREUDD_SUBJECT_CONTENT_MANIFEST_PATH",
        BASE_DIR.parent / "shows" / "personlighedspsykologi-en" / "content_manifest.json",
    )
)
FREUDD_READING_FILES_ROOT = Path(
    os.environ.get(
        "FREUDD_READING_FILES_ROOT",
        "/var/www/readings/personlighedspsykologi",
    )
)
FREUDD_READING_DOWNLOAD_EXCLUSIONS_PATH = Path(
    os.environ.get(
        "FREUDD_READING_DOWNLOAD_EXCLUSIONS_PATH",
        BASE_DIR.parent / "shows" / "personlighedspsykologi-en" / "reading_download_exclusions.json",
    )
)

QUIZ_SIGNUP_RATE_LIMIT = int(os.environ.get("QUIZ_SIGNUP_RATE_LIMIT", "20"))
QUIZ_LOGIN_RATE_LIMIT = int(os.environ.get("QUIZ_LOGIN_RATE_LIMIT", "40"))
QUIZ_RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("QUIZ_RATE_LIMIT_WINDOW_SECONDS", "3600"))
FREUDD_QUIZ_QUESTION_TIME_LIMIT_SECONDS = int(
    os.environ.get("FREUDD_QUIZ_QUESTION_TIME_LIMIT_SECONDS", "30")
)
FREUDD_QUIZ_RETRY_COOLDOWN_RESET_SECONDS = int(
    os.environ.get("FREUDD_QUIZ_RETRY_COOLDOWN_RESET_SECONDS", "3600")
)

FREUDD_GAMIFICATION_DAILY_GOAL = int(os.environ.get("FREUDD_GAMIFICATION_DAILY_GOAL", "20"))
FREUDD_GAMIFICATION_XP_PER_ANSWER = int(os.environ.get("FREUDD_GAMIFICATION_XP_PER_ANSWER", "5"))
FREUDD_GAMIFICATION_XP_PER_COMPLETION = int(
    os.environ.get("FREUDD_GAMIFICATION_XP_PER_COMPLETION", "50")
)
FREUDD_GAMIFICATION_XP_PER_LEVEL = int(os.environ.get("FREUDD_GAMIFICATION_XP_PER_LEVEL", "500"))
FREUDD_CREDENTIALS_MASTER_KEY = os.environ.get("FREUDD_CREDENTIALS_MASTER_KEY", "")
FREUDD_CREDENTIALS_KEY_VERSION = int(os.environ.get("FREUDD_CREDENTIALS_KEY_VERSION", "1"))
FREUDD_EXT_SYNC_TIMEOUT_SECONDS = int(os.environ.get("FREUDD_EXT_SYNC_TIMEOUT_SECONDS", "20"))

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "freudd-portal-cache",
    }
}

FREUDD_DESIGN_SYSTEM_DEFAULT = os.environ.get("FREUDD_DESIGN_SYSTEM_DEFAULT", "paper-studio")
FREUDD_DESIGN_SYSTEM_COOKIE_NAME = os.environ.get(
    "FREUDD_DESIGN_SYSTEM_COOKIE_NAME",
    "freudd_design_system",
)
FREUDD_SUBJECT_DETAIL_SHOW_READING_QUIZZES = (
    os.environ.get("FREUDD_SUBJECT_DETAIL_SHOW_READING_QUIZZES", "0").strip().lower()
    in {"1", "true", "yes", "on"}
)
