from __future__ import annotations

from django.db import models


class Recipient(models.Model):
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=150, blank=True)
    custom_fields = models.JSONField(default=dict, blank=True)
    subscribed = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["email"]

    def __str__(self) -> str:
        return self.email

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)


class RecipientList(models.Model):
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    recipients = models.ManyToManyField(Recipient, related_name="recipient_lists", blank=True)
    segment_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class SuppressionEntry(models.Model):
    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        UNSUBSCRIBE = "unsubscribe", "Unsubscribe"
        IMPORT = "import", "Import"
        BOUNCE = "bounce", "Bounce"
        TEST = "test", "Test"

    email = models.EmailField(unique=True)
    reason = models.CharField(max_length=255)
    source = models.CharField(max_length=30, choices=Source.choices, default=Source.MANUAL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["email"]

    def __str__(self) -> str:
        return f"{self.email} ({self.reason})"

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

