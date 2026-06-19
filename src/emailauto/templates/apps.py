from __future__ import annotations

from django.apps import AppConfig


class TemplatesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    label = "email_templates"
    name = "emailauto.templates"

