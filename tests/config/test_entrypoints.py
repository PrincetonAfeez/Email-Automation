""" Test entrypoints for EmailAuto."""

from __future__ import annotations

from emailauto.config.asgi import application as asgi_app
from emailauto.config.wsgi import application as wsgi_app
from emailauto.core import apps as core_apps


def test_wsgi_and_asgi_entrypoints():
    assert wsgi_app is not None
    assert asgi_app is not None


def test_core_app_config():
    assert core_apps.CoreConfig.name == "emailauto.core"
