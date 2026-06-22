""" Workers app for EmailAuto."""

from __future__ import annotations

from django.apps import AppConfig


class WorkersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "emailauto.workers"
    label = "workers"
