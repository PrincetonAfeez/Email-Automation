from __future__ import annotations

from django.db import models

from emailauto.core.states import AttemptResult, EventType, OutboxStatus


class EmailOutbox(models.Model):
    campaign = models.ForeignKey("campaigns.Campaign", on_delete=models.CASCADE, related_name="outbox_rows")
    campaign_run = models.ForeignKey("scheduling.CampaignRun", on_delete=models.CASCADE, related_name="outbox_rows")
    recipient = models.ForeignKey("recipients.Recipient", on_delete=models.PROTECT, related_name="outbox_rows")
    template = models.ForeignKey("email_templates.EmailTemplate", on_delete=models.PROTECT, related_name="outbox_rows")
    subject_snapshot = models.TextField()
    body_snapshot = models.TextField()
    required_variables_snapshot = models.JSONField(default=list, blank=True)
    body_format = models.CharField(max_length=10, default="text")
    idempotency_key = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=30, choices=OutboxStatus.CHOICES, default=OutboxStatus.PENDING)
    scheduled_for = models.DateTimeField()
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3)
    locked_by = models.CharField(max_length=150, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    claim_token = models.CharField(max_length=64, blank=True)
    lock_version = models.PositiveIntegerField(default=0)
    celery_task_id = models.CharField(max_length=255, blank=True)
    enqueued_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    dead_lettered_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scheduled_for", "id"]
        indexes = [
            models.Index(fields=["status", "next_attempt_at"]),
            models.Index(fields=["status", "locked_at"]),
            models.Index(fields=["campaign", "status"]),
            models.Index(fields=["campaign_run", "recipient"]),
        ]

    def __str__(self) -> str:
        return f"{self.recipient.email} [{self.status}]"


class EmailSendAttempt(models.Model):
    outbox = models.ForeignKey(EmailOutbox, on_delete=models.CASCADE, related_name="attempts")
    attempt_number = models.PositiveIntegerField()
    worker_id = models.CharField(max_length=150, blank=True)
    celery_task_id = models.CharField(max_length=255, blank=True)
    provider_name = models.CharField(max_length=80)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    result = models.CharField(max_length=30, choices=AttemptResult.CHOICES, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    error_message = models.TextField(blank=True)
    provider_response_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["outbox", "attempt_number"]
        constraints = [
            models.UniqueConstraint(fields=["outbox", "attempt_number"], name="unique_outbox_attempt_number"),
        ]

    def __str__(self) -> str:
        return f"{self.outbox_id} attempt {self.attempt_number}: {self.result or 'started'}"


class EmailEventLog(models.Model):
    event_type = models.CharField(max_length=50, choices=EventType.CHOICES)
    campaign = models.ForeignKey("campaigns.Campaign", null=True, blank=True, on_delete=models.CASCADE, related_name="event_logs")
    campaign_run = models.ForeignKey("scheduling.CampaignRun", null=True, blank=True, on_delete=models.CASCADE, related_name="event_logs")
    outbox = models.ForeignKey(EmailOutbox, null=True, blank=True, on_delete=models.CASCADE, related_name="event_logs")
    recipient = models.ForeignKey("recipients.Recipient", null=True, blank=True, on_delete=models.SET_NULL, related_name="event_logs")
    message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["event_type", "created_at"]),
            models.Index(fields=["outbox", "created_at"]),
            models.Index(fields=["campaign", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} @ {self.created_at:%Y-%m-%d %H:%M:%S}"

