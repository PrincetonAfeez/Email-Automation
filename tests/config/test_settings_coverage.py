""" Test settings coverage for EmailAuto."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys

import pytest


@pytest.fixture(autouse=True)
def isolate_settings_env(monkeypatch):
    monkeypatch.setenv("DJANGO_DEBUG", "true")
    monkeypatch.setenv("DJANGO_SECRET_KEY", "test-secret")
    monkeypatch.delenv("REDIS_CACHE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *_args, **_kwargs: None)
    yield
    importlib.reload(importlib.import_module("emailauto.config.settings"))


def test_env_bool_and_env_int_helpers():
    from emailauto.config.settings import env_bool

    assert env_bool("MISSING_VAR", default=True) is True
    assert env_bool("MISSING_VAR", default=False) is False


def test_env_int_invalid_returns_default(monkeypatch):
    monkeypatch.setenv("BAD_INT", "not-a-number")
    from emailauto.config.settings import env_int

    assert env_int("BAD_INT", 42) == 42


def test_env_bool_truthy_values(monkeypatch):
    from emailauto.config.settings import env_bool

    monkeypatch.setenv("FLAG", "yes")
    assert env_bool("FLAG") is True
    monkeypatch.setenv("FLAG", "off")
    assert env_bool("FLAG") is False


def test_database_url_config(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    settings = importlib.reload(importlib.import_module("emailauto.config.settings"))
    assert "default" in settings.DATABASES


def test_redis_cache_config(monkeypatch):
    monkeypatch.setenv("REDIS_CACHE_URL", "redis://localhost:6379/2")
    settings = importlib.reload(importlib.import_module("emailauto.config.settings"))
    assert "RedisCache" in settings.CACHES["default"]["BACKEND"]


def test_production_requires_secret_key():
    env = os.environ.copy()
    env["DJANGO_DEBUG"] = "false"
    env.pop("DJANGO_SECRET_KEY", None)
    env.pop("REDIS_CACHE_URL", None)
    code = (
        "import importlib; "
        "import emailauto.config.settings as s; "
        "importlib.reload(s)"
    )
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, cwd=os.getcwd())
    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY" in result.stderr


def test_production_requires_redis_cache():
    env = os.environ.copy()
    env["DJANGO_DEBUG"] = "false"
    env["DJANGO_SECRET_KEY"] = "prod-secret"
    env.pop("REDIS_CACHE_URL", None)
    code = (
        "import importlib; "
        "import emailauto.config.settings as s; "
        "importlib.reload(s)"
    )
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, cwd=os.getcwd())
    assert result.returncode != 0
    assert "REDIS_CACHE_URL" in result.stderr


def test_production_settings_improperly_configured_in_process(monkeypatch):
    import importlib

    from django.core.exceptions import ImproperlyConfigured

    monkeypatch.setenv("DJANGO_DEBUG", "false")
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *_a, **_k: None)
    with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
        importlib.reload(importlib.import_module("emailauto.config.settings"))

    monkeypatch.setenv("DJANGO_SECRET_KEY", "prod")
    monkeypatch.delenv("REDIS_CACHE_URL", raising=False)
    with pytest.raises(ImproperlyConfigured, match="REDIS_CACHE_URL"):
        importlib.reload(importlib.import_module("emailauto.config.settings"))
    monkeypatch.setenv("DJANGO_DEBUG", "false")
    monkeypatch.setenv("DJANGO_SECRET_KEY", "prod-secret")
    monkeypatch.setenv("REDIS_CACHE_URL", "redis://localhost:6379/2")
    monkeypatch.setenv("SECURE_HSTS_SECONDS", "3600")
    monkeypatch.setenv("SECURE_SSL_REDIRECT", "true")
    settings = importlib.reload(importlib.import_module("emailauto.config.settings"))
    assert settings.SESSION_COOKIE_SECURE is True
    assert settings.SECURE_HSTS_SECONDS == 3600
    assert settings.SECURE_SSL_REDIRECT is True
    assert settings.DEBUG is False
