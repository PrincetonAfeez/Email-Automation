""" Models for EmailAuto."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models


class EmailTemplate(models.Model):
    class BodyFormat(models.TextChoices):
        TEXT = "text", "Text"
        HTML = "html", "HTML"

    name = models.CharField(max_length=150, unique=True)
    subject_template = models.TextField()
    body_template = models.TextField()
    body_format = models.CharField(max_length=10, choices=BodyFormat.choices, default=BodyFormat.TEXT)
    required_variables = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        if not isinstance(self.required_variables, list):
            raise ValidationError({"required_variables": "Required variables must be a JSON list."})
        invalid = [item for item in self.required_variables if not isinstance(item, str)]
        if invalid:
            raise ValidationError({"required_variables": "Each required variable must be a string."})

    def save(self, *args, **kwargs):
        # Enforce clean() on every save (create and update), not only via admin forms,
        # so a CLI/ORM update can't persist an invalid template (e.g. a non-list of
        # required variables) that later breaks rendering.
        self.full_clean()
        super().save(*args, **kwargs)

