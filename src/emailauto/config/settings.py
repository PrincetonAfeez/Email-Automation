from __future__ import annotations

import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[3]
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


DEBUG = env_bool("DJANGO_DEBUG", True)

# DEBUG defaults True so the project is zero-config to run and demo. In production
# (DEBUG=false) a real secret is mandatory — never fall back to the known dev key.
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY") or ""
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "unsafe-dev-key-change-me"
    else:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is false.")

ALLOWED_HOSTS = [host.strip() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",") if host.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_celery_beat",
    "emailauto.templates.apps.TemplatesConfig",
    "emailauto.recipients.apps.RecipientsConfig",
    "emailauto.campaigns.apps.CampaignsConfig",
    "emailauto.scheduling.apps.SchedulingConfig",
    "emailauto.outbox.apps.OutboxConfig",
    "emailauto.workers",
    "emailauto.cli.apps.CliConfig",
    "emailauto.web.apps.WebConfig",
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

ROOT_URLCONF = "emailauto.config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "emailauto.config.wsgi.application"
ASGI_APPLICATION = "emailauto.config.asgi.application"

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    DATABASES = {"default": dj_database_url.config(default=DATABASE_URL, conn_max_age=60)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(BASE_DIR / "db.sqlite3"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_TIME_LIMIT = env_int("CELERY_TASK_TIME_LIMIT", 300)
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

REDIS_CACHE_URL = os.getenv("REDIS_CACHE_URL")
if REDIS_CACHE_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_CACHE_URL,
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
            "KEY_PREFIX": "emailauto",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "emailauto-dev",
        }
    }

EMAILAUTO_EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "console").strip().lower()
EMAILAUTO_DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "no-reply@example.com")
EMAILAUTO_MAX_SEND_ATTEMPTS = env_int("MAX_SEND_ATTEMPTS", 3)
EMAILAUTO_SEND_RATE_LIMIT = env_int("SEND_RATE_LIMIT", 60)
EMAILAUTO_CAMPAIGN_RATE_LIMIT = env_int("CAMPAIGN_RATE_LIMIT", 30)
EMAILAUTO_DASHBOARD_CACHE_TTL = env_int("DASHBOARD_CACHE_TTL", 5)
# A row stuck in 'enqueued' longer than this is treated as a lost task and re-published.
EMAILAUTO_ENQUEUED_STALE_SECONDS = env_int("ENQUEUED_STALE_SECONDS", 300)
# A row stuck in 'claimed'/'sending' longer than this is released back to retry_scheduled.
EMAILAUTO_CLAIMED_STALE_SECONDS = env_int("CLAIMED_STALE_SECONDS", 600)
EMAILAUTO_OPERATOR_RATE_LIMIT = env_int("OPERATOR_RATE_LIMIT", 30)

# Operator web surfaces require a logged-in (active) user — not necessarily Django staff.
LOGIN_URL = "emailauto:login"
LOGIN_REDIRECT_URL = "emailauto:dashboard"
LOGOUT_REDIRECT_URL = "emailauto:login"

# Production hardening, active only when DEBUG is off (dev/test/demo stay unchanged).
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 0)
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = env_int("SMTP_PORT", 587)
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_USE_TLS = env_bool("SMTP_USE_TLS", True)
SMTP_USE_SSL = env_bool("SMTP_USE_SSL", False)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "structured"}},
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        # Lifecycle/worker trace logs (event=... outbox_id=... ...).
        "emailauto": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}
