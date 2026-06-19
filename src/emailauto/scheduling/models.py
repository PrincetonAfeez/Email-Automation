from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from emailauto.core.states import CampaignRunStatus, ScheduleType


class CampaignSchedule(models.Model):
    class IntervalPeriod(models.TextChoices):
        MINUTES = "minutes", "Minutes"
        HOURS = "hours", "Hours"
        DAYS = "days", "Days"

    campaign = models.ForeignKey("campaigns.Campaign", on_delete=models.CASCADE, related_name="schedules")
    schedule_type = models.CharField(max_length=20, choices=ScheduleType.CHOICES)
    send_at = models.DateTimeField(null=True, blank=True, help_text="UTC time for one-time schedules or first recurring run.")
    cron_expression = models.CharField(max_length=80, blank=True, help_text="Five-field cron expression for recurring schedules.")
    interval_every = models.PositiveIntegerField(null=True, blank=True)
    interval_period = models.CharField(max_length=20, choices=IntervalPeriod.choices, blank=True)
    timezone_name = models.CharField(
        max_length=80,
        default="UTC",
        help_text="Display-only timezone for operator UI. Dispatch always uses UTC.",
    )
    enabled = models.BooleanField(default=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["next_run_at", "send_at", "id"]

    def __str__(self) -> str:
        return f"{self.campaign} {self.schedule_type}"

    def clean(self) -> None:
        if self.schedule_type == ScheduleType.ONE_TIME and not self.send_at:
            raise ValidationError({"send_at": "One-time schedules require send_at."})
        if self.schedule_type == ScheduleType.RECURRING and not (
            self.cron_expression or (self.interval_every and self.interval_period)
        ):
            raise ValidationError("Recurring schedules require either cron_expression or interval settings.")
        if self.cron_expression:
            from emailauto.scheduling.recurrence import validate_cron_expression

            try:
                validate_cron_expression(self.cron_expression)
            except ValueError as exc:
                raise ValidationError({"cron_expression": str(exc)}) from exc

    def save(self, *args, **kwargs):
        if self.schedule_type == ScheduleType.ONE_TIME and self.send_at:
            self.next_run_at = self.send_at
        elif self.schedule_type == ScheduleType.RECURRING and self.next_run_at is None:
            self.next_run_at = self.send_at or timezone.now()
        # Enforce clean() on every save (create and update) so invalid schedules can't be
        # made via the ORM/services, not only through admin forms.
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def send_at_local(self):
        from emailauto.core.clock import to_timezone

        return to_timezone(self.send_at, self.timezone_name)

    @property
    def next_run_at_local(self):
        from emailauto.core.clock import to_timezone

        return to_timezone(self.next_run_at, self.timezone_name)


class CampaignRun(models.Model):
    campaign = models.ForeignKey("campaigns.Campaign", on_delete=models.CASCADE, related_name="runs")
    schedule = models.ForeignKey(CampaignSchedule, on_delete=models.CASCADE, related_name="runs")
    run_key = models.CharField(max_length=255, unique=True)
    scheduled_for = models.DateTimeField()
    generated_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=30, choices=CampaignRunStatus.CHOICES, default=CampaignRunStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-scheduled_for"]
        constraints = [
            models.UniqueConstraint(fields=["schedule", "scheduled_for"], name="unique_schedule_occurrence"),
        ]

    def __str__(self) -> str:
        return f"{self.campaign} @ {self.scheduled_for.isoformat()}"

